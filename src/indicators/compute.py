"""Calcula indicadores técnicos sobre los Parquet crudos en data/raw/
y guarda el resultado en data/processed/<symbol>.parquet.

Indicadores (Estrategia A — Trend Following):
  SMA 20, 50, 150, 200 · RSI 14 · ATR 14 · volumen promedio 20 sesiones.

Usa `adj_close` (ajustado por splits/dividendos) como precio base para
evitar distorsiones — ver sección "Data Engineering" del documento de
visión sobre look-ahead bias / survivorship bias.
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    result = pd.Series(index=series.index, dtype="float64")
    no_loss = avg_loss == 0
    no_gain_no_loss = no_loss & (avg_gain == 0)
    rs = avg_gain / avg_loss.where(~no_loss)
    result[:] = 100 - (100 / (1 + rs))
    result[no_loss] = 100.0       # sin pérdidas -> RSI máximo
    result[no_gain_no_loss] = 50.0  # precio plano -> RSI neutral
    result[avg_gain.isna() | avg_loss.isna()] = pd.NA
    return result


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    price = df["adj_close"]

    df["sma_20"] = sma(price, 20)
    df["sma_50"] = sma(price, 50)
    df["sma_150"] = sma(price, 150)
    df["sma_200"] = sma(price, 200)
    df["rsi_14"] = rsi(price, 14)
    df["atr_14"] = atr(df, 14)
    df["vol_avg_20"] = df["volume"].rolling(window=20, min_periods=20).mean()
    df["sma_200_slope_20d"] = df["sma_200"] - df["sma_200"].shift(20)

    return df


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(RAW_DIR.glob("*.parquet"))
    if not raw_files:
        raise SystemExit(
            "No hay datos en data/raw/. Corre primero: python -m src.data.download"
        )

    for path in raw_files:
        df = pd.read_parquet(path)
        df = compute_indicators(df)
        out_path = PROCESSED_DIR / path.name
        df.to_parquet(out_path, index=False)
        print(f"  {path.stem}: {len(df)} filas -> {out_path}")

    print(f"\nProcesados: {len(raw_files)} símbolos")


if __name__ == "__main__":
    main()
