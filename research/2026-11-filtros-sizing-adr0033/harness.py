"""Harness de walk-forward rolling para la investigación de mecanismo
de ADR 0040 (filtros de sizing pendientes de ADR 0033).

Reconstruido desde cero: exploracion_2026_11/ era gitignored por diseño
(ver ADR 0033) y el código original de esa investigación ya no existía
en este clon — ese mismo problema de irreproducibilidad es la razón por
la que este archivo ya vive aquí, versionado, en vez de en una carpeta
ignorada (ver ADR 0041). Esta es una reconstrucción de buena fe del MECANISMO
descrito en ADR 0033 ("multiplicador según...", "penaliza tamaño
si..."), no una reproducción byte-a-byte — los parámetros exactos
(ventana del efficiency ratio, piso del multiplicador de correlación,
etc.) no están documentados en el ADR, así que se eligen aquí de forma
razonable y se declaran explícitamente. Por eso el primer paso de
cualquier corrida es la auto-verificación contra los números YA
publicados en ADR 0033 antes de confiar en cualquier descomposición
nueva (mismo principio que el placebo pre-registrado de EXP-002: si no
reproduce, se investiga y documenta la causa, no se fuerza el número).

NO IMPORTA ni modifica src/paper_trading/engine.py, live_engine.py ni
daily_signals.py — la fórmula de sizing (riesgo sobre equity actual,
no capital inicial fijo) y la fricción por lado se replican a mano
abajo porque son del dominio público del repo (ADR 0012, ver
FRICCION_POR_LADO en engine.py), no por import, para no acoplar esta
investigación exploratoria a producción."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # repo root (este archivo vive en research/<slug>/)
sys.path.insert(0, str(ROOT))

from src.backtesting.run import STRATEGIES, load_universe  # noqa: E402

FRICCION_POR_LADO = 0.001  # == engine.py FRICCION_POR_LADO (0.0005+0.0005), valor público del repo

BUCKETS = {
    "largo_plazo": {
        "universe_file": "config/universe_largo_plazo.txt",
        "risk_pct": 0.02,
        "strategy": "time_series_momentum",
    },
    "mediano_plazo": {
        "universe_file": "config/universe.txt",
        "risk_pct": 0.02,
        "strategy": "trend_following",
    },
    "riesgo_alto": {
        "universe_file": "config/universe_riesgo_alto.txt",
        "risk_pct": 0.05,
        "strategy": "momentum_breakout",
    },
}


def read_universe_file(path: Path) -> list[str]:
    symbols = []
    with open(ROOT / path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols


def signaled_universe(bucket_key: str) -> dict[str, pd.DataFrame]:
    """Universo del bucket con `signal`/`stop_price` ya calculados."""
    cfg = BUCKETS[bucket_key]
    symbols = read_universe_file(Path(cfg["universe_file"]))
    params_cls, signal_fn = STRATEGIES[cfg["strategy"]]
    params = params_cls()
    universe = load_universe(symbols=symbols)
    out = {}
    for symbol, df in universe.items():
        try:
            sdf = signal_fn(df, params)
        except ValueError:
            continue  # falta alguna columna (ej. relative_strength) para ese símbolo
        sdf = sdf.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
        if sdf.empty:
            continue
        out[symbol] = sdf
    return out


CROSS_SECTIONAL_FILTER_BUCKETS = {"largo_plazo"}
CROSS_SECTIONAL_PERCENTIL_MIN = 0.70


def apply_cross_sectional_filter(
    universe: dict[str, pd.DataFrame], percentil_min: float = CROSS_SECTIONAL_PERCENTIL_MIN
) -> dict[str, pd.DataFrame]:
    """Corrección (2026-11-19): el harness original de ADR 0040 nunca
    implementó el filtro cross-sectional de entrada que ADR 0034 puso
    en producción SOLO para `largo_plazo` (`CROSS_SECTIONAL_FILTER_
    BUCKETS`/`CROSS_SECTIONAL_PERCENTIL_MIN` en
    `src/paper_trading/engine.py`, reusado por `live_engine.py`) — las
    Capas 1/4/5/6/7 de EXP-003 probaron `largo_plazo` con la
    configuración VIEJA (pre-ADR-0034). Esta función replica fielmente
    `_percentiles_cross_sectional_hoy` + la condición de
    `run_bucket_tick` en `engine.py` (líneas ~384-400 y ~531-559): un
    candidato con `signal==1` se descarta (se pone en 0) si NO cumple
    `return_126d > 0 AND percentil(return_126d, mismo día, todo el
    universo del bucket) >= percentil_min`. No toca `signal==-1`
    (salidas nunca se filtran) ni símbolos sin `signal==1` ese día.

    Opera sobre el universo COMO SEA (real o una réplica bootstrapeada
    del placebo de Capa 4) — no depende de que los datos sean reales,
    solo de que cada DataFrame tenga columnas `date`/`signal`/
    `return_126d`, igual que la salida de `signaled_universe`."""
    idx_in = {s: df.set_index("date") for s, df in universe.items()}
    todas_fechas = sorted({d for df in idx_in.values() for d in df.index})

    out = {s: df.copy() for s, df in universe.items()}
    idx_out = {s: out[s].set_index("date", drop=False) for s in out}

    for fecha in todas_fechas:
        valores = {}
        for s, df in idx_in.items():
            if fecha not in df.index:
                continue
            ret = df.loc[fecha].get("return_126d")
            if pd.notna(ret):
                valores[s] = float(ret)
        if not valores:
            continue
        percentiles = pd.Series(valores).rank(pct=True)
        for s in idx_in:
            if fecha not in idx_out[s].index:
                continue
            if idx_out[s].loc[fecha, "signal"] != 1:
                continue
            ret = valores.get(s)
            perc = percentiles.get(s)
            pasa = ret is not None and ret > 0 and perc is not None and perc >= percentil_min
            if not pasa:
                idx_out[s].loc[fecha, "signal"] = 0

    return {s: df.reset_index(drop=True) for s, df in idx_out.items()}


def rolling_windows(end_date: pd.Timestamp, n_windows: int = 5, train_months: int = 12,
                     test_months: int = 6, step_months: int = 4) -> list[dict]:
    """5 ventanas ancladas hacia atrás desde `end_date` (la fecha más
    reciente de datos disponible), más recientes primero -> se
    reordenan cronológicamente al final. Replica "12m train / 6m test,
    paso 4m" de ADR 0033."""
    windows = []
    for i in range(n_windows):
        test_end = end_date - pd.DateOffset(months=step_months * i)
        test_start = test_end - pd.DateOffset(months=test_months)
        train_start = test_start - pd.DateOffset(months=train_months)
        windows.append({"train_start": train_start, "test_start": test_start, "test_end": test_end})
    windows.reverse()
    for i, w in enumerate(windows, start=1):
        w["window"] = i
    return windows


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    pnl_pct: float
    multiplier: float


@dataclass
class SimResult:
    equity_curve: pd.DataFrame  # columns: date, equity
    trades: list[Trade] = field(default_factory=list)


def simulate_bucket(
    universe: dict[str, pd.DataFrame],
    risk_pct: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    capital: float = 10_000.0,
    filter_fn=None,
) -> SimResult:
    """Simulación a nivel bucket (capital compartido, posiciones
    concurrentes, sizing por riesgo sobre equity ACTUAL — ADR 0012),
    desde `start` hasta `end`. `filter_fn(symbol, date, open_symbols,
    history_by_symbol) -> float en [0,1]` es el multiplicador de
    tamaño aplicado a cada entrada nueva; None = sin filtro (baseline).

    Índice por fecha ya construido por símbolo para lookup O(1)."""
    idx = {s: df.set_index("date") for s, df in universe.items()}
    all_dates = sorted({d for df in idx.values() for d in df.index if start <= d <= end})

    cash = capital
    open_positions: dict[str, dict] = {}
    trades: list[Trade] = []
    equity_rows = []

    for today in all_dates:
        # --- 1. salidas (stop trailing o signal==-1) ---
        for symbol in list(open_positions):
            if symbol not in idx or today not in idx[symbol].index:
                continue
            row = idx[symbol].loc[today]
            pos = open_positions[symbol]
            pos["stop_price"] = max(pos["stop_price"], float(row["stop_price"]))
            close = float(row["close"])
            stop_hit = close <= pos["stop_price"]
            exit_signal = int(row["signal"]) == -1
            if stop_hit or exit_signal:
                exit_price = pos["stop_price"] if stop_hit else close
                proceeds = exit_price * pos["shares"] * (1 - FRICCION_POR_LADO)
                cost_entrada = pos["entry_price"] * pos["shares"]
                cash += proceeds
                trades.append(Trade(
                    symbol=symbol, entry_date=pos["entry_date"], exit_date=str(today.date()),
                    entry_price=pos["entry_price"], exit_price=exit_price, shares=pos["shares"],
                    pnl=proceeds - cost_entrada, pnl_pct=(proceeds / cost_entrada - 1) * 100,
                    multiplier=pos["multiplier"],
                ))
                del open_positions[symbol]

        # --- equity de hoy (tras cierres, antes de nuevas entradas) ---
        valor_posiciones = sum(
            float(idx[s].loc[today]["close"]) * p["shares"]
            for s, p in open_positions.items() if today in idx[s].index
        )
        equity_now = cash + valor_posiciones

        # --- 2. entradas nuevas ---
        for symbol, df in idx.items():
            if symbol in open_positions or today not in df.index:
                continue
            row = df.loc[today]
            if int(row["signal"]) != 1:
                continue
            close = float(row["close"])
            stop_price = float(row["stop_price"])
            risk_per_share = close - stop_price
            if risk_per_share <= 0:
                continue
            risk_amount = equity_now * risk_pct
            shares = int(risk_amount // risk_per_share)
            if shares < 1:
                continue
            multiplier = 1.0
            if filter_fn is not None:
                multiplier = filter_fn(symbol, today, set(open_positions), idx)
                shares = int(shares * multiplier)
                if shares < 1:
                    continue
            entry_price = close * (1 + FRICCION_POR_LADO)
            cost = shares * entry_price
            if cost > cash:
                continue
            cash -= cost
            open_positions[symbol] = {
                "entry_date": str(today.date()), "entry_price": entry_price,
                "stop_price": stop_price, "shares": shares, "multiplier": multiplier,
            }

        valor_posiciones = sum(
            float(idx[s].loc[today]["close"]) * p["shares"]
            for s, p in open_positions.items() if today in idx[s].index
        )
        equity_rows.append({"date": today, "equity": cash + valor_posiciones})

    return SimResult(equity_curve=pd.DataFrame(equity_rows), trades=trades)


def window_metrics(sim: SimResult, test_start: pd.Timestamp, test_end: pd.Timestamp) -> dict:
    """Métricas SOLO del tramo test_start..test_end de una simulación
    que corrió desde train_start (así ya trae posiciones orgánicas
    abiertas al llegar a test_start, en vez de arrancar en cero)."""
    curve = sim.equity_curve
    seg = curve[(curve["date"] >= test_start) & (curve["date"] <= test_end)].reset_index(drop=True)
    if len(seg) < 2:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": 0}

    rets = seg["equity"].pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    return_pct = float((seg["equity"].iloc[-1] / seg["equity"].iloc[0] - 1) * 100)

    peak = seg["equity"].iloc[0]
    max_dd = 0.0
    for e in seg["equity"]:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)

    trades_in_window = [t for t in sim.trades if test_start <= pd.Timestamp(t.exit_date) <= test_end]
    return {
        "sharpe": round(sharpe, 2), "return_pct": round(return_pct, 2),
        "max_dd_pct": round(max_dd * 100, 2), "n_trades": len(trades_in_window),
        "trades": trades_in_window,
    }


def run_walkforward(bucket_key: str, filter_fn=None, n_windows: int = 5) -> list[dict]:
    cfg = BUCKETS[bucket_key]
    universe = signaled_universe(bucket_key)
    all_dates = sorted({d for df in universe.values() for d in df["date"]})
    end_date = all_dates[-1]
    windows = rolling_windows(end_date, n_windows=n_windows)

    results = []
    for w in windows:
        sim = simulate_bucket(
            universe, cfg["risk_pct"], w["train_start"], w["test_end"], filter_fn=filter_fn,
        )
        m = window_metrics(sim, w["test_start"], w["test_end"])
        m["window"] = w["window"]
        m["test_start"] = str(w["test_start"].date())
        m["test_end"] = str(w["test_end"].date())
        results.append(m)
    return results


def aggregate_sharpe(window_results: list[dict]) -> float | None:
    vals = [w["sharpe"] for w in window_results if w["sharpe"] is not None]
    return round(float(np.mean(vals)), 2) if vals else None
