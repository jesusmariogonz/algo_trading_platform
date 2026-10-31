"""Filtros de tendencia/momentum, uno por portafolio — deciden si un
activo recibe su peso objetivo completo o el peso "defensivo"
(defensive_scale) en el próximo rebalanceo. Ver definitions.py.

Cada función recibe la ÚLTIMA fila de indicadores de un símbolo (una
pd.Series) y devuelve True si el activo está "en tendencia" (peso
completo) o False si no (peso defensivo).

Simplificación declarada, no oculta: esto NO es pyramiding real de
Turtle Trading ni rebalanceo activo diario de posiciones — es
"¿este activo recibe su peso objetivo completo o reducido en el
próximo rebalanceo?", una adaptación razonable para un portafolio de
pesos fijos, no una réplica literal de las reglas académicas
originales.
"""

import pandas as pd


def sma200_momentum6m(row: pd.Series) -> bool:
    """Conservative Alpha: SMA 200 + momentum de 6 meses."""
    if pd.isna(row.get("sma_200")) or pd.isna(row.get("return_126d")):
        return False
    return bool(row["close"] > row["sma_200"] and row["return_126d"] > 0)


def ma_cross_multi_momentum(row: pd.Series) -> bool:
    """Balanced Growth: cruce de medias 50/200 + momentum combinado de
    3, 6 y 12 meses (promedio simple de los tres, debe ser positivo)."""
    needed = ["sma_50", "sma_200", "return_63d", "return_126d", "return_252d"]
    if any(pd.isna(row.get(k)) for k in needed):
        return False
    momentum_score = (row["return_63d"] + row["return_126d"] + row["return_252d"]) / 3
    return bool(row["sma_50"] > row["sma_200"] and momentum_score > 0)


def breakout_ema_confirm(row: pd.Series) -> bool:
    """Aggressive Momentum: ruptura de Turtle Trading (máximo de 20
    sesiones, igual que momentum_breakout.py) confirmada con EMA 20 >
    EMA 50. Revisión diaria, no mensual."""
    needed = ["high_20", "ema_20", "ema_50"]
    if any(pd.isna(row.get(k)) for k in needed):
        return False
    breakout = row["close"] > row["high_20"]
    ema_confirms = row["ema_20"] > row["ema_50"]
    return bool(breakout and ema_confirms)


TREND_FILTERS = {
    "sma200_momentum6m": sma200_momentum6m,
    "ma_cross_multi_momentum": ma_cross_multi_momentum,
    "breakout_ema_confirm": breakout_ema_confirm,
}
