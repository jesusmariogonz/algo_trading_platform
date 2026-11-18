"""EXP-003 Capa 1 — Walk-forward rolling baseline (ver PREREGISTRATION.md).

Corre las 3 estrategias de producción, SIN ningún filtro (baseline
exacto de hoy), sobre el harness rolling ya construido para ADR 0040
(research/2026-11-filtros-sizing-adr0033/harness.py — 5 ventanas, 12m
train/6m test, paso 4 meses). No reimplementa el motor de simulación,
solo lo invoca con filter_fn=None y aplica el criterio YA fijado en el
pre-registro.

NO importa ni modifica src/paper_trading/engine.py, live_engine.py ni
daily_signals.py — investigación pura, cero cambios de producción.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402

CRITERIO = {
    "VALIDATED": ">=4/5 ventanas con Sharpe OOS>0 Y ninguna ventana aporta >60% del retorno compuesto",
    "INCONCLUSIVE": "exactamente 3/5 ventanas positivas, o alguna ventana con <10 operaciones",
    "REJECTED": "<=2/5 ventanas con Sharpe OOS>0",
}


def retorno_compuesto_por_ventana(windows: list[dict]) -> list[float]:
    """Factor de crecimiento (1+retorno) de cada ventana, para medir
    qué fracción del retorno TOTAL compuesto aporta cada una."""
    return [1 + (w["return_pct"] or 0.0) / 100 for w in windows]


def aporte_maximo_de_una_ventana(windows: list[dict]) -> float:
    """% que representa la ventana de mayor retorno sobre el log del
    crecimiento compuesto total (evita que una sola ventana explique
    todo el resultado). Si el total es <=0 (producto <=1), se reporta
    None — "% del retorno" no es una medida sensata cuando no hubo
    retorno neto positivo que repartir entre ventanas."""
    factores = retorno_compuesto_por_ventana(windows)
    log_total = sum(__import__("math").log(f) for f in factores if f > 0)
    if log_total <= 0:
        return None
    log_contribs = [__import__("math").log(f) if f > 0 else 0.0 for f in factores]
    return round(max(log_contribs) / log_total * 100, 2)


def clasificar(windows: list[dict]) -> str:
    sharpes = [w["sharpe"] for w in windows]
    ventanas_positivas = sum(1 for s in sharpes if s is not None and s > 0)
    alguna_con_pocos_trades = any((w["n_trades"] or 0) < 10 for w in windows)

    if alguna_con_pocos_trades:
        return "INCONCLUSIVE (ventana con <10 operaciones)"
    if ventanas_positivas == 3:
        return "INCONCLUSIVE (exactamente 3/5 ventanas positivas)"
    if ventanas_positivas >= 4:
        aporte_max = aporte_maximo_de_una_ventana(windows)
        if aporte_max is not None and aporte_max > 60:
            return f"INCONCLUSIVE (>=4/5 positivas pero una ventana aporta {aporte_max}% del retorno compuesto)"
        return "VALIDATED"
    return "REJECTED"


def main():
    resultado = {}
    for bucket in harness.BUCKETS:
        windows = harness.run_walkforward(bucket, filter_fn=None)
        for w in windows:
            w.pop("trades", None)  # no serializar objetos Trade crudos en el resumen
        label = clasificar(windows)
        agg_sharpe = harness.aggregate_sharpe(windows)
        resultado[bucket] = {
            "windows": windows,
            "aggregate_sharpe_oos": agg_sharpe,
            "ventanas_positivas": sum(1 for w in windows if (w["sharpe"] or 0) > 0),
            "label": label,
        }
        print(f"\n=== {bucket} ===")
        for w in windows:
            print(f"  Ventana {w['window']} [{w['test_start']} -> {w['test_end']}]: "
                  f"Sharpe={w['sharpe']}, retorno={w['return_pct']}%, DD={w['max_dd_pct']}%, "
                  f"trades={w['n_trades']}")
        print(f"  Sharpe OOS promedio: {agg_sharpe} -> {label}")

    out_path = Path(__file__).parent / "resultados_capa1.json"
    out_path.write_text(json.dumps({"criterio": CRITERIO, "resultado": resultado}, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
