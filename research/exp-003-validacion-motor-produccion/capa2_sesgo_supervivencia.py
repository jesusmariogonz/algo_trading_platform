"""EXP-003 Capa 2 — Sesgo de supervivencia (ver PREREGISTRATION.md).

Pregunta: ¿cuánto del rendimiento reportado depende de que el
universo este elegido A MANO, hoy, con el diario de lo que ya gano?
(ver docs/roadmap.md: "corrido sobre nuestros 30 simbolos actuales que
incluyen NVDA, SMCI, AVGO, PLTR - elegidos a mano porque HOY sabemos
que fueron ganadores del rally de IA 2023-2025").

Metodo: en vez de un proveedor de datos point-in-time (no viable
gratis/rapido en este entorno), se construye un universo "neutral" de
comparacion a partir de TODOS los miembros ACTUALES del S&P 500 (lista
publica objetiva, github.com/datasets/s-and-p-500-companies), tomando
una muestra estratificada alfabetica (cada 3er simbolo de la lista
ordenada) en vez de los ~26-79 nombres elegidos a mano por bucket. Esto
NO elimina el sesgo de supervivencia completo (siguen siendo miembros
de HOY, no point-in-time de hace 5 anios) - SI elimina el sesgo de
SELECCION MANUAL adicional (elegir nombres especificos con el diario de
lo que ya gano, en vez de un corte objetivo de un indice amplio). Esta
distincion se documenta explicitamente en el resultado.

Alcance: solo mediano_plazo (trend_following) y riesgo_alto
(momentum_breakout) - son los 2 buckets de ACCIONES INDIVIDUALES donde
aplica el tipo de sesgo que roadmap.md documento (elegir nombres
especificos con hindsight). largo_plazo es un universo de ETFs de
CLASE DE ACTIVO (SPY, AGG, GLD, etc.) - elegir "que ETFs representan
cada clase de activo" no es el mismo fenomeno que elegir "que acciones
individuales ya sabemos que ganaron"; se documenta como INCONCLUSIVE
con la razon explicita, no se fuerza una comparacion de bajo valor
contra un universo neutral de ETFs.

Reusa harness (research/2026-11-filtros-sizing-adr0033/harness.py) -
mismo motor de simulacion que las demas capas. NO importa ni modifica
src/paper_trading/engine.py, live_engine.py, daily_signals.py ni
src/strategies/*.py - investigacion pura, cero cambios de produccion.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402
from src.backtesting.run import STRATEGIES, load_universe  # noqa: E402

CRITERIO = {
    "VALIDATED": "diferencia de retorno anualizado entre universo curado y neutral <= 30% relativo",
    "INCONCLUSIVE": "no se consigue un universo neutral reconstruible con esfuerzo razonable para ese tipo de sesgo",
    "REJECTED": "diferencia > 30% relativo (sesgo material; el numero de produccion es cota superior, no estimador puntual)",
}

NEUTRAL_UNIVERSE_FILE = Path(__file__).parent / "universo_neutral_sp500.txt"

BUCKETS_ACCIONES = {
    "mediano_plazo": {"strategy": "trend_following", "risk_pct": 0.02},
    "riesgo_alto": {"strategy": "momentum_breakout", "risk_pct": 0.05},
}


def read_symbols(path: Path) -> list[str]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def signaled_universe_neutral(strategy_key: str) -> dict:
    """Igual que harness.signaled_universe pero con el universo neutral
    de S&P 500 en vez del universo curado a mano del bucket."""
    symbols = read_symbols(NEUTRAL_UNIVERSE_FILE)
    params_cls, signal_fn = STRATEGIES[strategy_key]
    params = params_cls()
    universe = load_universe(symbols=symbols)
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


def full_period_metrics(sim) -> dict:
    curve = sim.equity_curve
    if len(curve) < 2:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": 0, "n_years": None, "return_anual_pct": None}

    rets = curve["equity"].pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    return_pct = float((curve["equity"].iloc[-1] / curve["equity"].iloc[0] - 1) * 100)

    n_days = (curve["date"].iloc[-1] - curve["date"].iloc[0]).days
    n_years = max(n_days / 365.25, 0.01)
    factor = curve["equity"].iloc[-1] / curve["equity"].iloc[0]
    return_anual_pct = float((factor ** (1 / n_years) - 1) * 100) if factor > 0 else None

    peak = curve["equity"].iloc[0]
    max_dd = 0.0
    for e in curve["equity"]:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)

    return {
        "sharpe": round(sharpe, 2), "return_pct": round(return_pct, 2),
        "return_anual_pct": round(return_anual_pct, 2) if return_anual_pct is not None else None,
        "max_dd_pct": round(max_dd * 100, 2), "n_trades": len(sim.trades), "n_years": round(n_years, 2),
    }


def run_full_period(universe: dict, risk_pct: float) -> dict:
    if not universe:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": 0, "n_years": None, "return_anual_pct": None}
    all_dates = sorted({d for df in universe.values() for d in df["date"]})
    sim = harness.simulate_bucket(universe, risk_pct, all_dates[0], all_dates[-1])
    return full_period_metrics(sim)


def clasificar(curado: dict, neutral: dict) -> str:
    r_curado = curado.get("return_anual_pct")
    r_neutral = neutral.get("return_anual_pct")
    if r_curado is None or r_neutral is None:
        return "INCONCLUSIVE (no se pudo calcular retorno anualizado en alguno de los 2 universos)"
    base = max(abs(r_curado), 1e-6)
    diff_pct = abs(r_curado - r_neutral) / base * 100
    label = "VALIDATED" if diff_pct <= 30 else "REJECTED"
    return f"{label} (diferencia {round(diff_pct, 1)}% relativo al retorno anualizado curado)"


def main():
    resultado = {"criterio": CRITERIO}

    neutral_symbols = read_symbols(NEUTRAL_UNIVERSE_FILE)
    print(f"Universo neutral: {len(neutral_symbols)} simbolos (muestra S&P 500 cada 3o, alfabetico)")

    for bucket_key, cfg in BUCKETS_ACCIONES.items():
        print(f"\n=== {bucket_key} ({cfg['strategy']}) ===")

        universo_curado = harness.signaled_universe(bucket_key)
        curado = run_full_period(universo_curado, cfg["risk_pct"])
        print(f"  Curado ({len(universo_curado)} simbolos con señal): Sharpe={curado['sharpe']}, "
              f"retorno total={curado['return_pct']}%, retorno anual={curado['return_anual_pct']}%, "
              f"DD={curado['max_dd_pct']}%, trades={curado['n_trades']}")

        universo_neutral = signaled_universe_neutral(cfg["strategy"])
        neutral = run_full_period(universo_neutral, cfg["risk_pct"])
        print(f"  Neutral S&P500 ({len(universo_neutral)} simbolos con señal): Sharpe={neutral['sharpe']}, "
              f"retorno total={neutral['return_pct']}%, retorno anual={neutral['return_anual_pct']}%, "
              f"DD={neutral['max_dd_pct']}%, trades={neutral['n_trades']}")

        label = clasificar(curado, neutral)
        print(f"  -> {label}")

        resultado[bucket_key] = {
            "n_simbolos_curado": len(universo_curado),
            "n_simbolos_neutral": len(universo_neutral),
            "curado": curado,
            "neutral": neutral,
            "label": label,
        }

    # largo_plazo: documentado como INCONCLUSIVE con razon explicita, sin forzar numero
    resultado["largo_plazo"] = {
        "label": "INCONCLUSIVE (tipo de sesgo no aplica de la misma forma: universo de ETFs de clase de "
                  "activo, no acciones individuales elegidas con hindsight - ver docstring del script)",
        "razon": (
            "El sesgo documentado en roadmap.md ('elegidos a mano porque HOY sabemos que fueron "
            "ganadores') describe elegir ACCIONES INDIVIDUALES especificas con el diario de lo que ya "
            "gano (NVDA, SMCI, AVGO, PLTR). El universo de largo_plazo es una lista de ETFs que "
            "representan clases de activo (SPY=equity US, AGG=bonos, GLD=oro, VNQ=REIT, etc.) - "
            "'elegir que ETF representa cada clase de activo' no es el mismo fenomeno de seleccion con "
            "hindsight que 'elegir que accion individual ya gano'. Construir un universo neutral de "
            "ETFs (ej. todos los SPDR sectoriales + todos los iShares de pais) no testearia ese tipo de "
            "sesgo, testearia una pregunta distinta (concentracion sectorial de ETFs) ya cubierta por "
            "la Capa 5. Se documenta como limitacion explicita en vez de forzar una comparacion de bajo "
            "valor informativo."
        ),
    }

    out_path = Path(__file__).parent / "resultados_capa2.json"
    out_path.write_text(json.dumps(resultado, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
