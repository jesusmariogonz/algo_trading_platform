import pandas as pd

from src.backtesting.walk_forward import slice_universe, split_windows


def _make_universe():
    dates = pd.date_range("2020-01-01", periods=400, freq="D")
    return {
        "AAA": pd.DataFrame({"date": dates, "close": range(400)}),
        "BBB": pd.DataFrame({"date": dates, "close": range(400)}),
    }


def test_split_windows_returns_requested_count():
    universe = _make_universe()
    windows = split_windows(universe, n_windows=4)
    assert len(windows) == 4


def test_split_windows_are_consecutive_and_non_overlapping():
    universe = _make_universe()
    windows = split_windows(universe, n_windows=4)
    for i in range(len(windows) - 1):
        assert windows[i][1] == windows[i + 1][0]  # el fin de una es el inicio de la siguiente


def test_split_windows_cover_full_range():
    universe = _make_universe()
    all_dates = pd.concat([df["date"] for df in universe.values()])
    windows = split_windows(universe, n_windows=3)
    assert windows[0][0] == all_dates.min()
    assert windows[-1][1] == all_dates.max()


def test_slice_universe_keeps_history_before_start():
    universe = _make_universe()
    _, _ = None, None
    start = pd.Timestamp("2020-06-01")
    end = pd.Timestamp("2020-08-01")
    sliced, returned_start = slice_universe(universe, start, end)

    # Debe conservar TODA la historia hasta `end` (para que los
    # indicadores de calentamiento ya estén calculados), no solo [start, end].
    assert sliced["AAA"]["date"].min() == universe["AAA"]["date"].min()
    assert sliced["AAA"]["date"].max() <= end
    assert returned_start == start


def test_slice_universe_excludes_dates_after_end():
    universe = _make_universe()
    end = pd.Timestamp("2020-03-01")
    sliced, _ = slice_universe(universe, pd.Timestamp("2020-02-01"), end)
    assert (sliced["AAA"]["date"] <= end).all()
