"""EXP-003 — Capa 4: Placebo con potencia verificada.

Ver `PREREGISTRATION.md` sección "Capa 4" — criterio fijado ANTES de
correr esto, no se cambia aquí.

Lección de EXP-002 (pulso-research-lab): un placebo de rotación
circular sobre una estadística invariante al orden (CAGR vía producto)
tuvo potencia estadística CERO. Estas 3 estrategias de producción SÍ
dependen del orden temporal (trailing stop, entradas/salidas
secuenciales) — pero hay que CONFIRMARLO, no asumirlo, calculando la
varianza del Sharpe entre réplicas placebo antes de mirar el
percentil.

Método: block-bootstrap MÓVIL (moving block bootstrap) de los
retornos diarios crudos (`data/raw/<symbol>.parquet`, antes de
cualquier indicador), con tamaño de bloque de 21 sesiones (~1 mes de
trading — suficiente para preservar la autocorrelación de corto plazo
típica de retornos diarios de renta variable, que se disipa en pocas
semanas). El mismo calendario de bloques (misma secuencia de índices
de retorno) se aplica a TODOS los símbolos del universo de un bucket
Y al benchmark (SPY) en una réplica dada — bootstrap conjunto, no
independiente por símbolo, para preservar la estructura cross-
seccional dentro de cada bloque (si no, la relative_strength de
`momentum_breakout` perdería sentido). Desde los retornos
bootstrapeados se reconstruye un panel OHLCV sintético completo
(close, high, low vía su razón histórica contra el close del día
anterior; volumen pasa igual, día por día, junto con el bloque), se
recalculan TODOS los indicadores desde cero (`compute_indicators`,
`compute_relative_strength` — las mismas funciones de producción,
nunca reimplementadas) y se vuelve a correr la estrategia completa de
producción (`generate_signals` de `src/strategies/*.py`) y el motor de
simulación (`simulate_bucket` de
`research/2026-11-filtros-sizing-adr0033/harness.py`, reusado sin
modificar) sobre ese universo sintético.

NO IMPORTA ni modifica engine.py/live_engine.py/daily_signals.py ni
los archivos de src/strategies/ (solo los usa). Código 100%
versionado (ADR 0041), nunca gitignored.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))

from src.backtesting.run import STRATEGIES  # noqa: E402
from src.indicators.compute import compute_indicators  # noqa: E402
from src.indicators.relative_strength import compute_relative_strength  # noqa: E402
from harness import BUCKETS, read_universe_file, simulate_bucket, window_metrics  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
BLOCK_SIZE = 21  # ~1 mes de trading, elección documentada arriba
BENCHMARK = "SPY"


def load_raw(symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(RAW_DIR / f"{symbol}.parquet")
    return df.sort_values("date").reset_index(drop=True)


def build_ratio_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Razones día-a-día (retorno simple) de cada columna de precio
    relativas al CLOSE del día anterior — longitud N-1, índice j
    corresponde al retorno real de los días (j, j+1)."""
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    adj = df["adj_close"].to_numpy()
    vol = df["volume"].to_numpy()
    return {
        "ratio_close": close[1:] / close[:-1],
        "ratio_high": high[1:] / close[:-1],
        "ratio_low": low[1:] / close[:-1],
        "ratio_adj": adj[1:] / adj[:-1],
        "vol": vol,  # longitud N, vol[i] es el volumen real del día i
        "close0": close[0],
        "adj0": adj[0],
        "high0": high[0],
        "low0": low[0],
    }


def bootstrap_block_sequence(n_returns: int, block_size: int, rng: np.random.Generator) -> np.ndarray:
    """Moving block bootstrap: bloques de tamaño `block_size`
    muestreados con reemplazo de los índices de retorno originales
    [0, n_returns-1], concatenados y recortados a longitud n_returns."""
    n_blocks = -(-n_returns // block_size)
    max_start = n_returns - block_size
    starts = rng.integers(0, max_start + 1, size=n_blocks)
    seq = np.concatenate([np.arange(s, s + block_size) for s in starts])
    return seq[:n_returns]


def synthetic_symbol_df(dates: pd.Series, ratios: dict, seq: np.ndarray, symbol: str) -> pd.DataFrame:
    """Reconstruye un panel OHLCV sintético de longitud len(dates) a
    partir de las razones originales re-ordenadas según `seq` (la
    misma secuencia de bloques para todos los símbolos de la réplica).
    """
    n = len(dates)
    rc = ratios["ratio_close"][seq]
    rh = ratios["ratio_high"][seq]
    rl = ratios["ratio_low"][seq]
    ra = ratios["ratio_adj"][seq]

    close = ratios["close0"] * np.concatenate([[1.0], np.cumprod(rc)])
    adj_close = ratios["adj0"] * np.concatenate([[1.0], np.cumprod(ra)])
    high = np.empty(n)
    low = np.empty(n)
    high[0], low[0] = ratios["high0"], ratios["low0"]
    high[1:] = close[:-1] * rh
    low[1:] = close[:-1] * rl
    # Volumen real del día "destino" de cada retorno reproducido —
    # pasa junto con el bloque (preserva la relación volumen/retorno
    # dentro de cada bloque, no se inventa).
    vol = np.concatenate([[ratios["vol"][0]], ratios["vol"][seq + 1]])

    return pd.DataFrame({
        "date": dates.to_numpy(), "symbol": symbol,
        "open": close, "high": high, "low": low, "close": close,
        "adj_close": adj_close, "volume": vol,
    })


def run_replica(bucket_key: str, raw: dict[str, pd.DataFrame], symbols: list[str],
                 ratios_by_symbol: dict[str, dict], rng: np.random.Generator) -> float | None:
    cfg = BUCKETS[bucket_key]
    dates = raw[symbols[0]]["date"]
    n_returns = len(dates) - 1
    seq = bootstrap_block_sequence(n_returns, BLOCK_SIZE, rng)  # UNA secuencia, compartida

    bench_df = synthetic_symbol_df(dates, ratios_by_symbol[BENCHMARK], seq, BENCHMARK)

    universe: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        sdf = synthetic_symbol_df(dates, ratios_by_symbol[symbol], seq, symbol)
        sdf = compute_indicators(sdf)
        sdf = compute_relative_strength(sdf, bench_df if symbol != BENCHMARK else bench_df, window=63)
        params_cls, signal_fn = STRATEGIES[cfg["strategy"]]
        try:
            sdf = signal_fn(sdf, params_cls())
        except (ValueError, KeyError):
            continue
        sdf = sdf.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
        if sdf.empty:
            continue
        universe[symbol] = sdf

    if not universe:
        return None
    start, end = dates.min(), dates.max()
    sim = simulate_bucket(universe, cfg["risk_pct"], start, end)
    m = window_metrics(sim, start, end)
    return m["sharpe"]


def calibrate_and_run(bucket_key: str, target_replicas: int, time_budget_s: float, seed: int) -> dict:
    cfg = BUCKETS[bucket_key]
    symbols = read_universe_file(Path(cfg["universe_file"]))
    all_symbols = list(dict.fromkeys(symbols + [BENCHMARK]))

    MIN_RAW_ROWS = 500  # ~2 años — por debajo de esto, un solo símbolo
    # roto o muy reciente (ej. ROKU con 2 filas de datos corruptos,
    # WOLF con 287 por ser un agregado reciente al universo) acota el
    # calendario común de TODO el bucket a casi nada si se le deja
    # entrar a la intersección — se excluye el símbolo, no se acorta
    # la muestra de los demás.
    raw = {}
    excluidos_por_historia_corta = []
    for s in all_symbols:
        path = RAW_DIR / f"{s}.parquet"
        if not path.exists():
            continue
        df = load_raw(s)
        if len(df) < MIN_RAW_ROWS:
            excluidos_por_historia_corta.append({"symbol": s, "filas": len(df)})
            continue
        raw[s] = df
    missing = [s for s in all_symbols if s not in raw]
    usable_symbols = [s for s in symbols if s in raw]

    # Calendario común (intersección) entre todos los símbolos usables + benchmark.
    common_dates = None
    for s in usable_symbols + [BENCHMARK]:
        if s not in raw:
            continue
        d = set(raw[s]["date"])
        common_dates = d if common_dates is None else (common_dates & d)
    aligned = {}
    for s in usable_symbols + [BENCHMARK]:
        if s not in raw:
            continue
        df = raw[s][raw[s]["date"].isin(common_dates)].sort_values("date").reset_index(drop=True)
        aligned[s] = df
    ratios_by_symbol = {s: build_ratio_arrays(df) for s, df in aligned.items()}
    usable_symbols = [s for s in usable_symbols if s in aligned]

    rng = np.random.default_rng(seed)

    # --- Calibración de tiempo: 5 réplicas reales, se cronometran ---
    t0 = time.time()
    calib_sharpes = []
    for _ in range(5):
        sh = run_replica(bucket_key, aligned, usable_symbols, ratios_by_symbol, rng)
        if sh is not None:
            calib_sharpes.append(sh)
    t_calib = time.time() - t0
    per_replica_s = t_calib / 5

    n_feasible = max(5, int(time_budget_s / per_replica_s)) if per_replica_s > 0 else target_replicas
    n_run = min(target_replicas, n_feasible)

    sharpes = list(calib_sharpes)
    t1 = time.time()
    for _ in range(max(0, n_run - 5)):
        sh = run_replica(bucket_key, aligned, usable_symbols, ratios_by_symbol, rng)
        if sh is not None:
            sharpes.append(sh)
    elapsed_total = (time.time() - t1) + t_calib

    return {
        "bucket": bucket_key,
        "n_symbols_universo": len(symbols),
        "n_symbols_usables": len(usable_symbols),
        "symbols_faltantes": missing,
        "excluidos_por_historia_corta": excluidos_por_historia_corta,
        "n_dias_comunes": len(common_dates) if common_dates else 0,
        "per_replica_seconds": round(per_replica_s, 3),
        "target_replicas": target_replicas,
        "n_replicas_corridas": len(sharpes),
        "tiempo_total_segundos": round(elapsed_total, 1),
        "placebo_sharpes": sharpes,
    }


def main():
    out_dir = Path(__file__).parent
    resultados = {}
    # Presupuesto de tiempo por bucket, calibrado empíricamente abajo
    # tras la primera corrida de 5 réplicas de cada bucket — ver
    # CAPA-4-placebo.md para la justificación real con números.
    TIME_BUDGET_S = 900  # 15 min por bucket, documentado si limita N
    for i, bucket_key in enumerate(BUCKETS):
        print(f"=== {bucket_key} ===", flush=True)
        res = calibrate_and_run(bucket_key, target_replicas=1000, time_budget_s=TIME_BUDGET_S, seed=1000 + i)
        print(
            f"  {res['n_replicas_corridas']} réplicas, "
            f"{res['per_replica_seconds']}s/réplica, "
            f"{res['tiempo_total_segundos']}s total", flush=True,
        )
        resultados[bucket_key] = res

    out_path = out_dir / "resultados_capa4.json"
    out_path.write_text(json.dumps(resultados, indent=2, default=str))
    print(f"Guardado en {out_path}")


if __name__ == "__main__":
    main()
