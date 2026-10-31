import pandas as pd

from src.quant_portfolios.trend_filters import (
    breakout_ema_confirm,
    ma_cross_multi_momentum,
    sma200_momentum6m,
)


def test_sma200_momentum6m_true_when_both_positive():
    row = pd.Series({"close": 110, "sma_200": 100, "return_126d": 0.05})
    assert sma200_momentum6m(row) is True


def test_sma200_momentum6m_false_when_below_sma():
    row = pd.Series({"close": 90, "sma_200": 100, "return_126d": 0.05})
    assert sma200_momentum6m(row) is False


def test_sma200_momentum6m_false_when_missing_data():
    row = pd.Series({"close": 110, "sma_200": None, "return_126d": 0.05})
    assert sma200_momentum6m(row) is False


def test_ma_cross_multi_momentum_true_when_aligned_and_positive():
    row = pd.Series(
        {"sma_50": 105, "sma_200": 100, "return_63d": 0.02, "return_126d": 0.04, "return_252d": 0.10}
    )
    assert ma_cross_multi_momentum(row) is True


def test_ma_cross_multi_momentum_false_when_momentum_negative_on_average():
    row = pd.Series(
        {"sma_50": 105, "sma_200": 100, "return_63d": -0.20, "return_126d": -0.20, "return_252d": 0.05}
    )
    assert ma_cross_multi_momentum(row) is False


def test_breakout_ema_confirm_true_when_breakout_and_ema_aligned():
    row = pd.Series({"close": 110, "high_20": 105, "ema_20": 108, "ema_50": 100})
    assert breakout_ema_confirm(row) is True


def test_breakout_ema_confirm_false_without_breakout():
    row = pd.Series({"close": 100, "high_20": 105, "ema_20": 108, "ema_50": 100})
    assert breakout_ema_confirm(row) is False


def test_breakout_ema_confirm_false_without_ema_confirmation():
    row = pd.Series({"close": 110, "high_20": 105, "ema_20": 95, "ema_50": 100})
    assert breakout_ema_confirm(row) is False
