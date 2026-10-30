import pandas as pd

from src.strategies.momentum_breakout import MomentumBreakoutParams, generate_signals


def _make_df(n=5, **overrides):
    base = {
        "date": pd.date_range("2024-01-01", periods=n),
        "close": [110.0] * n,
        "high_20": [100.0] * n,
        "high_55": [105.0] * n,
        "volume_relative": [2.0] * n,
        "relative_strength_63": [1.2] * n,
        "atr_contraction_20d": [0.8] * n,
        "atr_14": [2.0] * n,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_entry_when_all_conditions_align():
    df = _make_df()
    result = generate_signals(df)
    assert (result["signal"] == 1).all()


def test_no_entry_without_breakout():
    df = _make_df(close=[90.0] * 5)  # por debajo del máximo de 20 sesiones
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_without_volume_surge():
    df = _make_df(volume_relative=[1.1] * 5)  # debajo del umbral 1.5
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_when_underperforming_benchmark():
    df = _make_df(relative_strength_63=[0.8] * 5)  # peor que el benchmark
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_when_volatility_expanding():
    df = _make_df(atr_contraction_20d=[1.5] * 5)  # ATR expandiéndose, no contrayéndose
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_missing_relative_strength_raises():
    df = _make_df().drop(columns=["relative_strength_63"])
    try:
        generate_signals(df)
        assert False, "debía lanzar ValueError"
    except ValueError:
        pass


def test_breakout_window_55_uses_high_55():
    params = MomentumBreakoutParams(breakout_window=55)
    df = _make_df(close=[102.0] * 5)  # > high_55? no (105) -> sin entrada
    result = generate_signals(df, params)
    assert (result["signal"] != 1).all()
