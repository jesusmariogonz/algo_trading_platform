"""Motor de los 3 Quant Portfolios — rebalanceo a pesos objetivo con
Risk Engine real integrado (circuit breakers), no solo sugerencias.

Mecánica por tick (un día de mercado):
  1. Si es un día nuevo, fija `day_start_equity` (equity con el que
     empezó HOY, antes de cualquier cambio) — es la base para el
     circuit breaker de pérdida diaria.
  2. Calcula equity actual (cash + valor de mercado de lo que ya
     tiene) con los precios de hoy.
  3. CIRCUIT BREAKERS (antes de decidir nada más):
     - Pérdida diaria: si (day_start_equity - equity_hoy) / day_start_equity
       >= daily_loss_limit_pct, se bloquean NUEVAS entradas por el
       resto del día (se resetea automáticamente al día siguiente).
     - Drawdown de revisión: si (peak_equity - equity_hoy) / peak_equity
       >= drawdown_review_pct, el portafolio queda SUSPENDIDO — no
       solo por hoy, sino hasta que se reautorice a mano
       (src/risk/reauthorize.py). Esto es la regla del usuario:
       "revisa posiciones y exige autorización para reactivarse. No
       significa liquidar automáticamente toda la cartera" — por eso
       NO vende lo que ya tiene, solo bloquea comprar más.
  4. Si toca rebalanceo (mensual o diario según el portafolio) y NO
     está bloqueado/suspendido: para cada activo, si su filtro de
     tendencia pasa, su peso objetivo es el peso completo definido;
     si no, es el peso "defensivo" (una fracción menor, no cero) —
     ver definitions.py. Si SÍ está bloqueado/suspendido, no se
     aumenta ninguna posición (el rebalanceo, si corre, solo puede
     reducir exposición, nunca incrementarla).
  5. Guarda el snapshot del día en el historial (nunca se sobrescribe).
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.backtesting.run import load_universe
from src.quant_portfolios.definitions import PORTFOLIOS, PortfolioDefinition
from src.quant_portfolios.trend_filters import TREND_FILTERS

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "quant_portfolios" / "state.json"
HISTORY_PATH = ROOT / "data" / "quant_portfolios" / "history.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text())


def save_history(history: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def init_portfolio_state(starting_capital: float) -> dict:
    return {
        "starting_capital": round(starting_capital, 2),
        "start_date": date.today().isoformat(),
        "cash": round(starting_capital, 2),
        "holdings": {},  # símbolo -> acciones (puede ser fraccionario)
        "peak_equity": round(starting_capital, 2),
        "day_start_equity": round(starting_capital, 2),
        "day_start_date": None,
        "last_rebalance_month": None,
        "suspended": False,
        "suspended_reason": None,
        "suspended_since": None,
        "daily_loss_tripped_today": False,
    }


def _last_row_as_of(df: pd.DataFrame, as_of: pd.Timestamp | None):
    snapshot = df if as_of is None else df[df["date"] <= as_of]
    if snapshot.empty:
        return None
    return snapshot.iloc[-1]


def _today_label(universe: dict, as_of: pd.Timestamp | None) -> str | None:
    for df in universe.values():
        last = _last_row_as_of(df, as_of)
        if last is not None:
            return str(last["date"].date())
    return None


def compute_equity(state: dict, prices: dict[str, float]) -> float:
    value = state["cash"]
    for symbol, shares in state["holdings"].items():
        if symbol in prices:
            value += shares * prices[symbol]
    return value


def should_rebalance(portfolio_def: PortfolioDefinition, state: dict, today: str) -> bool:
    if portfolio_def.rebalance_frequency == "daily":
        return True
    # "monthly": rebalancea la primera vez que se ve un mes calendario nuevo
    month = today[:7]  # "YYYY-MM"
    return state.get("last_rebalance_month") != month


def rebalance_to_weights(state: dict, prices: dict[str, float], target_weights: dict[str, float], equity: float) -> None:
    """Ajusta holdings/cash para que cada símbolo valga
    target_weights[symbol] * equity al precio de hoy. Permite
    fracciones de acciones (Alpaca las soporta en los instrumentos
    elegibles — ver propuesta del usuario)."""
    for symbol, target_weight in target_weights.items():
        price = prices.get(symbol)
        if price is None or price <= 0:
            continue
        target_value = equity * target_weight
        target_shares = target_value / price
        current_shares = state["holdings"].get(symbol, 0.0)
        delta_shares = target_shares - current_shares
        state["cash"] -= delta_shares * price
        state["holdings"][symbol] = round(target_shares, 6)


def run_portfolio_tick(portfolio_id: str, state: dict, as_of: pd.Timestamp | None = None) -> dict:
    portfolio_def = PORTFOLIOS[portfolio_id]
    symbols = list(portfolio_def.weights.keys())
    universe = load_universe(symbols=symbols)

    today = _today_label(universe, as_of)
    if today is None:
        return {"date": None}

    # --- 1. ¿Día nuevo? Fija el equity con el que arrancó hoy ---
    prices_today = {}
    trend_status = {}
    for symbol in symbols:
        last = _last_row_as_of(universe[symbol], as_of)
        if last is None:
            continue
        prices_today[symbol] = float(last["close"])
        trend_status[symbol] = TREND_FILTERS[portfolio_def.trend_filter](last)

    if state["day_start_date"] != today:
        state["day_start_equity"] = compute_equity(state, prices_today)
        state["day_start_date"] = today
        state["daily_loss_tripped_today"] = False

    # --- 2. Equity actual (antes de rebalancear) ---
    equity_before = compute_equity(state, prices_today)

    # --- 3. Circuit breakers ---
    daily_loss_pct = (
        (state["day_start_equity"] - equity_before) / state["day_start_equity"]
        if state["day_start_equity"]
        else 0.0
    )
    if daily_loss_pct >= portfolio_def.daily_loss_limit_pct:
        state["daily_loss_tripped_today"] = True

    state["peak_equity"] = max(state["peak_equity"], equity_before)
    drawdown_pct = (
        (state["peak_equity"] - equity_before) / state["peak_equity"] if state["peak_equity"] else 0.0
    )
    newly_suspended = False
    if drawdown_pct >= portfolio_def.drawdown_review_pct and not state["suspended"]:
        state["suspended"] = True
        state["suspended_reason"] = (
            f"Drawdown {drawdown_pct*100:.1f}% alcanzó el límite de revisión "
            f"({portfolio_def.drawdown_review_pct*100:.0f}%)"
        )
        state["suspended_since"] = today
        newly_suspended = True

    blocked = state["suspended"] or state["daily_loss_tripped_today"]

    # --- 4. Rebalanceo (nunca incrementa exposición si está bloqueado) ---
    rebalanced = False
    if should_rebalance(portfolio_def, state, today):
        target_weights = {}
        for symbol, weight in portfolio_def.weights.items():
            full_weight_ok = trend_status.get(symbol, False) and not blocked
            target_weights[symbol] = weight if full_weight_ok else weight * portfolio_def.defensive_scale
        rebalance_to_weights(state, prices_today, target_weights, equity_before)
        state["last_rebalance_month"] = today[:7]
        rebalanced = True

    equity_after = compute_equity(state, prices_today)
    state["peak_equity"] = max(state["peak_equity"], equity_after)

    return {
        "date": today,
        "equity": round(equity_after, 2),
        "cash": round(state["cash"], 2),
        "holdings": dict(state["holdings"]),
        "daily_loss_pct": round(daily_loss_pct * 100, 2),
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "daily_loss_breaker_tripped": state["daily_loss_tripped_today"],
        "suspended": state["suspended"],
        "suspended_reason": state["suspended_reason"],
        "newly_suspended_today": newly_suspended,
        "rebalanced_today": rebalanced,
        "cumulative_return_pct": round((equity_after / state["starting_capital"] - 1) * 100, 2),
        "trend_status": trend_status,
    }


def run_daily_tick_all(as_of: pd.Timestamp | None = None) -> dict:
    state = load_state()
    snapshot = {"date": None, "portfolios": {}}

    for portfolio_id, portfolio_def in PORTFOLIOS.items():
        if portfolio_id not in state:
            # Capital inicial: parte en partes iguales entre los 3
            # portafolios desde el mismo $1,000 de referencia del
            # proyecto — el usuario los definió como modelos a
            # comparar con el MISMO capital, no 3 cuentas financiadas
            # por separado (ver su propia recomendación, sección 6).
            state[portfolio_id] = init_portfolio_state(1000.0 / len(PORTFOLIOS))

        result = run_portfolio_tick(portfolio_id, state[portfolio_id], as_of)
        snapshot["portfolios"][portfolio_id] = result
        if result.get("date"):
            snapshot["date"] = result["date"]

    save_state(state)

    if snapshot["date"]:
        history = load_history()
        history = [h for h in history if h["date"] != snapshot["date"]]
        history.append(snapshot)
        history.sort(key=lambda h: h["date"])
        save_history(history)

    return snapshot
