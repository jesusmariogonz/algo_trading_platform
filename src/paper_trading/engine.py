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
  1. Revisa las posiciones abiertas: si el precio de hoy tocó el stop,
     o la estrategia da señal de salida, se cierra (a precio de cierre
     o al stop, el que corresponda).
  2. Para las señales de entrada de hoy (mismas reglas que
     daily_signals.py) que no estén ya abiertas, abre una posición si
     el efectivo disponible del bucket alcanza para al menos 1 acción
     respetando el % de riesgo del bucket.
  3. Calcula el equity del bucket (efectivo + valor de mercado de las
     posiciones abiertas) y lo agrega al historial.

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


def init_bucket_state(bucket: str, starting_capital: float) -> dict:
    return {
        "starting_capital": round(starting_capital, 2),
        "start_date": date.today().isoformat(),
        "cash": round(starting_capital, 2),
        "open_positions": [],
        "closed_positions": [],
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

    today_label = None
    cash = bucket_state["cash"]
    open_positions = bucket_state["open_positions"]
    closed_today = []

    # --- 1. Revisar posiciones abiertas: stop o señal de salida ---
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

        close_price = float(last["close"])
        stop_hit = close_price <= pos["stop_price"]
        exit_signal = int(last["signal"]) == -1

        if stop_hit or exit_signal:
            exit_price = pos["stop_price"] if stop_hit else close_price
            proceeds = exit_price * pos["shares"]
            pnl = proceeds - pos["entry_price"] * pos["shares"]
            cash += proceeds
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

    # --- 2. Señales de entrada de hoy ---
    open_symbols = {p["symbol"] for p in open_positions}
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
            if shares < 1 or cost > cash:
                continue

            cash -= cost
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

    equity = cash + unrealized
    realized_pnl_today = sum(c["pnl"] for c in closed_today)

    bucket_state["cash"] = round(cash, 2)
    bucket_state["open_positions"] = open_positions
    bucket_state["closed_positions"].extend(closed_today)

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
            state[bucket] = init_bucket_state(bucket, starting_capital)

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
