import pytest

from src.quant_portfolios import engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    yield


def test_init_portfolio_state_full_cash_no_holdings():
    state = engine.init_portfolio_state(1000.0)
    assert state["cash"] == 1000.0
    assert state["holdings"] == {}
    assert state["suspended"] is False
    assert state["peak_equity"] == 1000.0


def test_compute_equity_cash_plus_holdings():
    state = engine.init_portfolio_state(1000.0)
    state["cash"] = 400.0
    state["holdings"] = {"VOO": 2.0, "BND": 10.0}
    equity = engine.compute_equity(state, {"VOO": 100.0, "BND": 50.0})
    assert equity == 400.0 + 2 * 100 + 10 * 50


def test_rebalance_to_weights_moves_cash_into_holdings():
    state = engine.init_portfolio_state(1000.0)
    prices = {"VOO": 100.0, "BND": 50.0}
    engine.rebalance_to_weights(state, prices, {"VOO": 0.6, "BND": 0.4}, equity=1000.0)

    assert state["holdings"]["VOO"] == pytest.approx(6.0)  # 600 / 100
    assert state["holdings"]["BND"] == pytest.approx(8.0)  # 400 / 50
    assert state["cash"] == pytest.approx(0.0, abs=0.01)


def test_rebalance_to_weights_allows_fractional_shares():
    state = engine.init_portfolio_state(1000.0)
    prices = {"VOO": 300.0}
    engine.rebalance_to_weights(state, prices, {"VOO": 1.0}, equity=1000.0)
    assert state["holdings"]["VOO"] == pytest.approx(1000.0 / 300.0)


def test_should_rebalance_monthly_only_once_per_month():
    from src.quant_portfolios.definitions import PortfolioDefinition

    portfolio_def = PortfolioDefinition(
        id="x", name="X", tagline="", weights={"VOO": 1.0}, trend_filter="sma200_momentum6m",
        rebalance_frequency="monthly", defensive_scale=0.5, risk_per_trade_pct=0.01,
        daily_loss_limit_pct=0.01, drawdown_review_pct=0.1, benchmark="VOO",
    )
    state = engine.init_portfolio_state(1000.0)
    assert engine.should_rebalance(portfolio_def, state, "2026-01-15") is True

    state["last_rebalance_month"] = "2026-01"
    assert engine.should_rebalance(portfolio_def, state, "2026-01-20") is False
    assert engine.should_rebalance(portfolio_def, state, "2026-02-01") is True


def test_should_rebalance_daily_always_true():
    from src.quant_portfolios.definitions import PortfolioDefinition

    portfolio_def = PortfolioDefinition(
        id="x", name="X", tagline="", weights={"VOO": 1.0}, trend_filter="breakout_ema_confirm",
        rebalance_frequency="daily", defensive_scale=0.2, risk_per_trade_pct=0.01,
        daily_loss_limit_pct=0.01, drawdown_review_pct=0.1, benchmark="VOO",
    )
    state = engine.init_portfolio_state(1000.0)
    state["last_rebalance_month"] = "2026-01"
    assert engine.should_rebalance(portfolio_def, state, "2026-01-15") is True


def test_drawdown_circuit_breaker_suspends_without_liquidating(monkeypatch):
    """Simula una caída de equity que rompe el límite de drawdown —
    debe suspender el portafolio PERO sin vender nada (holdings
    intactos), cumpliendo la regla del usuario."""
    import pandas as pd

    fake_universe = {
        "VOO": pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-01-01")],
                "close": [50.0],  # cayó de 100 a 50 -> 50% drawdown
                "sma_200": [90.0],
                "return_126d": [-0.3],
            }
        )
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: fake_universe)

    from src.quant_portfolios.definitions import PortfolioDefinition

    portfolio_def = PortfolioDefinition(
        id="test", name="Test", tagline="", weights={"VOO": 1.0}, trend_filter="sma200_momentum6m",
        rebalance_frequency="monthly", defensive_scale=0.5, risk_per_trade_pct=0.01,
        daily_loss_limit_pct=0.5, drawdown_review_pct=0.10, benchmark="VOO",
    )
    monkeypatch.setitem(engine.PORTFOLIOS, "test", portfolio_def)

    state = engine.init_portfolio_state(1000.0)
    state["cash"] = 0.0
    state["holdings"] = {"VOO": 10.0}  # a $100 original = $1000; ahora a $50 = $500
    state["peak_equity"] = 1000.0
    state["day_start_equity"] = 1000.0

    result = engine.run_portfolio_tick("test", state, as_of=None)

    assert result["suspended"] is True
    assert result["newly_suspended_today"] is True
    # No se liquidó nada por la suspensión en sí — las acciones siguen ahí
    # (pueden cambiar por el rebalanceo defensivo, pero no se vacían a cero)
    assert state["holdings"]["VOO"] > 0
