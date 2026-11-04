"""Motor de Paper Trading EN VIVO — mismas reglas de entrada/salida que
`src/paper_trading/engine.py` (señales, trailing stop, circuit
breakers), pero las posiciones se abren y cierran con órdenes REALES
de mercado contra la cuenta paper de IBKR (ver ADR 0022 y 0023),
usando el fill real en vez del precio de cierre.

Corre EN PARALELO al motor simulado, con su propio estado
(`data/paper_trading_live/`), para poder comparar simulado vs.
ejecución real sin arriesgar el histórico ya acumulado del simulado.

Diferencia deliberada vs. el motor simulado (ver ADR 0023): el cash
ocioso NO se invierte en el benchmark SPY/GLD aquí — se queda como
cash real en la cuenta. Invertirlo implicaría mandar órdenes reales de
SPY/GLD constantemente solo para "parquear" cash, multiplicando el
volumen de operaciones reales sin aportar a la pregunta que este motor
está validando (¿las señales se ejecutan bien contra un broker real?).
Esto hace que el equity reportado aquí no sea 1:1 comparable al
simulado en buckets con mucho cash ocioso — es una limitación conocida,
no un bug.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.backtesting.run import load_universe
from src.broker.ibkr_adapter import Fill, OrdenNoLlenada, ejecutar_orden_mercado, posiciones_reales
from src.paper_trading.engine import (
    FRICCION_POR_LADO,
    RISK_LIMITS,
    _last_row_as_of,
    _signals_for_symbol,
)
from src.screening.daily_signals import BUCKET_CONFIG, read_universe_file

ROOT = Path(__file__).resolve().parents[2]
LIVE_STATE_PATH = ROOT / "data" / "paper_trading_live" / "state.json"
LIVE_HISTORY_PATH = ROOT / "data" / "paper_trading_live" / "history.json"

ACTIVE_BUCKETS = list(BUCKET_CONFIG.keys())


def load_state() -> dict:
    if not LIVE_STATE_PATH.exists():
        return {}
    return json.loads(LIVE_STATE_PATH.read_text())


def save_state(state: dict) -> None:
    LIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_history() -> list[dict]:
    if not LIVE_HISTORY_PATH.exists():
        return []
    return json.loads(LIVE_HISTORY_PATH.read_text())


def save_history(history: list[dict]) -> None:
    LIVE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def init_bucket_state(bucket: str, starting_capital: float) -> dict:
    """A diferencia del motor simulado, el cash arranca como cash real
    — no se invierte en benchmark (ver docstring del módulo)."""
    return {
        "starting_capital": round(starting_capital, 2),
        "start_date": date.today().isoformat(),
        "cash": round(starting_capital, 2),
        "open_positions": [],
        "closed_positions": [],
        "peak_equity": round(starting_capital, 2),
        "day_start_equity": round(starting_capital, 2),
        "day_start_date": None,
        "suspended": False,
        "suspended_reason": None,
        "suspended_since": None,
        "daily_loss_tripped_today": False,
        "ordenes_fallidas": [],
    }


def run_bucket_tick_live(bucket: str, bucket_state: dict, ib, as_of: pd.Timestamp | None = None) -> dict:
    """Un día de mercado para un bucket, con órdenes reales vía `ib`
    (una conexión ya conectada de `src.broker.ibkr_adapter.conectar`).

    `as_of` solo existe para pruebas con mocks — en uso real se deja
    en None y usa el último dato descargado, igual que el simulado."""
    config = BUCKET_CONFIG[bucket]
    symbols = read_universe_file(config["universe_file"])
    risk_pct = config["risk_pct"]
    strategies = config["strategies"]
    universe = load_universe(symbols=symbols)

    today_label = None
    for df in universe.values():
        last = _last_row_as_of(df, as_of)
        if last is not None:
            today_label = str(last["date"].date())
            break

    open_positions = bucket_state["open_positions"]
    cash = bucket_state.get("cash", 0.0)
    closed_today = []
    ordenes_fallidas_hoy = []

    # --- 1. Revisar posiciones abiertas: trailing stop o señal de salida ---
    still_open = []
    for pos in open_positions:
        symbol = pos["symbol"]
        df = universe.get(symbol)
        if df is None:
            still_open.append(pos)
            continue
        signaled = _signals_for_symbol(df, pos["strategy"])
        last = _last_row_as_of(signaled, as_of)
        if last is None:
            still_open.append(pos)
            continue
        today_label = str(last["date"].date())

        pos["stop_price"] = max(pos["stop_price"], float(last["stop_price"]))
        close_price = float(last["close"])
        stop_hit = close_price <= pos["stop_price"]
        exit_signal = int(last["signal"]) == -1

        if not (stop_hit or exit_signal):
            still_open.append(pos)
            continue

        try:
            fill: Fill = ejecutar_orden_mercado(ib, symbol, "SELL", pos["shares"])
        except OrdenNoLlenada as e:
            # No se pudo cerrar hoy — se queda abierta, se reintenta
            # mañana. Nunca se asume cerrada sin un fill real.
            ordenes_fallidas_hoy.append({"symbol": symbol, "accion": "SELL", "error": str(e)})
            still_open.append(pos)
            continue

        proceeds = fill.precio_promedio * pos["shares"]
        pnl = proceeds - pos["entry_price"] * pos["shares"]
        cash += proceeds
        closed_today.append(
            {
                **pos,
                "exit_date": today_label,
                "exit_price": round(fill.precio_promedio, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round((proceeds / (pos["entry_price"] * pos["shares"]) - 1) * 100, 2),
                "reason": "stop_hit" if stop_hit else "signal_exit",
            }
        )

    open_positions = still_open

    # --- 1.5. Circuit breakers — misma mecánica que el motor simulado ---
    limits = RISK_LIMITS.get(bucket)
    blocked = False
    daily_loss_pct = 0.0
    drawdown_pct = 0.0
    newly_suspended = False
    equity_now = bucket_state["starting_capital"]
    if limits is not None and today_label is not None:
        if bucket_state.get("day_start_date") != today_label:
            bucket_state["day_start_equity"] = bucket_state.get("last_equity", bucket_state["starting_capital"])
            bucket_state["day_start_date"] = today_label
            bucket_state["daily_loss_tripped_today"] = False

        unrealized_now = sum(
            float(_last_row_as_of(universe[p["symbol"]], as_of)["close"]) * p["shares"]
            for p in open_positions
            if universe.get(p["symbol"]) is not None and _last_row_as_of(universe[p["symbol"]], as_of) is not None
        )
        equity_now = cash + unrealized_now

        day_start_equity = bucket_state.get("day_start_equity") or bucket_state["starting_capital"]
        daily_loss_pct = (day_start_equity - equity_now) / day_start_equity if day_start_equity else 0.0
        if daily_loss_pct >= limits["daily_loss_limit_pct"]:
            bucket_state["daily_loss_tripped_today"] = True

        bucket_state["peak_equity"] = max(bucket_state.get("peak_equity", 0.0), equity_now)
        peak_equity = bucket_state["peak_equity"]
        drawdown_pct = (peak_equity - equity_now) / peak_equity if peak_equity else 0.0
        if drawdown_pct >= limits["drawdown_review_pct"] and not bucket_state.get("suspended"):
            bucket_state["suspended"] = True
            bucket_state["suspended_reason"] = (
                f"Drawdown {drawdown_pct*100:.1f}% alcanzó el límite de revisión "
                f"({limits['drawdown_review_pct']*100:.0f}%)"
            )
            bucket_state["suspended_since"] = today_label
            newly_suspended = True

        blocked = bucket_state.get("suspended", False) or bucket_state.get("daily_loss_tripped_today", False)

    # --- 2. Señales de entrada de hoy ---
    open_symbols = {p["symbol"] for p in open_positions}
    if blocked:
        strategies = []
    for strategy_key in strategies:
        for symbol in symbols:
            if symbol in open_symbols:
                continue
            df = universe.get(symbol)
            if df is None:
                continue
            signaled = _signals_for_symbol(df, strategy_key)
            last = _last_row_as_of(signaled, as_of)
            if last is None or int(last["signal"]) != 1:
                continue
            today_label = str(last["date"].date())

            entry_price_estimado = float(last["close"])
            stop_price = float(last["stop_price"])
            risk_per_share = entry_price_estimado - stop_price
            if risk_per_share <= 0:
                continue

            risk_amount = equity_now * risk_pct
            shares = int(risk_amount // risk_per_share)
            # Costo estimado con la misma fricción del backtest, solo
            # para decidir si alcanza el cash — el costo REAL lo da el
            # fill de la orden, no esta estimación.
            cost_estimado = shares * entry_price_estimado * (1 + FRICCION_POR_LADO)
            if shares < 1 or cost_estimado > cash:
                continue

            try:
                fill: Fill = ejecutar_orden_mercado(ib, symbol, "BUY", shares)
            except OrdenNoLlenada as e:
                ordenes_fallidas_hoy.append({"symbol": symbol, "accion": "BUY", "error": str(e)})
                continue

            cost_real = fill.precio_promedio * shares
            if cost_real > cash:
                # El fill real salió más caro que el estimado y ya no
                # alcanza — no debería pasar casi nunca (fricción real
                # suele ser menor al 0.1% estimado), pero si pasa, no
                # se inventa cash: se registra y se sigue.
                ordenes_fallidas_hoy.append(
                    {
                        "symbol": symbol,
                        "accion": "BUY",
                        "error": f"fill real (${cost_real:.2f}) superó el cash disponible (${cash:.2f})",
                    }
                )
                continue

            cash -= cost_real
            open_positions.append(
                {
                    "symbol": symbol,
                    "strategy": strategy_key,
                    "entry_date": today_label,
                    "entry_price": round(fill.precio_promedio, 2),
                    "stop_price": round(stop_price, 2),
                    "shares": shares,
                }
            )
            open_symbols.add(symbol)

    # --- 3. Equity del bucket ---
    unrealized = 0.0
    for pos in open_positions:
        df = universe.get(pos["symbol"])
        if df is None:
            continue
        last = _last_row_as_of(df, as_of)
        if last is None:
            continue
        unrealized += float(last["close"]) * pos["shares"]
        today_label = today_label or str(last["date"].date())

    equity = cash + unrealized
    realized_pnl_today = sum(c["pnl"] for c in closed_today)

    bucket_state["cash"] = round(cash, 2)
    bucket_state["open_positions"] = open_positions
    bucket_state["closed_positions"].extend(closed_today)
    bucket_state.setdefault("ordenes_fallidas", []).extend(ordenes_fallidas_hoy)
    if limits is not None:
        bucket_state["peak_equity"] = max(bucket_state.get("peak_equity", 0.0), equity)
        bucket_state["last_equity"] = equity

    return {
        "date": today_label,
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "unrealized_pnl": round(unrealized - sum(p["entry_price"] * p["shares"] for p in open_positions), 2),
        "open_count": len(open_positions),
        "closed_today": len(closed_today),
        "realized_pnl_today": round(realized_pnl_today, 2),
        "cumulative_return_pct": round((equity / bucket_state["starting_capital"] - 1) * 100, 2),
        "closed_today_detail": closed_today,
        "ordenes_fallidas_hoy": ordenes_fallidas_hoy,
        "daily_loss_pct": round(daily_loss_pct * 100, 2),
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "daily_loss_breaker_tripped": bucket_state.get("daily_loss_tripped_today", False),
        "suspended": bucket_state.get("suspended", False),
        "suspended_reason": bucket_state.get("suspended_reason"),
        "newly_suspended_today": newly_suspended,
    }


def run_daily_tick_live(ib, starting_capital_por_bucket: dict[str, float]) -> dict:
    """`starting_capital_por_bucket`: capital inicial por bucket, fijado
    una sola vez (igual que el motor simulado) — se pasa explícito en
    vez de leer de `allocation.get_balances()` porque esa función
    reporta el capital del PORTAFOLIO SIMULADO, no de la cuenta real de
    IBKR; quien llama a esto decide cómo repartir el equity real de la
    cuenta paper entre los 4 buckets."""
    state = load_state()
    snapshot = {"date": None, "buckets": {}, "alertas": []}

    for bucket in ACTIVE_BUCKETS:
        if bucket not in state:
            capital = starting_capital_por_bucket.get(bucket, 0.0)
            if capital <= 0:
                continue
            state[bucket] = init_bucket_state(bucket, capital)

        equity_antes = state[bucket].get("last_equity")
        result = run_bucket_tick_live(bucket, state[bucket], ib)
        snapshot["buckets"][bucket] = result

        if equity_antes and equity_antes > 0:
            cambio_pct = abs(result["equity"] - equity_antes) / equity_antes
            if cambio_pct > 0.25:
                alerta = (
                    f"⚠️⚠️ SALTO DE EQUITY SOSPECHOSO (LIVE) en '{bucket}': "
                    f"${equity_antes:.2f} -> ${result['equity']:.2f} "
                    f"({cambio_pct*100:.1f}% en un día)."
                )
                snapshot["alertas"].append(alerta)

        if result.get("ordenes_fallidas_hoy"):
            for o in result["ordenes_fallidas_hoy"]:
                snapshot["alertas"].append(
                    f"⚠️ Orden fallida en '{bucket}': {o['accion']} {o['symbol']} — {o['error']}"
                )

        if result["date"]:
            snapshot["date"] = result["date"]

    save_state(state)

    if snapshot["date"]:
        history = load_history()
        history = [h for h in history if h["date"] != snapshot["date"]]
        history.append(snapshot)
        history.sort(key=lambda h: h["date"])
        save_history(history)

    return snapshot


def posiciones_reconciliadas(ib) -> dict:
    """Compara lo que el estado local cree tener abierto, bucket por
    bucket, contra lo que IBKR reporta como posiciones reales de la
    cuenta — para detectar divergencias (ej. una orden que se llenó
    parcialmente, o algo movido fuera de este motor)."""
    state = load_state()
    reales = posiciones_reales(ib)

    esperado: dict[str, int] = {}
    for bucket, bstate in state.items():
        for pos in bstate.get("open_positions", []):
            esperado[pos["symbol"]] = esperado.get(pos["symbol"], 0) + pos["shares"]

    simbolos = set(esperado) | set(reales)
    divergencias = {
        s: {"esperado": esperado.get(s, 0), "real": reales.get(s, 0)}
        for s in simbolos
        if esperado.get(s, 0) != reales.get(s, 0)
    }
    return {"esperado": esperado, "real": reales, "divergencias": divergencias}
