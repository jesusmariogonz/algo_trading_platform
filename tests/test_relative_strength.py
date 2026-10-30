import pandas as pd

from src.indicators.relative_strength import compute_relative_strength


def test_outperformance_gives_ratio_above_1():
    dates = pd.date_range("2024-01-01", periods=70)
    # El símbolo sube 20%, el benchmark sube 10% en la misma ventana.
    symbol = pd.DataFrame({"date": dates, "adj_close": [100 + i * 0.2 for i in range(70)]})
    benchmark = pd.DataFrame({"date": dates, "adj_close": [100 + i * 0.1 for i in range(70)]})

    result = compute_relative_strength(symbol, benchmark, window=63)
    last = result.iloc[-1]["relative_strength_63"]
    assert last > 1


def test_underperformance_gives_ratio_below_1():
    dates = pd.date_range("2024-01-01", periods=70)
    symbol = pd.DataFrame({"date": dates, "adj_close": [100 + i * 0.05 for i in range(70)]})
    benchmark = pd.DataFrame({"date": dates, "adj_close": [100 + i * 0.2 for i in range(70)]})

    result = compute_relative_strength(symbol, benchmark, window=63)
    last = result.iloc[-1]["relative_strength_63"]
    assert last < 1


def test_missing_benchmark_dates_produce_na_not_crash():
    dates = pd.date_range("2024-01-01", periods=70)
    symbol = pd.DataFrame({"date": dates, "adj_close": [100.0] * 70})
    benchmark = pd.DataFrame({"date": dates[:30], "adj_close": [100.0] * 30})  # incompleto

    result = compute_relative_strength(symbol, benchmark, window=63)
    assert pd.isna(result.iloc[-1]["relative_strength_63"])
