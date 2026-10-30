"""Estrategia B — Momentum / Breakout (ver docs/vision.md § 4.3).

Reglas de investigación, NO una estrategia validada. Inspirada en
ideas de Minervini/O'Neil/Weinstein pero simplificada para esta fase:

  - Ruptura: close > máximo de las 20 (o 55) sesiones previas
  - Volumen de ruptura: volume_relative >= min_breakout_volume
  - Fuerza relativa: relative_strength_63 > min_relative_strength
    (el símbolo debe estar superando al benchmark)
  - Contracción previa de volatilidad (proxy VCP simplificado):
    atr_contraction_20d <= max_atr_contraction — la volatilidad debía
    estar contrayéndose antes de la ruptura, no expandiéndose ya

Nota: esto NO es detección completa de un patrón VCP (que requiere
identificar múltiples contracciones sucesivas de precio y volumen).
Es un proxy de una sola variable; una iteración futura puede
refinarlo si el proxy simple no es suficiente.

Salida: stop loss por ATR, más ajustado que en Trend Following
(las rupturas fallidas suelen revertir rápido).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class MomentumBreakoutParams:
    id: str = "momentum_breakout_v1"
    name: str = "Momentum / Breakout (VCP simplificado)"
    version: str = "0.1.0"
    breakout_window: int = 20  # usar 55 para rupturas de rango más largo
    min_breakout_volume: float = 1.5  # volumen >= 1.5x el promedio de 20 sesiones
    min_relative_strength: float = 1.0  # debe superar al benchmark
    max_atr_contraction: float = 1.0  # ATR actual <= ATR de hace 20 sesiones
    atr_stop_multiple: float = 1.75


def generate_signals(df: pd.DataFrame, params: MomentumBreakoutParams = MomentumBreakoutParams()) -> pd.DataFrame:
    """Recibe un DataFrame con indicadores de src/indicators/compute.py
    y relative_strength_63 de src/indicators/relative_strength.py.
    Agrega `signal` (1 entrada / 0 nada / -1 salida) y `stop_price`.
    """
    df = df.copy()

    breakout_col = "high_55" if params.breakout_window == 55 else "high_20"
    if breakout_col not in df.columns:
        raise ValueError(f"Falta la columna '{breakout_col}'. Corre src.indicators.compute primero.")
    if "relative_strength_63" not in df.columns:
        raise ValueError(
            "Falta 'relative_strength_63'. Corre src.indicators.relative_strength "
            "después de src.indicators.compute."
        )

    breakout = df["close"] > df[breakout_col]
    volume_confirmed = df["volume_relative"] >= params.min_breakout_volume
    relative_strength_ok = df["relative_strength_63"] > params.min_relative_strength
    volatility_contracted = df["atr_contraction_20d"] <= params.max_atr_contraction

    entry_condition = breakout & volume_confirmed & relative_strength_ok & volatility_contracted

    df["stop_price"] = df["close"] - params.atr_stop_multiple * df["atr_14"]

    df["signal"] = 0
    df.loc[entry_condition, "signal"] = 1
    df.loc[df["close"] < df["stop_price"].shift(1), "signal"] = -1

    df["strategy_id"] = params.id
    df["strategy_version"] = params.version
    return df
