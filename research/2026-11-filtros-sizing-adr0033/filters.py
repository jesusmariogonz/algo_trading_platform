"""Los 2 filtros candidatos pendientes de ADR 0033 — reconstrucción
de buena fe del MECANISMO descrito en el ADR (no hay parámetros
exactos documentados: ventana del efficiency ratio, piso del
multiplicador de correlación, etc. — se eligen aquí y se declaran)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def trend_efficiency_ratio(idx: dict[str, pd.DataFrame], symbol: str, date: pd.Timestamp, window: int = 20) -> float:
    """Kaufman Efficiency Ratio: desplazamiento neto / suma de
    desplazamientos absolutos diarios en los últimos `window` días.
    1.0 = movimiento perfectamente suave (tendencia limpia), cerca de
    0 = errático (mismo desplazamiento neto logrado con mucho ruido).
    Usado directo como multiplicador de tamaño (0-1)."""
    df = idx.get(symbol)
    if df is None or date not in df.index:
        return 1.0
    closes = df["close"]
    hist = closes[closes.index <= date].tail(window + 1)
    if len(hist) < window + 1:
        return 1.0
    net_change = abs(hist.iloc[-1] - hist.iloc[0])
    path_sum = hist.diff().abs().sum()
    if path_sum == 0:
        return 1.0
    return float(net_change / path_sum)


def make_trend_efficiency_filter(window: int = 20):
    def _filter(symbol, date, open_symbols, idx):
        return trend_efficiency_ratio(idx, symbol, date, window)
    return _filter


def correlation_adjusted_multiplier(
    idx: dict[str, pd.DataFrame], symbol: str, date: pd.Timestamp, open_symbols: set[str],
    lookback: int = 60, floor: float = 0.1,
) -> float:
    """Penaliza el tamaño si el candidato correlaciona (retornos
    diarios, `lookback` días) con lo ya abierto en el bucket — toma la
    correlación MÁXIMA contra cualquier posición abierta (peor caso de
    diversificación), multiplicador = clip(1 - corr_max, floor, 1.0).
    Sin posiciones abiertas: sin penalización (multiplicador 1.0)."""
    if not open_symbols:
        return 1.0
    df_c = idx.get(symbol)
    if df_c is None or date not in df_c.index:
        return 1.0
    ret_c = df_c["close"][df_c.index <= date].tail(lookback + 1).pct_change().dropna()
    if len(ret_c) < lookback // 2:
        return 1.0

    max_corr = 0.0
    for other in open_symbols:
        df_o = idx.get(other)
        if df_o is None:
            continue
        ret_o = df_o["close"][df_o.index <= date].tail(lookback + 1).pct_change().dropna()
        aligned = pd.concat([ret_c, ret_o], axis=1, join="inner")
        if len(aligned) < lookback // 2:
            continue
        corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        if pd.notna(corr):
            max_corr = max(max_corr, corr)

    return float(np.clip(1 - max_corr, floor, 1.0))


def make_correlation_adjusted_filter(lookback: int = 60, floor: float = 0.1):
    def _filter(symbol, date, open_symbols, idx):
        return correlation_adjusted_multiplier(idx, symbol, date, open_symbols, lookback, floor)
    return _filter
