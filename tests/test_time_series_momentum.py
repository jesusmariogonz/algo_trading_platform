import pandas as pd

from src.strategies.time_series_momentum import TimeSeriesMomentumParams, generate_signals


def _make_df(n=5, **overrides):
    base = {
        "date": pd.date_range("2024-01-01", periods=n),
        "close": [110.0] * n,
        "return_252d": [0.15] * n,  # +15% en 12 meses
        "return_126d": [0.08] * n,  # +8% en 6 meses
        "atr_14": [2.0] * n,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_entry_when_both_momentum_windows_positive():
    df = _make_df()
    result = generate_signals(df)
    assert (result["signal"] == 1).all()


def test_no_entry_when_12m_momentum_negative():
    df = _make_df(return_252d=[-0.05] * 5)
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_no_entry_when_6m_does_not_confirm():
    df = _make_df(return_126d=[-0.02] * 5)  # 12m positivo pero 6m negativo: no confirma
    result = generate_signals(df)
    assert (result["signal"] != 1).all()


def test_exit_signal_when_12m_turns_negative():
    df = _make_df(return_252d=[-0.01] * 5)
    result = generate_signals(df)
    assert (result["signal"] == -1).all()


def test_missing_return_columns_raises():
    df = _make_df().drop(columns=["return_252d"])
    try:
        generate_signals(df)
        assert False, "debía lanzar ValueError"
    except ValueError:
        pass


def test_stop_price_wider_than_other_strategies():
    # atr_stop_multiple=3.0 (vs 2.5 de trend_following) — horizonte largo, menos ruido
    df = _make_df()
    result = generate_signals(df)
    expected_stop = 110.0 - 3.0 * 2.0
    assert result["stop_price"].iloc[0] == expected_stop
