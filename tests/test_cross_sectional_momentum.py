import pandas as pd

from src.strategies.cross_sectional_momentum import CrossSectionalMomentumParams, rank_universe


def _symbol_df(return_6m, above_sma, date="2026-01-01"):
    close = 100.0
    sma = close - 5 if above_sma else close + 5
    return pd.DataFrame(
        {
            "date": [pd.Timestamp(date)],
            "close": [close],
            "sma_200": [sma],
            "return_126d": [return_6m],
        }
    )


def test_ranks_by_return_descending():
    universe = {
        "A": _symbol_df(0.10, above_sma=True),
        "B": _symbol_df(0.30, above_sma=True),
        "C": _symbol_df(0.20, above_sma=True),
    }
    ranking = rank_universe(universe, pd.Timestamp("2026-01-01"))
    assert ranking["symbol"].tolist() == ["B", "C", "A"]


def test_selects_top_pct_only():
    universe = {f"S{i}": _symbol_df(return_6m=0.01 * i, above_sma=True) for i in range(10)}
    params = CrossSectionalMomentumParams(top_pct=0.20)
    ranking = rank_universe(universe, pd.Timestamp("2026-01-01"), params)
    assert ranking["selected"].sum() == 2  # 20% de 10


def test_excludes_below_sma200_even_if_top_ranked():
    universe = {
        "WINNER_BUT_BELOW_SMA": _symbol_df(0.50, above_sma=False),
        "RUNNER_UP": _symbol_df(0.20, above_sma=True),
        "THIRD": _symbol_df(0.10, above_sma=True),
        "FOURTH": _symbol_df(0.05, above_sma=True),
        "FIFTH": _symbol_df(0.01, above_sma=True),
    }
    params = CrossSectionalMomentumParams(top_pct=0.20)  # cutoff = 1
    ranking = rank_universe(universe, pd.Timestamp("2026-01-01"), params)
    selected = ranking[ranking["selected"]]["symbol"].tolist()
    assert "WINNER_BUT_BELOW_SMA" not in selected


def test_empty_universe_returns_empty_ranking():
    ranking = rank_universe({}, pd.Timestamp("2026-01-01"))
    assert ranking.empty


def test_skips_symbols_with_missing_indicators():
    universe = {
        "GOOD": _symbol_df(0.10, above_sma=True),
        "MISSING_SMA": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [None], "return_126d": [0.5]}
        ),
    }
    ranking = rank_universe(universe, pd.Timestamp("2026-01-01"))
    assert ranking["symbol"].tolist() == ["GOOD"]
