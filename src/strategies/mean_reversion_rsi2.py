"""Estrategia D — Mean Reversion RSI(2) (Connors/Radge).

Investigación base: Connors & Radge, "Short Term Trading Strategies
That Work" — RSI(2) sobrevendido dentro de una tendencia alcista mayor.

Reglas (ver docs/adr/0019-agrega-mean-reversion-produccion.md):
  - Filtro de régimen: solo LONG si close > sma_200 — a diferencia de
    las otras 3 estrategias en producción (que compran FORTALEZA),
    esta compra DEBILIDAD TEMPORAL, pero únicamente dentro de una
    tendencia alcista de fondo ya confirmada — nunca contra ella.
  - Entrada LONG: RSI(2) < 10 (muy sobrevendido).
  - Salida: RSI(2) > 70 (recuperó) O cierre por debajo de su propio
    sma_5 (salida de seguridad si el rebote no llega) O stop ATR.
  - Horizonte: 2-15 días — mucho más corto que las otras 3 estrategias.

Validado con datos reales congelados (36 meses, universo combinado de
mediano_plazo + riesgo_alto): +47.90% aislado, correlación de 0.142 con
el resto del sistema (ver ADR 0019) — la correlación baja es la razón
por la que se agrega como bucket independiente en vez de competir por
símbolo dentro de un bucket existente (lección de ADR 0018, donde
Donchian Breakout sí compitió y diluyó la señal más fuerte).
"""

from dataclasses import dataclass

import pandas as pd

from src.indicators.compute import rsi


@dataclass
class MeanReversionRSI2Params:
    id: str = "mean_reversion_rsi2_v1"
    name: str = "Mean Reversion RSI(2)"
    version: str = "0.1.0"
    rsi_window: int = 2
    entry_threshold: float = 10.0
    exit_threshold: float = 70.0
    atr_stop_multiple: float = 2.0
    require_uptrend_regime: bool = True


def generate_signals(df: pd.DataFrame, params: MeanReversionRSI2Params = MeanReversionRSI2Params()) -> pd.DataFrame:
    """Recibe un DataFrame con indicadores de src/indicators/compute.py
    y agrega `signal` (1 entrada / 0 nada / -1 salida) y `stop_price`.
    """
    df = df.copy()
    price = df["adj_close"] if "adj_close" in df.columns else df["close"]

    df["rsi_2"] = rsi(price, params.rsi_window)
    df["sma_5"] = price.rolling(window=5, min_periods=5).mean()

    regime_ok = (df["close"] > df["sma_200"]) if params.require_uptrend_regime else True

    entry_condition = (df["rsi_2"] < params.entry_threshold) & regime_ok

    df["stop_price"] = df["close"] - params.atr_stop_multiple * df["atr_14"]

    df["signal"] = 0
    df.loc[entry_condition, "signal"] = 1
    exit_condition = (df["rsi_2"] > params.exit_threshold) | (df["close"] < df["sma_5"].shift(1))
    df.loc[exit_condition, "signal"] = -1

    df["strategy_id"] = params.id
    df["strategy_version"] = params.version
    return df
