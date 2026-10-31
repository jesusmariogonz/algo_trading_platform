"""Motor de Paper Trading — simula, día tras día, abrir y cerrar
posiciones EXACTAMENTE con las mismas reglas del screener diario
(src/screening/daily_signals.py), pero sin que tú tengas que decidir
nada: aquí sí se "ejecuta" automáticamente, porque no es dinero real.

Es el puente entre "el backtest dice que esto funcionó en el pasado"
y "operarlo con dinero real" — el master prompt lo exige
explícitamente antes de habilitar LIVE (docs/vision.md § Modos:
RESEARCH, BACKTEST, PAPER, LIVE).

Estado persistido en:
  data/paper_trading/state.json    — posiciones abiertas por bucket
  data/paper_trading/history.json  — snapshot diario por bucket (append-only)

Cada corrida de `run_daily_tick()` representa UN día de mercado:
  1. Revisa las posiciones abiertas: se recalcula el stop del día
     (trailing stop — ver abajo) y se cierra si el precio lo tocó, o
     si la estrategia da señal de salida.
  2. Para las señales de entrada de hoy (mismas reglas que
     daily_signals.py) que no estén ya abiertas, abre una posición si
     el efectivo disponible del bucket alcanza para al menos 1 acción
     respetando el % de riesgo del bucket.
  3. Calcula el equity del bucket (cash/benchmark + valor de mercado
     de las posiciones abiertas) y lo agrega al historial.

CAMBIOS vs. la versión original (decisión del usuario tras comparar
backtests reales de 2025-2026 — ver docs/adr/0006-elimina-bucket-cripto.md
y docs/adr/0007-trailing-stop-y-cash-en-benchmark.md):

  - TRAILING STOP: el stop ya no queda fijo en el precio de entrada.
    Cada día se recalcula con la misma fórmula de la estrategia
    (close - multiplicador*ATR_14) y solo SUBE si el nuevo cálculo es
    más alto que el guardado — nunca baja. Deja correr ganadores sin
    aumentar el riesgo ya asumido al entrar.
  - CASH OCIOSO EN BENCHMARK: el efectivo que no está en ninguna
    posición se invierte en BENCHMARK_SYMBOL (SPY) en vez de quedarse
    parado sin generar nada. Se marca a mercado cada día; al abrir una
    posición nueva se vende la porción de benchmark necesaria.
  - Bucket de cripto (muy_alta_volatilidad) ELIMINADO: el backtest con
    cripto rindió peor en las 3 ventanas probadas (6, 22 y 34 meses).
    El 10% que tenía se repartió EQUITATIVAMENTE entre los 3 buckets
    restantes (decisión explícita del usuario) — ver allocation.py.
  - RISK ENGINE REAL (circuit breakers), llevado desde los Quant
    Portfolios (ver docs/adr/0008-circuit-breakers-en-buckets.md):
      * Pérdida diaria: si el equity cae más del límite desde el
        inicio del día, se bloquean NUEVAS entradas por el resto del
        día (se resetea solo al día siguiente). Las posiciones ya
        abiertas se revisan igual (stop/señal de salida no se bloquea).
      * Drawdown de revisión: si el equity cae más del límite desde su
        máximo histórico, el bucket queda SUSPENDIDO hasta
        reautorización manual (`python -m src.paper_trading.reauthorize
        <bucket>`) — nunca liquida posiciones existentes, solo bloquea
        aumentar exposición.

IMPORTANTE: el capital "starting_capital" de cada bucket se fija la
PRIMERA vez que se corre el motor (snapshot del libro de
allocation.py en ese momento) y no se mueve con inyecciones
posteriores durante la ventana de prueba — así el % de retorno mide
el desempeño de la estrategia, no confunde "metí más dinero" con
"la estrategia ganó más". Nuevas inyecciones durante el paper trading
se ignoran a propósito; se reconcilian manualmente si hace falta.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.backtesting.run import load_universe
from src.portfolio.allocation import get_balances
from src.screening.daily_signals import BUCKET_CONFIG, read_universe_file
from src.strategies.momentum_breakout import generate_signals as momentum_breakout_signals
from src.strategies.time_series_momentum import generate_signals as time_series_momentum_signals
from src.strategies.trend_following import generate_signals as trend_following_signals

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "paper_trading" / "state.json"
HISTORY_PATH = ROOT / "data" / "paper_trading" / "history.json"

SIGNAL_FNS = {
    "trend_following": trend_following_signals,
    "momentum_breakout": momentum_breakout_signals,
    "time_series_momentum": time_series_momentum_signals,
}

# Benchmark donde se invierte el cash ocioso de cada bucket — todos
# los buckets restantes son de acciones/ETFs de EE.UU., así que SPY
# es el ancla natural (ver ADR 0007).
BENCHMARK_SYMBOL = {
    "largo_plazo": "SPY",
    "mediano_plazo": "SPY",
    "riesgo_alto": "SPY",
}

# Circuit breakers por bucket — misma mecánica que src/quant_portfolios
# (ver ADR 0008), con límites crecientes según el riesgo de cada
# bucket (1%/1.5%/2% riesgo por operación -> límites de pérdida diaria
# y drawdown también crecientes).
RISK_LIMITS = {
    "largo_plazo": {"daily_loss_limit_pct": 0.01, "drawdown_review_pct": 0.06},
    "mediano_plazo": {"daily_loss_limit_pct": 0.015, "drawdown_review_pct": 0.10},
    "riesgo_alto": {"daily_loss_limit_pct": 0.02, "drawdown_review_pct": 0.15},
}

ACTIVE_BUCKETS = list(BUCKET_CONFIG.keys())  # buckets con estrategia real — ver BUCKET_CONFIG


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


def _benchmark_price(bucket: str, as_of: pd.Timestamp | None) -> float | None:
    bench_symbol = BENCHMARK_SYMBOL.get(bucket)
    if bench_symbol is None:
        return None
    df = load_universe(symbols=[bench_symbol])[bench_symbol]
    last = _last_row_as_of(df, as_of)
    return None if last is None else float(last["close"])


def init_bucket_state(bucket: str, starting_capital: float, as_of: pd.Timestamp | None = None) -> dict:
    """El capital inicial se invierte de entrada en el benchmark del
    bucket (no se queda en cash parado) — ver ADR 0007."""
    bench_price = _benchmark_price(bucket, as_of)
    bench_shares = starting_capital / bench_price if bench_price else 0.0
    return {
        "starting_capital": round(starting_capital, 2),
        "start_date": date.today().isoformat(),
        "cash": 0.0 if bench_price else round(starting_capital, 2),
        "bench_shares": bench_shares,
        "open_positions": [],
        "closed_positions": [],
        "peak_equity": round(starting_capital, 2),
        "day_start_equity": round(starting_capital, 2),
        "day_start_date": None,
        "suspended": False,
        "suspended_reason": None,
        "suspended_since": None,
        "daily_loss_tripped_today": False,
    }


def _signals_for_symbol(df: pd.DataFrame, strategy_key: str) -> pd.DataFrame:
    df = SIGNAL_FNS[strategy_key](df)
    return df.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)


def _last_row_as_of(df: pd.DataFrame, as_of: pd.Timestamp | None):
    snapshot = df if as_of is None else df[df["date"] <= as_of]
    if snapshot.empty:
        return None
    return snapshot.iloc[-1]


def run_bucket_tick(bucket: str, bucket_state: dict, as_of: pd.Timestamp | None = None) -> dict:
    """Corre un día para un bucket. `as_of` permite simular una fecha
    pasada (lo usa el backfill de demostración) — en uso real se deja
    en None y toma el último dato descargado."""
    config = BUCKET_CONFIG[bucket]
    symbols = read_universe_file(config["universe_file"])
    risk_pct = config["risk_pct"]
    strategies = config["strategies"]
    universe = load_universe(symbols=symbols)

    # Fecha del día: del universo, no de si hubo actividad — un bucket
    # sin posiciones ni señales hoy (ej. sin capital, o sin que nada
    # cumpliera la regla) sigue siendo "hoy" en el historial, no debe
    # quedar con fecha nula (bug real: pasaba antes de este fix).
    today_label = None
    for df in universe.values():
        last = _last_row_as_of(df, as_of)
        if last is not None:
            today_label = str(last["date"].date())
            break

    bench_price = _benchmark_price(bucket, as_of)
    bench_shares = bucket_state.get("bench_shares", 0.0)
    open_positions = bucket_state["open_positions"]
    closed_today = []

    def disponible() -> float:
        return bench_shares * bench_price if bench_price else bucket_state.get("cash", 0.0)

    # --- 1. Revisar posiciones abiertas: trailing stop o señal de salida ---
    still_open = []
    for pos in open_positions:
        symbol = pos["symbol"]
        df = universe.get(symbol)
        if df is None:
            still_open.append(pos)  # símbolo ya no está en el universo del bucket; no se toca
            continue
        signaled = _signals_for_symbol(df, pos["strategy"])
        last = _last_row_as_of(signaled, as_of)
        if last is None:
            still_open.append(pos)
            continue
        today_label = str(last["date"].date())

        # Trailing stop: el stop recalculado de hoy (misma fórmula de
        # la estrategia) solo sube el guardado, nunca lo baja.
        pos["stop_price"] = max(pos["stop_price"], float(last["stop_price"]))

        close_price = float(last["close"])
        stop_hit = close_price <= pos["stop_price"]
        exit_signal = int(last["signal"]) == -1

        if stop_hit or exit_signal:
            exit_price = pos["stop_price"] if stop_hit else close_price
            proceeds = exit_price * pos["shares"]
            pnl = proceeds - pos["entry_price"] * pos["shares"]
            if bench_price:
                bench_shares += proceeds / bench_price
            else:
                bucket_state["cash"] = bucket_state.get("cash", 0.0) + proceeds
            closed = {
                **pos,
                "exit_date": today_label,
                "exit_price": round(exit_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round((exit_price / pos["entry_price"] - 1) * 100, 2),
                "reason": "stop_hit" if stop_hit else "signal_exit",
            }
            closed_today.append(closed)
        else:
            still_open.append(pos)

    open_positions = still_open

    # --- 1.5. Circuit breakers (Risk Engine real) — se evalúan con el
    # equity YA con los cierres de hoy aplicados, antes de decidir
    # entradas nuevas. Nunca bloquean ni revierten un cierre. ---
    limits = RISK_LIMITS.get(bucket)
    blocked = False
    daily_loss_pct = 0.0
    drawdown_pct = 0.0
    newly_suspended = False
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
        equity_now = (bench_shares * bench_price if bench_price else bucket_state.get("cash", 0.0)) + unrealized_now

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

    # --- 2. Señales de entrada de hoy (financiadas vendiendo benchmark si aplica) ---
    # Si está bloqueado (pérdida diaria o suspendido por drawdown), no
    # se abre NADA nuevo hoy — nunca liquida lo que ya está abierto.
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

            entry_price = float(last["close"])
            stop_price = float(last["stop_price"])
            risk_per_share = entry_price - stop_price
            if risk_per_share <= 0:
                continue

            risk_amount = bucket_state["starting_capital"] * risk_pct
            shares = int(risk_amount // risk_per_share)
            cost = shares * entry_price
            if shares < 1 or cost > disponible():
                continue

            if bench_price:
                bench_shares -= cost / bench_price
            else:
                bucket_state["cash"] = bucket_state.get("cash", 0.0) - cost
            open_positions.append(
                {
                    "symbol": symbol,
                    "strategy": strategy_key,
                    "entry_date": today_label,
                    "entry_price": round(entry_price, 2),
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

    cash_val = bench_shares * bench_price if bench_price else bucket_state.get("cash", 0.0)
    equity = cash_val + unrealized
    realized_pnl_today = sum(c["pnl"] for c in closed_today)

    bucket_state["bench_shares"] = bench_shares
    bucket_state["cash"] = round(bucket_state.get("cash", 0.0), 2)
    bucket_state["open_positions"] = open_positions
    bucket_state["closed_positions"].extend(closed_today)
    if limits is not None:
        bucket_state["peak_equity"] = max(bucket_state.get("peak_equity", 0.0), equity)
        bucket_state["last_equity"] = equity

    return {
        "date": today_label,
        "equity": round(equity, 2),
        "cash": round(cash_val, 2),
        "unrealized_pnl": round(unrealized - sum(p["entry_price"] * p["shares"] for p in open_positions), 2),
        "open_count": len(open_positions),
        "closed_today": len(closed_today),
        "realized_pnl_today": round(realized_pnl_today, 2),
        "cumulative_return_pct": round((equity / bucket_state["starting_capital"] - 1) * 100, 2),
        "closed_today_detail": closed_today,
        "daily_loss_pct": round(daily_loss_pct * 100, 2),
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "daily_loss_breaker_tripped": bucket_state.get("daily_loss_tripped_today", False),
        "suspended": bucket_state.get("suspended", False),
        "suspended_reason": bucket_state.get("suspended_reason"),
        "newly_suspended_today": newly_suspended,
    }


def run_daily_tick(as_of: pd.Timestamp | None = None) -> dict:
    state = load_state()
    balances = get_balances()

    snapshot = {"date": None, "buckets": {}}
    for bucket in ACTIVE_BUCKETS:
        if bucket not in state:
            starting_capital = balances.get(bucket, 0.0)
            if starting_capital <= 0:
                continue  # sin capital registrado para este bucket todavía
            state[bucket] = init_bucket_state(bucket, starting_capital, as_of)

        result = run_bucket_tick(bucket, state[bucket], as_of)
        snapshot["buckets"][bucket] = result
        if result["date"]:
            snapshot["date"] = result["date"]

    save_state(state)

    if snapshot["date"]:
        history = load_history()
        # Idempotencia: si ya existe un snapshot para esta fecha, se
        # reemplaza (permite re-correr el mismo día sin duplicar).
        history = [h for h in history if h["date"] != snapshot["date"]]
        history.append(snapshot)
        history.sort(key=lambda h: h["date"])
        save_history(history)

    return snapshot
