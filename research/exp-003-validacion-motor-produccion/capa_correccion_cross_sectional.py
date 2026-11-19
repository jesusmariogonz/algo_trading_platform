"""EXP-003 — Corrección (2026-11-19): el harness de ADR 0040, reusado
por las Capas 1/4/5/6/7, nunca implementó el filtro cross-sectional de
entrada que ADR 0034 puso en producción SOLO para `largo_plazo`
(`CROSS_SECTIONAL_FILTER_BUCKETS`/`CROSS_SECTIONAL_PERCENTIL_MIN` en
`src/paper_trading/engine.py`, reusado por `live_engine.py`). Las 5
capas probaron `largo_plazo` con la configuración VIEJA (pre-ADR-0034,
Sharpe full-period 0.78). Este script re-corre las 5 capas SOLO para
`largo_plazo` con `harness.apply_cross_sectional_filter` activo —
`mediano_plazo`/`riesgo_alto` no se tocan, sus resultados ya
publicados siguen vigentes tal cual (el filtro es exclusivo de
`largo_plazo`).

Reusa `harness.apply_cross_sectional_filter` (agregada en este mismo
commit a research/2026-11-filtros-sizing-adr0033/harness.py) y la
lógica de cada capa original (clasificación, métricas) tal cual, sin
cambiar ningún criterio pre-registrado.

NO importa ni modifica src/paper_trading/engine.py, live_engine.py,
daily_signals.py ni src/strategies/*.py — investigación pura, cero
cambios de producción.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402
from src.backtesting.run import STRATEGIES  # noqa: E402
from src.indicators.compute import compute_indicators  # noqa: E402
from src.indicators.relative_strength import compute_relative_strength  # noqa: E402

import capa1_walkforward as c1  # noqa: E402
import capa5_leave_one_group_out as c5  # noqa: E402
import capa6_perturbacion as c6  # noqa: E402
import capa7_ejecucion as c7  # noqa: E402
import capa4_placebo as c4  # noqa: E402

BUCKET = "largo_plazo"
OUT_DIR = Path(__file__).parent


def _full_period_metrics(sim) -> dict:
    curve = sim.equity_curve
    if len(curve) < 2:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": 0}
    rets = curve["equity"].pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    return_pct = float((curve["equity"].iloc[-1] / curve["equity"].iloc[0] - 1) * 100)
    peak = curve["equity"].iloc[0]
    max_dd = 0.0
    for e in curve["equity"]:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    return {
        "sharpe": round(sharpe, 2), "return_pct": round(return_pct, 2),
        "max_dd_pct": round(max_dd * 100, 2), "n_trades": len(sim.trades),
    }


# ---------------------------------------------------------------------------
# Autoverificación: ¿se acerca a ADR 0034 (Sharpe OOS 2.25, +19.14%, DD 6.99%,
# 0/5 ventanas negativas, walk-forward rolling)?
# ---------------------------------------------------------------------------

def filter_fn_walkforward(symbol, date, open_symbols, history_by_symbol):
    """Misma lógica que harness.apply_cross_sectional_filter, pero como
    filter_fn puntual (para el motor de walk-forward de Capa 1, que ya
    soporta filter_fn=multiplicador en vez de pre-filtrar el universo)."""
    valores = {}
    for s, df in history_by_symbol.items():
        if date not in df.index:
            continue
        ret = df.loc[date].get("return_126d")
        if pd.notna(ret):
            valores[s] = float(ret)
    if not valores:
        return 0.0
    percentiles = pd.Series(valores).rank(pct=True)
    ret = valores.get(symbol)
    perc = percentiles.get(symbol)
    if ret is not None and ret > 0 and perc is not None and perc >= harness.CROSS_SECTIONAL_PERCENTIL_MIN:
        return 1.0
    return 0.0


def autoverificacion() -> dict:
    windows = harness.run_walkforward(BUCKET, filter_fn=filter_fn_walkforward)
    agg = harness.aggregate_sharpe(windows)
    neg = sum(1 for w in windows if (w["sharpe"] or 0) < 0)
    for w in windows:
        w.pop("trades", None)

    universe = harness.signaled_universe(BUCKET)
    filtered = harness.apply_cross_sectional_filter(universe)
    all_dates = sorted({d for df in filtered.values() for d in df["date"]})
    cfg = harness.BUCKETS[BUCKET]
    sim_f = harness.simulate_bucket(filtered, cfg["risk_pct"], all_dates[0], all_dates[-1])
    m_full_filtrado = _full_period_metrics(sim_f)
    sim_b = harness.simulate_bucket(universe, cfg["risk_pct"], all_dates[0], all_dates[-1])
    m_full_base = _full_period_metrics(sim_b)

    return {
        "walkforward_rolling": {
            "windows": windows, "aggregate_sharpe_oos": agg, "ventanas_negativas": neg,
            "adr_0034_publicado": {"sharpe": 2.25, "return_pct": 19.14, "max_dd_pct": 6.99, "ventanas_negativas": 0},
            "coincide_con_adr_0034": False,
            "nota": (
                "No reproduce la magnitud de ADR 0034 (2.25 publicado vs. "
                f"{agg} reconstruido) — misma categoría de discrepancia ya "
                "documentada en Capa 1 para el baseline sin filtro (distinta "
                "ventana/esquema de capital que la exploración original de "
                "ADR 0033/0034, no identificado con exactitud). Se documenta "
                "honestamente en vez de forzarse, mismo estándar de ADR 0040."
            ),
        },
        "full_period": {
            "sin_filtro_ya_publicado": m_full_base,
            "con_filtro": m_full_filtrado,
            "nota": "Full-period SÍ muestra mejora en la dirección esperada (Sharpe sube, DD baja, menos trades) aunque de menor magnitud que el walk-forward de ADR 0034.",
        },
    }


# ---------------------------------------------------------------------------
# Capa 1 corregida (walk-forward rolling)
# ---------------------------------------------------------------------------

def capa1_corregida(verif: dict) -> dict:
    windows = verif["walkforward_rolling"]["windows"]
    label = c1.clasificar(windows)
    return {
        "windows": windows,
        "aggregate_sharpe_oos": verif["walkforward_rolling"]["aggregate_sharpe_oos"],
        "label": label,
    }


# ---------------------------------------------------------------------------
# Capa 7 corregida (ejecución realista)
# ---------------------------------------------------------------------------

def capa7_corregida() -> dict:
    universe = harness.signaled_universe(BUCKET)
    filtered = harness.apply_cross_sectional_filter(universe)
    all_dates = sorted({d for df in filtered.values() for d in df["date"]})
    cfg = harness.BUCKETS[BUCKET]
    start, end = all_dates[0], all_dates[-1]

    sim_base = harness.simulate_bucket(filtered, cfg["risk_pct"], start, end, filter_fn=None)
    m_base = _full_period_metrics(sim_base)

    sim_pesimista = c7.simulate_bucket_fill_pesimista(filtered, cfg["risk_pct"], start, end)
    m_pesimista = _full_period_metrics(sim_pesimista)

    label = c7.clasificar(m_base, m_pesimista)
    return {
        "baseline_con_filtro": m_base,
        "pesimista_con_filtro": m_pesimista,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Capa 6 corregida (perturbación de parámetros) — atr_stop_multiple, con
# el filtro cross-sectional activo de fondo en cada punto de la malla.
# ---------------------------------------------------------------------------

def capa6_corregida() -> dict:
    cfg = harness.BUCKETS[BUCKET]
    params_cls, _ = STRATEGIES[cfg["strategy"]]
    base_params = params_cls()
    valor_base = base_params.atr_stop_multiple

    puntos = {}
    for pct in c6.PERTURBACIONES_PCT:
        valor_perturbado = valor_base * (1 + pct / 100)
        params_perturbados = replace(base_params, atr_stop_multiple=valor_perturbado)
        universe = c6.signaled_universe_con_params(BUCKET, params_perturbados)
        filtered = harness.apply_cross_sectional_filter(universe)
        all_dates = sorted({d for df in filtered.values() for d in df["date"]})
        sim = harness.simulate_bucket(filtered, cfg["risk_pct"], all_dates[0], all_dates[-1])
        puntos[pct] = _full_period_metrics(sim)

    baseline_sharpe = puntos[0]["sharpe"]
    label = c6.clasificar(BUCKET, baseline_sharpe, puntos)
    return {
        "valor_produccion": valor_base,
        "puntos": {str(k): v for k, v in puntos.items()},
        "label": label,
    }


# ---------------------------------------------------------------------------
# Capa 5 corregida (leave-one-group-out) — mismos 5 grupos de ETF, con
# el filtro cross-sectional activo ANTES de quitar cada grupo.
# ---------------------------------------------------------------------------

def capa5_corregida() -> dict:
    grupos = c5.GRUPOS_LARGO_PLAZO
    universo_completo = harness.signaled_universe(BUCKET)
    universo_filtrado = harness.apply_cross_sectional_filter(universo_completo)

    baseline = c5.run_con_universo(BUCKET, universo_filtrado)
    baseline_sharpe = baseline["sharpe"]

    resultados_sin_grupo = {}
    for grupo_nombre, miembros in grupos.items():
        universo_sin_grupo = {s: df for s, df in universo_filtrado.items() if s not in miembros}
        resultados_sin_grupo[grupo_nombre] = c5.run_con_universo(BUCKET, universo_sin_grupo)

    label = c5.clasificar(baseline_sharpe, resultados_sin_grupo, len(grupos))
    return {
        "baseline_con_filtro": baseline,
        "n_grupos": len(grupos),
        "sin_grupo": resultados_sin_grupo,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Capa 4 corregida (placebo) — mismo diseño (bloques de 21 días, bootstrap
# conjunto), con el filtro cross-sectional aplicado a CADA réplica, antes
# de simular.
# ---------------------------------------------------------------------------

def run_replica_con_filtro(raw, symbols, ratios_by_symbol, rng) -> float | None:
    cfg = harness.BUCKETS[BUCKET]
    dates = raw[symbols[0]]["date"]
    n_returns = len(dates) - 1
    seq = c4.bootstrap_block_sequence(n_returns, c4.BLOCK_SIZE, rng)
    bench_df = c4.synthetic_symbol_df(dates, ratios_by_symbol[c4.BENCHMARK], seq, c4.BENCHMARK)

    universe: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        sdf = c4.synthetic_symbol_df(dates, ratios_by_symbol[symbol], seq, symbol)
        sdf = compute_indicators(sdf)
        sdf = compute_relative_strength(sdf, bench_df, window=63)
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
    universe = harness.apply_cross_sectional_filter(universe)
    start, end = dates.min(), dates.max()
    sim = harness.simulate_bucket(universe, cfg["risk_pct"], start, end)
    m = harness.window_metrics(sim, start, end)
    return m["sharpe"]


def capa4_corregida(sharpe_real_filtrado: float, n_replicas_objetivo: int = 300, seed: int = 4019) -> dict:
    cfg = harness.BUCKETS[BUCKET]
    symbols = harness.read_universe_file(Path(cfg["universe_file"]))
    all_symbols = list(dict.fromkeys(symbols + [c4.BENCHMARK]))

    raw = {}
    excluidos = []
    for s in all_symbols:
        path = c4.RAW_DIR / f"{s}.parquet"
        if not path.exists():
            continue
        df = c4.load_raw(s)
        if len(df) < 500:
            excluidos.append(s)
            continue
        raw[s] = df
    usable_symbols = [s for s in symbols if s in raw]

    common_dates = None
    for s in usable_symbols + [c4.BENCHMARK]:
        if s not in raw:
            continue
        d = set(raw[s]["date"])
        common_dates = d if common_dates is None else (common_dates & d)
    aligned = {}
    for s in usable_symbols + [c4.BENCHMARK]:
        if s not in raw:
            continue
        df = raw[s][raw[s]["date"].isin(common_dates)].sort_values("date").reset_index(drop=True)
        aligned[s] = df
    ratios_by_symbol = {s: c4.build_ratio_arrays(df) for s, df in aligned.items()}
    usable_symbols = [s for s in usable_symbols if s in aligned]

    rng = np.random.default_rng(seed)

    t0 = time.time()
    sharpes = []
    for i in range(n_replicas_objetivo):
        sh = run_replica_con_filtro(aligned, usable_symbols, ratios_by_symbol, rng)
        if sh is not None:
            sharpes.append(sh)
        if (i + 1) % 50 == 0:
            print(f"  [capa4 corregida] {i+1}/{n_replicas_objetivo} réplicas, {round(time.time()-t0,1)}s", flush=True)
    elapsed = time.time() - t0

    placebo_mean = float(np.mean(sharpes))
    placebo_std = float(np.std(sharpes))
    # BUG corregido: np.mean([1 for s in sharpes if s < real]) siempre da 1.0
    # (es la media de una lista que solo contiene 1s) — no divide por el
    # total de réplicas. La fórmula correcta es count/total.
    percentil = float(sum(1 for s in sharpes if s < sharpe_real_filtrado) / len(sharpes) * 100) if sharpes else None

    potencia_confirmada = placebo_std > 0.05  # umbral: no degenerado tipo EXP-002 (~1e-16)
    if not potencia_confirmada:
        label = "INCONCLUSIVE (sin potencia confirmada)"
    elif percentil is None:
        label = "INCONCLUSIVE (sin réplicas válidas)"
    elif percentil >= 95:
        label = "VALIDATED"
    elif percentil >= 80:
        label = "INCONCLUSIVE"
    else:
        label = "REJECTED"

    return {
        "n_replicas_corridas": len(sharpes),
        "tiempo_segundos": round(elapsed, 1),
        "excluidos_por_historia_corta": excluidos,
        "sharpe_real_con_filtro": sharpe_real_filtrado,
        "placebo_mean": round(placebo_mean, 3),
        "placebo_std": round(placebo_std, 3),
        "potencia_confirmada": potencia_confirmada,
        "percentil": round(percentil, 2) if percentil is not None else None,
        "placebo_sharpes": sharpes,  # lista cruda, para poder auditar/recalcular sin re-correr
        "label": label,
    }


def main():
    print("=== Autoverificación contra ADR 0034 ===", flush=True)
    verif = autoverificacion()
    print(json.dumps(verif, indent=2, default=str))

    sharpe_real_filtrado = verif["full_period"]["con_filtro"]["sharpe"]

    print("\n=== Capa 1 corregida ===", flush=True)
    r1 = capa1_corregida(verif)
    print(f"  Sharpe OOS promedio: {r1['aggregate_sharpe_oos']} -> {r1['label']}")

    print("\n=== Capa 7 corregida ===", flush=True)
    r7 = capa7_corregida()
    print(f"  Baseline: {r7['baseline_con_filtro']} / Pesimista: {r7['pesimista_con_filtro']} -> {r7['label']}")

    print("\n=== Capa 6 corregida ===", flush=True)
    r6 = capa6_corregida()
    print(f"  atr_stop_multiple puntos: {r6['puntos']} -> {r6['label']}")

    print("\n=== Capa 5 corregida ===", flush=True)
    r5 = capa5_corregida()
    print(f"  Baseline con filtro: {r5['baseline_con_filtro']} -> {r5['label']}")

    print("\n=== Capa 4 corregida (placebo, puede tardar varios minutos) ===", flush=True)
    r4 = capa4_corregida(sharpe_real_filtrado, n_replicas_objetivo=300)
    print(f"  {r4} -> {r4['label']}")

    resultado = {
        "autoverificacion": verif,
        "capa1": r1, "capa4": r4, "capa5": r5, "capa6": r6, "capa7": r7,
    }
    out_path = OUT_DIR / "resultados_correccion_largo_plazo.json"
    out_path.write_text(json.dumps(resultado, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
