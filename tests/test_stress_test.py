import pandas as pd

from src.backtesting.stress_test import find_worst_drawdown_window


def test_finds_obvious_peak_and_trough():
    dates = pd.date_range("2024-01-01", periods=10)
    prices = [100, 110, 120, 90, 80, 85, 95, 130, 140, 135]  # pico en idx2 (120), valle en idx4 (80)
    df = pd.DataFrame({"date": dates, "adj_close": prices})

    window = find_worst_drawdown_window(df)
    assert window["peak_date"] == "2024-01-03"
    assert window["trough_date"] == "2024-01-05"
    assert window["drawdown_pct"] == pytest_approx((80 / 120 - 1) * 100)


def pytest_approx(value):
    return round(value, 2)


def test_monotonic_increase_has_near_zero_drawdown():
    dates = pd.date_range("2024-01-01", periods=5)
    prices = [100, 105, 110, 115, 120]
    df = pd.DataFrame({"date": dates, "adj_close": prices})

    window = find_worst_drawdown_window(df)
    assert window["drawdown_pct"] == 0.0


def test_monotonic_decrease_peak_is_first_day():
    dates = pd.date_range("2024-01-01", periods=5)
    prices = [100, 90, 80, 70, 60]
    df = pd.DataFrame({"date": dates, "adj_close": prices})

    window = find_worst_drawdown_window(df)
    assert window["peak_date"] == "2024-01-01"
    assert window["trough_date"] == "2024-01-05"
