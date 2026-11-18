"""EXP-003 Capa 6 — Superficie de perturbación de parámetros (ver
PREREGISTRATION.md).

Para cada estrategia de producción, perturba sus parámetros numéricos
reales (±10%/±20%, uno a la vez, los demás fijos en su valor de
producción) y corre el backtest de bucket COMPLETO (todo el período
disponible, no walk-forward — eso ya lo hizo la Capa 1) para medir si
el Sharpe es una meseta estable o un pico aislado alrededor del valor
actual.

Reusa `simulate_bucket`/`BUCKETS`/`FRICCION_POR_LADO` del harness ya
construido para ADR 0040
(research/2026-11-filtros-sizing-adr0033/harness.py) — mismo motor de
simulación que usaron las Capas 1 y 7, para que los números sean
comparables entre capas. Ese harness siempre instancia los params de
producción POR DEFECTO (`params_cls()`); aquí se agrega una variante
de `signaled_universe` que acepta una instancia de params ya
construida con el valor perturbado, sin modificar el harness
original (que ya pasó su propia verificación en la Capa 1/7).

NO importa ni modifica src/paper_trading/engine.py, live_engine.py,
daily_signals.py ni los archivos de src/strategies/ — solo LEE sus
dataclasses de parámetros. Investigación pura, cero cambios de
producción.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402
from src.backtesting.run import STRATEGIES  # noqa: E402

CRITERIO = {
    "VALIDATED": "Sharpe dentro de +-15% de cualquier parametro no cae mas del 50% respecto al valor de produccion",
    "INCONCLUSIVE": "malla demasiado ruidosa (muy pocas operaciones) para distinguir meseta de pico",
    "REJECTED": "alguna perturbacion <=15% produce una caida de Sharpe >50%",
}

# Parametros continuos reales de cada estrategia (dataclasses en
# src/strategies/*.py) elegidos para perturbar. breakout_window de
# momentum_breakout se excluye a proposito: es un switch discreto
# (20 o 55, selecciona entre dos columnas precomputadas high_20/
# high_55), no un valor continuo perturbable en un grid +-%.
PARAMS_A_PERTURBAR = {
    "largo_plazo": ["atr_stop_multiple"],
    "mediano_plazo": ["atr_stop_multiple"],
    "riesgo_alto": [
        "atr_stop_multiple", "min_breakout_volume",
        "min_relative_strength", "max_atr_contraction",
    ],
}

PERTURBACIONES_PCT = [-20, -10, 0, 10, 20]


def signaled_universe_con_params(bucket_key: str, params) -> dict:
    """Igual que harness.signaled_universe, pero con una instancia de
    params ya construida (perturbada) en vez de params_cls() por
    defecto."""
    cfg = harness.BUCKETS[bucket_key]
    symbols = harness.read_universe_file(Path(cfg["universe_file"]))
    _, signal_fn = STRATEGIES[cfg["strategy"]]
    universe = harness.load_universe(symbols=symbols)
    out = {}
    for symbol, df in universe.items():
        try:
            sdf = signal_fn(df, params)
        except ValueError:
            continue
        sdf = sdf.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
        if sdf.empty:
            continue
        out[symbol] = sdf
    return out


def full_period_metrics(sim: "harness.SimResult") -> dict:
    """Igual que harness.window_metrics pero sobre TODA la curva de
    equity (Capa 6 no usa ventanas de walk-forward, por diseño)."""
    import numpy as np

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


def run_punto(bucket_key: str, params) -> dict:
    universe = signaled_universe_con_params(bucket_key, params)
    all_dates = sorted({d for df in universe.values() for d in df["date"]})
    cfg = harness.BUCKETS[bucket_key]
    sim = harness.simulate_bucket(
        universe, cfg["risk_pct"], all_dates[0], all_dates[-1],
    )
    return full_period_metrics(sim)


def clasificar(bucket_key: str, baseline_sharpe: float, puntos: dict) -> str:
    """Solo los puntos dentro de +-15% (aqui: +-10%, el +-20% queda
    fuera de la banda estricta del criterio y se reporta como contexto
    adicional, no decide el label) entran al criterio pre-registrado."""
    dentro_de_banda = {k: v for k, v in puntos.items() if abs(k) <= 15}
    sharpes_validos = [v["sharpe"] for v in dentro_de_banda.values() if v["sharpe"] is not None]
    trades_validos = [v["n_trades"] for v in dentro_de_banda.values()]

    if baseline_sharpe is None or baseline_sharpe == 0 or any(t < 10 for t in trades_validos):
        return "INCONCLUSIVE (malla ruidosa: <10 operaciones en algun punto dentro de +-15%)"

    for pct, v in dentro_de_banda.items():
        if v["sharpe"] is None:
            continue
        caida_pct = (baseline_sharpe - v["sharpe"]) / abs(baseline_sharpe) * 100
        if caida_pct > 50:
            return f"REJECTED (perturbacion {pct:+d}% produce caida de {round(caida_pct, 1)}% en Sharpe)"
    return "VALIDATED"


def main():
    resultado = {}
    for bucket_key, param_names in PARAMS_A_PERTURBAR.items():
        cfg = harness.BUCKETS[bucket_key]
        params_cls, _ = STRATEGIES[cfg["strategy"]]
        base_params = params_cls()

        print(f"\n=== {bucket_key} ({cfg['strategy']}) ===")
        resultado[bucket_key] = {}
        for pname in param_names:
            valor_base = getattr(base_params, pname)
            puntos = {}
            for pct in PERTURBACIONES_PCT:
                valor_perturbado = valor_base * (1 + pct / 100)
                params_perturbados = replace(base_params, **{pname: valor_perturbado})
                m = run_punto(bucket_key, params_perturbados)
                puntos[pct] = m
                print(f"  {pname} {pct:+d}% (={round(valor_perturbado, 4)}): "
                      f"Sharpe={m['sharpe']}, retorno={m['return_pct']}%, "
                      f"DD={m['max_dd_pct']}%, trades={m['n_trades']}")

            baseline_sharpe = puntos[0]["sharpe"]
            label = clasificar(bucket_key, baseline_sharpe, puntos)
            print(f"  -> {pname}: {label}")
            resultado[bucket_key][pname] = {
                "valor_produccion": valor_base,
                "puntos": {str(k): v for k, v in puntos.items()},
                "label": label,
            }

    out_path = Path(__file__).parent / "resultados_capa6.json"
    out_path.write_text(json.dumps({"criterio": CRITERIO, "resultado": resultado}, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
