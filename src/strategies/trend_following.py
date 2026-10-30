"""Estrategia A — Trend Following (ver docs/vision.md § 4.3).

Reglas de investigación, NO una estrategia validada:
  - Precio > SMA 50
  - SMA 50 > SMA 150 > SMA 200   (alineación de medias, "Stage 2" de Weinstein)
  - SMA 200 con pendiente positiva (sma_200_slope_20d > 0)
  - Volumen >= promedio de 20 sesiones (confirmación de volumen)

Fuerza relativa (vs. benchmark) se deja fuera de este primer corte:
requiere comparar contra SPY y se añade en la siguiente iteración.

Salida: stop loss por ATR (configurable) — sin take-profit fijo en
esta versión inicial; se cierra por cruce de tendencia o stop.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class TrendFollowingParams:
    id: str = "trend_following_v1"
    name: str = "Trend Following (SMA alignment)"
    version: str = "0.1.0"
    atr_stop_multiple: float = 2.5
    require_volume_confirmation: bool = True


def generate_signals(df: pd.DataFrame, params: TrendFollowingParams = TrendFollowingParams()) -> pd.DataFrame:
    """Recibe un DataFrame con indicadores ya calculados (ver
    src/indicators/compute.py) y agrega una columna `signal`:
      1  = entrada long
      0  = sin señal / mantener
     -1  = salida (stop ATR)
    y `stop_price` con el nivel de stop loss calculado por ATR.
    """
    df = df.copy()

    price_above_sma50 = df["close"] > df["sma_50"]
    sma_alignment = (df["sma_50"] > df["sma_150"]) & (df["sma_150"] > df["sma_200"])
    sma200_rising = df["sma_200_slope_20d"] > 0
    volume_ok = (
        df["volume"] >= df["vol_avg_20"] if params.require_volume_confirmation else True
    )

    entry_condition = price_above_sma50 & sma_alignment & sma200_rising & volume_ok

    df["stop_price"] = df["close"] - params.atr_stop_multiple * df["atr_14"]

    df["signal"] = 0
    df.loc[entry_condition, "signal"] = 1
    df.loc[df["close"] < df["stop_price"].shift(1), "signal"] = -1

    df["strategy_id"] = params.id
    df["strategy_version"] = params.version
    return df
