"""EXP-003 Capa 5 — Cross-sectional leave-one-group-out (ver
PREREGISTRATION.md).

Pregunta: ¿el resultado de cada bucket sobrevive si se le quita
cualquier grupo de símbolos correlacionados (sector/clase de activo),
o depende de que ese grupo específico esté adentro?

Método: agrupa el universo de cada bucket por sector/clase de activo
(ver GRUPOS abajo — criterio documentado inline, complementa la
clasificación gruesa de src/portfolio/asset_types.py con sectores
GICS aproximados a mano para los universos de acciones individuales,
donde esa clasificación gruesa cae casi todo en "Stock" y no sirve
para distinguir grupos). Para cada bucket, construye el universo
completo UNA vez (`harness.signaled_universe`, params de producción
por defecto) y, para cada grupo, re-corre `simulate_bucket` sobre el
mismo universo MENOS los símbolos de ese grupo — nunca recalcula
señales por símbolo (relative_strength_63, sma_200, atr_14 son todas
métricas calculadas por símbolo contra SPY/su propio historial, no
contra el resto del universo del bucket, así que quitar otros
símbolos no cambia la señal de los que quedan).

Reusa `simulate_bucket`/`BUCKETS`/`FRICCION_POR_LADO` del harness ya
construido para ADR 0040
(research/2026-11-filtros-sizing-adr0033/harness.py) — mismo motor de
simulación que las Capas 1/6/7, para que los números sean comparables
entre capas.

NO importa ni modifica src/paper_trading/engine.py, live_engine.py,
daily_signals.py, src/strategies/*.py ni src/portfolio/asset_types.py
— solo LEE/usa esos módulos. Investigación pura, cero cambios de
producción.
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

CRITERIO = {
    "VALIDATED": "Sharpe sin NINGUN grupo individual cae mas del 40% respecto al universo completo",
    "INCONCLUSIVE": "el universo queda con menos de 3 grupos distinguibles",
    "REJECTED": "quitar algun grupo individual hace caer el Sharpe >40% o lo vuelve negativo",
}

# Grupos por bucket. largo_plazo: clase de activo (ya es la unidad
# natural para un universo de ETFs). mediano_plazo/riesgo_alto:
# sector GICS aproximado a mano (acciones individuales + ETFs
# sectoriales correspondientes agrupados con su sector real, ej. XLF
# con los bancos) — asset_types.py es demasiado grueso para esto (casi
# todo cae en "Stock" por default), así que se construye aparte, no se
# reusa ese módulo.

GRUPOS_LARGO_PLAZO = {
    "US_Equity": ["SPY", "QQQ", "VTI", "DIA", "IWM", "IJH", "IJR"],
    "Intl_Equity": ["EFA", "VWO", "EEM", "EWJ", "FXI", "SCZ", "VNQI"],
    "Bonds": ["AGG", "TLT", "SHY", "LQD", "HYG", "MUB", "EMB"],
    "REIT_US": ["VNQ"],
    "Commodities": ["GLD", "SLV", "USO", "DBC"],
}

GRUPOS_MEDIANO_PLAZO = {
    "Broad_Market_ETF": ["SPY", "QQQ"],
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ADBE", "ORCL", "CSCO", "INTC", "AMD", "QCOM", "TXN", "IBM", "XLK"],
    "Communication_Services": ["GOOGL", "META", "DIS", "NFLX", "T", "VZ"],
    "Consumer_Discretionary": ["AMZN", "HD", "NKE", "SBUX", "LOW", "TJX", "MCD", "XLY"],
    "Consumer_Staples": ["PG", "KO", "PEP", "WMT", "COST", "XLP"],
    "Financials": ["JPM", "BAC", "GS", "MS", "C", "AXP", "WFC", "V", "MA", "PYPL", "XLF"],
    "Energy": ["XOM", "CVX", "XLE"],
    "Healthcare": ["LLY", "JNJ", "UNH", "MRK", "ABBV", "PFE", "TMO", "ABT", "XLV"],
    "Industrials": ["GE", "CAT", "BA", "HON", "MMM", "LMT", "RTX", "DE", "EMR", "ETN", "UPS", "XLI"],
    "Utilities": ["SO", "DUK", "NEE"],
}

GRUPOS_RIESGO_ALTO = {
    "Fintech_Crypto": ["SOFI", "UPST", "AFRM", "COIN", "HOOD", "XYZ", "BILL", "MARA"],
    "Enterprise_Software_Security": ["PLTR", "PATH", "AI", "NET", "DDOG", "ZS", "CRWD", "S", "OKTA", "DOCU", "ASAN", "U"],
    "Ecommerce_Marketplace": ["SHOP", "ETSY", "W", "CHWY", "FVRR", "UPWK", "CARG", "CVNA", "OPEN"],
    "Consumer_Internet_Media": ["PINS", "SNAP", "RBLX", "ROKU", "FUBO", "ZM", "TTD"],
    "Hardware_Semis": ["SMCI", "IONQ", "WOLF"],
    "Gaming_Betting_Leisure": ["DKNG", "PENN", "PTON"],
    "EV_Auto": ["RIVN"],
    "Consumer_Staples_Beverage": ["CELH"],
    "Mobility_Rideshare": ["LYFT"],
}

GRUPOS = {
    "largo_plazo": GRUPOS_LARGO_PLAZO,
    "mediano_plazo": GRUPOS_MEDIANO_PLAZO,
    "riesgo_alto": GRUPOS_RIESGO_ALTO,
}


def full_period_metrics(sim: "harness.SimResult") -> dict:
    """Igual que en Capa 6/7: métricas sobre TODA la curva de equity
    (Capa 5 no usa ventanas de walk-forward, por diseño)."""
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


def run_con_universo(bucket_key: str, universo: dict) -> dict:
    if not universo:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": 0}
    all_dates = sorted({d for df in universo.values() for d in df["date"]})
    cfg = harness.BUCKETS[bucket_key]
    sim = harness.simulate_bucket(universo, cfg["risk_pct"], all_dates[0], all_dates[-1])
    return full_period_metrics(sim)


def clasificar(baseline_sharpe: float, resultados_sin_grupo: dict, n_grupos: int) -> str:
    if n_grupos < 3:
        return "INCONCLUSIVE (menos de 3 grupos distinguibles en este universo)"
    if baseline_sharpe is None or baseline_sharpe == 0:
        return "INCONCLUSIVE (baseline sin Sharpe valido)"

    for grupo, m in resultados_sin_grupo.items():
        if m["sharpe"] is None:
            continue
        if m["sharpe"] < 0:
            return f"REJECTED (quitar '{grupo}' vuelve el Sharpe negativo: {m['sharpe']})"
        caida_pct = (baseline_sharpe - m["sharpe"]) / abs(baseline_sharpe) * 100
        if caida_pct > 40:
            return f"REJECTED (quitar '{grupo}' produce caida de {round(caida_pct, 1)}% en Sharpe)"
    return "VALIDATED"


def main():
    resultado = {}
    for bucket_key, grupos in GRUPOS.items():
        print(f"\n=== {bucket_key} ===")
        universo_completo = harness.signaled_universe(bucket_key)
        simbolos_en_universo = set(universo_completo.keys())
        simbolos_en_grupos = {s for members in grupos.values() for s in members}

        faltantes = simbolos_en_grupos - simbolos_en_universo
        sin_grupo = simbolos_en_universo - simbolos_en_grupos
        if faltantes:
            print(f"  (aviso) simbolos en GRUPOS pero sin señal calculada (datos insuficientes): {sorted(faltantes)}")
        if sin_grupo:
            print(f"  (aviso) simbolos con señal pero sin grupo asignado: {sorted(sin_grupo)}")

        baseline = run_con_universo(bucket_key, universo_completo)
        baseline_sharpe = baseline["sharpe"]
        print(f"  Universo completo: Sharpe={baseline_sharpe}, retorno={baseline['return_pct']}%, "
              f"DD={baseline['max_dd_pct']}%, trades={baseline['n_trades']}")

        resultados_sin_grupo = {}
        for grupo_nombre, miembros in grupos.items():
            miembros_presentes = [s for s in miembros if s in universo_completo]
            universo_sin_grupo = {s: df for s, df in universo_completo.items() if s not in miembros}
            m = run_con_universo(bucket_key, universo_sin_grupo)
            resultados_sin_grupo[grupo_nombre] = m
            caida = None
            if baseline_sharpe and m["sharpe"] is not None:
                caida = round((baseline_sharpe - m["sharpe"]) / abs(baseline_sharpe) * 100, 1)
            print(f"  Sin '{grupo_nombre}' ({len(miembros_presentes)} simbolos quitados): "
                  f"Sharpe={m['sharpe']} (caida {caida}%), retorno={m['return_pct']}%, trades={m['n_trades']}")

        label = clasificar(baseline_sharpe, resultados_sin_grupo, len(grupos))
        print(f"  -> {label}")

        resultado[bucket_key] = {
            "baseline": baseline,
            "n_grupos": len(grupos),
            "sin_grupo": resultados_sin_grupo,
            "simbolos_sin_senal_en_grupos": sorted(faltantes),
            "simbolos_sin_grupo_asignado": sorted(sin_grupo),
            "label": label,
        }

    out_path = Path(__file__).parent / "resultados_capa5.json"
    out_path.write_text(json.dumps({"criterio": CRITERIO, "resultado": resultado}, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
