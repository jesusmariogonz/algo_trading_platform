import pandas as pd

from src.strategies.trend_following import TrendFollowingParams, generate_signals


def _make_df(n=10, **overrides):
    base = {
        "date": pd.date_range("2024-01-01", periods=n),
        "close": [100.0] * n,
        "sma_50": [95.0] * n,
        "sma_150": [90.0] * n,
        "sma_200": [85.0] * n,
        "sma_200_slope_20d": [1.0] * n,
        "volume": [1_000_000] * n,
        "vol_avg_20": [900_000] * n,
        "atr_14": [2.0] * n,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_entry_signal_when_all_conditions_align():
    df = _make_df()
    result = generate_signals(df)
    assert (result["signal"] == 1).all()


def test_no_entry_when_sma_not_aligned():
    df = _make_df(sma_50=[80.0] * 10)  # sma_50 < sma_150: rompe el orden
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_when_sma200_falling():
    df = _make_df(sma_200_slope_20d=[-1.0] * 10)
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_without_volume_confirmation():
    df = _make_df(volume=[500_000] * 10)  # por debajo del promedio
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_stop_price_below_close():
    df = _make_df()
    result = generate_signals(df)
    assert (result["stop_price"] < result["close"]).all()
