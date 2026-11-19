"""EXP-003 — Capa 3: Deflated Sharpe Ratio + PBO sobre el espacio de
búsqueda histórico documentado en docs/adr/0001-0043.

ADVERTENCIA METODOLÓGICA CRÍTICA (leer antes de usar los números de
esta capa): el harness compartido de EXP-003
(research/2026-11-filtros-sizing-adr0033/harness.py) reproduce
`largo_plazo` SOLO con `time_series_momentum` puro — NO incluye el
filtro de cross-sectional momentum que ADR 0034 puso en producción
real (`CROSS_SECTIONAL_FILTER_BUCKETS = {"largo_plazo"}` en
src/paper_trading/engine.py, confirmado leyendo el código fuente
actual). Esto significa que el Sharpe 0.78 usado como "baseline de
producción" de largo_plazo en TODAS las capas de EXP-003 (1, 4, 5, 6,
7, y esta) NO es la configuración real que corre en producción hoy —
es la estrategia ANTES de ADR 0034. El propio ADR 0034 reporta el
Sharpe real walk-forward de la configuración CON el filtro: 2.25 (OOS
prom., std 1.43), muy distinto de 0.78. Esta capa calcula DSR con
AMBOS números para largo_plazo, explícitamente, en vez de elegir uno
y esconder el otro — ver sección final del reporte.

Catálogo de N=47 configuraciones materialmente distintas, medidas con
Sharpe o retorno comparable, documentadas en docs/adr/ — lista
completa y auditable en CATALOGO_VARIANTES abajo.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))

from harness import BUCKETS, signaled_universe, simulate_bucket  # noqa: E402

RESULT_DIR = Path(__file__).resolve().parent
EULER_MASCHERONI = 0.5772156649015329

# ---------------------------------------------------------------------------
# Catálogo de variantes (Paso 1) — cada entrada es una configuración
# materialmente distinta con Sharpe/retorno medido y reportado en un ADR.
# No se cuentan dos veces las mismas variantes descritas en ADRs
# distintos (ej. ADR 0015/0016 son re-mediciones de la MISMA config de
# producción en distintos momentos, no variantes nuevas — no se listan
# aquí como entradas propias).
# ---------------------------------------------------------------------------
CATALOGO_VARIANTES = [
    # Grupo A — Bucket cripto / reparto de capital (ADR 0004/0006): 4
    {"id": 1, "adr": "0004/0006", "desc": "Bucket cripto (Trend Following + Momentum/Breakout sobre universo BTC/ETH/SOL/...)", "sharpe": None},
    {"id": 2, "adr": "0006", "desc": "Reparto sin cripto, proporcional (44.4/33.3/22.3)", "sharpe": None},
    {"id": 3, "adr": "0006", "desc": "Reparto sin cripto, todo al mejor bucket", "sharpe": None},
    {"id": 4, "adr": "0006", "desc": "Reparto sin cripto, equitativo (43.33/33.33/23.33) — CHOSEN, split de producción", "sharpe": None},
    # Grupo B — Mecánica del motor (ADR 0007): 3
    {"id": 5, "adr": "0007", "desc": "Trailing stop vs. stop fijo (3 buckets) — CHOSEN", "sharpe": None},
    {"id": 6, "adr": "0007", "desc": "Trailing stop en bucket cripto (ya eliminado) — descartado", "sharpe": None},
    {"id": 7, "adr": "0007", "desc": "Cash ocioso invertido en SPY vs. cash parado — CHOSEN", "sharpe": None},
    # Grupo C — Expansión de universo (ADR 0010): 4
    {"id": 8, "adr": "0010", "desc": "Universo ampliado paso 1 (75 símbolos)", "sharpe": None},
    {"id": 9, "adr": "0010", "desc": "Universo ampliado paso 2 (117 símbolos) — chosen en su momento, luego ampliado más (ADR 0011/0016)", "sharpe": None},
    {"id": 10, "adr": "0010", "desc": "Trailing stop ATR 3.0x en Riesgo Alto — descartado", "sharpe": None},
    {"id": 11, "adr": "0010", "desc": "Filtro de régimen (SMA200) para cash-en-benchmark — descartado", "sharpe": None},
    # Grupo D — Riesgo Alto + fricción (ADR 0011): 1
    {"id": 12, "adr": "0011", "desc": "Riesgo Alto ampliado a 45 símbolos + fricción real en el motor — CHOSEN", "sharpe": None},
    # Grupo E — Riesgo% + sizing (ADR 0012): 3
    {"id": 13, "adr": "0012", "desc": "Riesgo 2%/2%/3% + sizing sobre equity actual — CHOSEN", "sharpe": None},
    {"id": 14, "adr": "0012", "desc": "Blend 50% SPY / 50% AGG como cash holder — descartado", "sharpe": None},
    {"id": 15, "adr": "0012", "desc": "SGOV (casi-cash) como cash holder — descartado", "sharpe": None},
    # Grupo F — Semis/defensa + oro (ADR 0013): 2
    {"id": 16, "adr": "0013", "desc": "+ Semiconductores/Defensa (TSM/SMH/GD/NOC/LHX) — descartado", "sharpe": None},
    {"id": 17, "adr": "0013", "desc": "100% GLD como cash holder (extremo, antes del blend 50/50) — superseded por ADR 0014", "sharpe": None},
    # Grupo G — Largo Plazo expansión (ADR 0016): 1
    {"id": 18, "adr": "0016", "desc": "Largo Plazo ampliado a 26 ETFs — CHOSEN, universo de producción actual", "sharpe": None},
    # Grupo H — Donchian + Risk Parity (ADR 0018): 2
    {"id": 19, "adr": "0018", "desc": "+ Donchian Breakout (3ra estrategia en Mediano/Riesgo Alto) — descartado", "sharpe": None},
    {"id": 20, "adr": "0018", "desc": "Risk Parity / volatilidad inversa (re-ponderación mensual) — descartado", "sharpe": None},
    # Grupo I — Mean Reversion RSI(2) (ADR 0019/0026/0027): 5
    {"id": 21, "adr": "0019", "desc": "Mean Reversion RSI(2) aislado, capital propio — removido en ADR 0027", "sharpe": 0.67},
    {"id": 22, "adr": "0019", "desc": "Mean Reversion RSI(2) @ 15% del capital", "sharpe": None},
    {"id": 23, "adr": "0019", "desc": "Mean Reversion RSI(2) @ 25% del capital", "sharpe": None},
    {"id": 24, "adr": "0019", "desc": "Mean Reversion RSI(2) @ 35% del capital — fue producción real nov 1-5", "sharpe": None},
    {"id": 25, "adr": "0019", "desc": "Mean Reversion RSI(2) @ 50% del capital", "sharpe": None},
    # Grupo J — Barrido exploratorio de 10 estrategias nuevas (ADR 0025)
    {"id": 26, "adr": "0025", "desc": "Reversión a la media (Bollinger %B) — descartado tras walk-forward", "sharpe": 2.04},
    {"id": 27, "adr": "0025", "desc": "Breakout + filtro ADX — descartado", "sharpe": 1.52},
    {"id": 28, "adr": "0025", "desc": "Señal de volumen (OBV) — descartado", "sharpe": 1.31},
    {"id": 29, "adr": "0025", "desc": "Breakout de volatilidad (squeeze) — descartado", "sharpe": 0.87},
    {"id": 30, "adr": "0025", "desc": "ML (Gradient Boosting) — descartado, overfitting confirmado", "sharpe": 1.96},
    {"id": 31, "adr": "0025", "desc": "Volatility targeting sobre trend_following — descartado", "sharpe": 0.71},
    {"id": 32, "adr": "0025", "desc": "Rotación cross-sectional / Dual momentum — descartado", "sharpe": 0.42},
    {"id": 33, "adr": "0025", "desc": "Ensemble (2 de 3 señales) — descartado", "sharpe": 0.28},
    {"id": 34, "adr": "0025", "desc": "Pairs trading (V/MA) — descartado", "sharpe": 0.28},
    {"id": 35, "adr": "0025", "desc": "Estacionalidad fin de mes — descartado", "sharpe": -0.04},
    # Grupo K — ADR 0033, 10 hipótesis de filtros de sizing/entrada
    {"id": 36, "adr": "0033", "desc": "#1 Vol-regime sizing — descartado", "sharpe": None},
    {"id": 37, "adr": "0033", "desc": "#2 Correlation-adjusted sizing (largo_plazo) — candidato pendiente", "sharpe": 2.00},
    {"id": 38, "adr": "0033/0034", "desc": "#3 Cross-sectional momentum (largo_plazo) — IMPLEMENTADO en producción", "sharpe": 2.25},
    {"id": 39, "adr": "0033", "desc": "#4 Market breadth — no implementado", "sharpe": None},
    {"id": 40, "adr": "0033", "desc": "#5 Trend efficiency ratio (mediano_plazo) — candidato pendiente", "sharpe": 1.75},
    {"id": 41, "adr": "0033", "desc": "#5 Trend efficiency ratio (riesgo_alto) — rompe el bucket", "sharpe": 0.42},
    {"id": 42, "adr": "0033", "desc": "#6 Momentum acceleration — descartado, no se construyó filtro", "sharpe": None},
    {"id": 43, "adr": "0033", "desc": "#7 Residual momentum (largo_plazo) — descartado", "sharpe": None},
    {"id": 44, "adr": "0033", "desc": "#8 Proximidad a máximo 52 semanas — descartado, efecto invertido", "sharpe": None},
    {"id": 45, "adr": "0033", "desc": "#9 Lead/lag entre señales — descartado, correlación espuria", "sharpe": None},
    {"id": 46, "adr": "0033", "desc": "#10 Meta-modelo ML trade-level — descartado, overfitting confirmado", "sharpe": None},
    # Grupo L — ADR 0040, swaps estrategia×universo no probados antes
    {"id": 47, "adr": "0040", "desc": "trend_following × universo riesgo_alto (swap, aislar estrategia de universo)", "sharpe": None},
]

assert len(CATALOGO_VARIANTES) == 47, f"N esperado 47, encontrado {len(CATALOGO_VARIANTES)}"

SHARPE_MUESTRA_EMPIRICA = [v["sharpe"] for v in CATALOGO_VARIANTES if v["sharpe"] is not None]
# Agrega el baseline de largo_plazo (1.33, ADR 0033/0034) como punto de
# referencia de la MISMA tabla de donde salen 2.00/2.25 — no es una
# variante nueva (es el control), pero sí es parte de la MUESTRA de
# Sharpes observados en ese ejercicio de búsqueda, necesaria para que
# sigma_SR no esté sesgada hacia solo los "ganadores" reportados.
SHARPE_MUESTRA_EMPIRICA.append(1.33)
SHARPE_MUESTRA_EMPIRICA.append(0.96)  # baseline mediano_plazo/trend_following, ADR 0033 #5
SHARPE_MUESTRA_EMPIRICA.append(1.49)  # baseline riesgo_alto/momentum_breakout, ADR 0033 #5


def deflated_sharpe_ratio(sr_hat: float, sigma_sr_hat: float, n_trials: int, sigma_sr_trials: float) -> dict:
    """Bailey & Lopez de Prado (2014). Devuelve SR_0 (máximo esperado
    por azar), el z-score, y DSR = Phi(z) (probabilidad de que sr_hat
    sea genuinamente mejor que el máximo esperado de n_trials intentos
    con dispersión sigma_sr_trials)."""
    z1 = sp_stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = sp_stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    sr_0 = sigma_sr_trials * ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)
    z = (sr_hat - sr_0) / sigma_sr_hat if sigma_sr_hat > 0 else float("nan")
    dsr = sp_stats.norm.cdf(z)
    return {"sr_0_esperado_por_azar": round(sr_0, 4), "z": round(z, 4), "dsr": round(dsr, 4)}


def sharpe_std_error(sr_hat: float, t_obs: int, skew: float, kurt_exc: float) -> float:
    """Error estándar del Sharpe estimado (misma fórmula que el
    appendix de EXP-002: ajusta por asimetría y curtosis en exceso de
    los retornos usados para estimar sr_hat)."""
    inside = 1 - skew * sr_hat + ((kurt_exc + 3 - 1) / 4) * sr_hat**2
    return math.sqrt(max(inside, 1e-9) / (t_obs - 1))


def daily_returns_de_bucket(bucket_key: str) -> tuple[pd.Series, float, int]:
    """Corre el baseline SIN filtros (mismo harness ya usado en Capas
    1/4/5/6/7) y devuelve (retornos diarios, Sharpe anualizado, T)."""
    cfg = BUCKETS[bucket_key]
    universe = signaled_universe(bucket_key)
    all_dates = sorted({d for df in universe.values() for d in df["date"]})
    start, end = all_dates[0], all_dates[-1]
    result = simulate_bucket(universe, cfg["risk_pct"], start, end, filter_fn=None)
    eq = result.equity_curve.set_index("date")["equity"]
    rets = eq.pct_change().dropna()
    sharpe_anual = rets.mean() / rets.std() * math.sqrt(252) if rets.std() > 0 else 0.0
    return rets, float(sharpe_anual), len(rets)


def main() -> dict:
    sigma_sr_trials = float(np.std(SHARPE_MUESTRA_EMPIRICA, ddof=1))
    print(f"N trials catalogados: {len(CATALOGO_VARIANTES)}")
    print(f"Muestra empírica de Sharpe (n={len(SHARPE_MUESTRA_EMPIRICA)}): {SHARPE_MUESTRA_EMPIRICA}")
    print(f"sigma_SR (dispersión de Sharpe entre trials): {sigma_sr_trials:.4f}")

    salida = {
        "n_trials": len(CATALOGO_VARIANTES),
        "sigma_sr_trials": round(sigma_sr_trials, 4),
        "muestra_empirica_sharpe": SHARPE_MUESTRA_EMPIRICA,
        "buckets": {},
    }

    for bucket_key in ["largo_plazo", "mediano_plazo", "riesgo_alto"]:
        rets, sharpe_reconstruido, t_obs = daily_returns_de_bucket(bucket_key)
        skew = float(sp_stats.skew(rets))
        kurt_exc = float(sp_stats.kurtosis(rets))  # ya en exceso (Fisher) por default en scipy

        sigma_sr_hat = sharpe_std_error(sharpe_reconstruido, t_obs, skew, kurt_exc)
        dsr_resultado = deflated_sharpe_ratio(sharpe_reconstruido, sigma_sr_hat, len(CATALOGO_VARIANTES), sigma_sr_trials)

        print(f"\n--- {bucket_key} ---")
        print(f"Sharpe (harness, SIN filtros ADR 0034) = {sharpe_reconstruido:.4f}, T={t_obs}, skew={skew:.4f}, kurt_exc={kurt_exc:.4f}")
        print(f"sigma_SR_hat = {sigma_sr_hat:.4f}")
        print(f"DSR = {dsr_resultado}")

        entrada = {
            "sharpe_harness_sin_filtro_adr0034": round(sharpe_reconstruido, 4),
            "t_obs": t_obs,
            "skew": round(skew, 4),
            "kurt_exceso": round(kurt_exc, 4),
            "sigma_sr_hat": round(sigma_sr_hat, 4),
            **dsr_resultado,
        }

        if bucket_key == "largo_plazo":
            # Segundo cálculo con el Sharpe REAL de producción (CON el
            # filtro de ADR 0034), usando la misma T/skew/kurt como
            # aproximación razonable (no se tiene la serie de retornos
            # exacta con el filtro aplicado en este harness) — declarado
            # explícitamente como aproximación.
            sharpe_real_prod = 2.25
            sigma_sr_hat_real = sharpe_std_error(sharpe_real_prod, t_obs, skew, kurt_exc)
            dsr_real = deflated_sharpe_ratio(sharpe_real_prod, sigma_sr_hat_real, len(CATALOGO_VARIANTES), sigma_sr_trials)
            entrada["sharpe_real_produccion_con_filtro_adr0034"] = sharpe_real_prod
            entrada["dsr_con_sharpe_real_produccion"] = dsr_real
            print(f"[AJUSTE] DSR con Sharpe REAL de producción (2.25, ADR 0034) = {dsr_real}")

        salida["buckets"][bucket_key] = entrada

    out_path = RESULT_DIR / "resultados_capa3_dsr.json"
    out_path.write_text(json.dumps(salida, indent=2, ensure_ascii=False))
    print(f"\nGuardado en {out_path}")
    return salida


if __name__ == "__main__":
    main()
