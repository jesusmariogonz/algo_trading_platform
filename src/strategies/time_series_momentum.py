"""Estrategia C — Time-Series Momentum (ver docs/vision.md § 4.3).

Investigación base: Moskowitz, Ooi & Pedersen (2012), "Time Series
Momentum", Journal of Financial Economics. Encontraron persistencia
de retornos entre 1 y 12 meses sobre 58 instrumentos (índices,
divisas, materias primas, bonos).

Reglas (adaptadas de la propuesta del usuario):
  - Entrada LONG: retorno de 12 meses positivo Y retorno de 6 meses
    también positivo (confirmación de tendencia en la misma dirección)
  - Salida: el retorno de 12 meses cambia de signo
  - Revisión pensada para ser MENSUAL, no diaria — una estrategia de
    horizonte largo no debería generar ni evaluarse con ruido diario.
    El backtest sí corre sobre datos diarios (vectorbt lo requiere),
    pero en uso real (daily_signals.py) esta estrategia se consulta
    una vez al mes, no cada mañana.

Diferencia deliberada frente al paper original: el paper opera LONG
y SHORT simétricamente. Esta implementación es SOLO LONG — este
proyecto no tiene infraestructura de shorting/margen (cuenta de
efectivo, swing retail), y fingir que sí la tiene sería inventar una
capacidad que no existe. Cuando el retorno de 12 meses es negativo,
la regla aquí es "no tener posición", no "ir corto".
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class TimeSeriesMomentumParams:
    id: str = "time_series_momentum_v1"
    name: str = "Time-Series Momentum (12m/6m, solo largo)"
    version: str = "0.1.0"
    atr_stop_multiple: float = 3.0  # más ancho que las otras estrategias: horizonte largo, menos ruido


def generate_signals(df: pd.DataFrame, params: TimeSeriesMomentumParams = TimeSeriesMomentumParams()) -> pd.DataFrame:
    df = df.copy()

    if "return_252d" not in df.columns or "return_126d" not in df.columns:
        raise ValueError(
            "Faltan 'return_252d'/'return_126d'. Corre src.indicators.compute primero."
        )

    momentum_12m_positive = df["return_252d"] > 0
    momentum_6m_confirms = df["return_126d"] > 0
    entry_condition = momentum_12m_positive & momentum_6m_confirms

    df["stop_price"] = df["close"] - params.atr_stop_multiple * df["atr_14"]

    df["signal"] = 0
    df.loc[entry_condition, "signal"] = 1
    # Salida: el retorno de 12 meses cambia de signo (deja de ser positivo),
    # que es la regla del paper — más conservadora que solo el stop ATR.
    df.loc[df["return_252d"] <= 0, "signal"] = -1

    df["strategy_id"] = params.id
    df["strategy_version"] = params.version
    return df
