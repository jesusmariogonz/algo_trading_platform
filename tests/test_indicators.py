import numpy as np
import pandas as pd

from src.indicators.compute import atr, rsi, sma


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5])
    result = sma(s, window=3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 2.0
    assert result.iloc[4] == 4.0


def test_rsi_all_gains_is_100():
    s = pd.Series(range(1, 30))  # estrictamente creciente
    result = rsi(s, window=14)
    assert result.iloc[-1] == 100


def test_rsi_all_losses_is_0():
    s = pd.Series(range(30, 1, -1))  # estrictamente decreciente
    result = rsi(s, window=14)
    assert result.iloc[-1] == 0


def test_atr_non_negative():
    df = pd.DataFrame(
        {
            "high": [10, 11, 12, 11, 13, 14, 15, 14, 16, 17, 18, 17, 19, 20, 21],
            "low": [9, 9, 10, 9, 11, 12, 13, 12, 14, 15, 16, 15, 17, 18, 19],
            "close": [9.5, 10.5, 11, 10, 12, 13, 14, 13, 15, 16, 17, 16, 18, 19, 20],
        }
    )
    result = atr(df, window=14)
    valid = result.dropna()
    assert (valid >= 0).all()
