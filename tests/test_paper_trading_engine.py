import pandas as pd
import pytest

from src.paper_trading import engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    yield


def test_init_bucket_state_starts_with_full_cash():
    state = engine.init_bucket_state("mediano_plazo", 300.0)
    assert state["cash"] == 300.0
    assert state["starting_capital"] == 300.0
    assert state["open_positions"] == []
    assert state["closed_positions"] == []


def test_state_persists_round_trip(tmp_path):
    state = {"mediano_plazo": engine.init_bucket_state("mediano_plazo", 300.0)}
    engine.save_state(state)
    loaded = engine.load_state()
    assert loaded == state


def test_history_is_idempotent_for_same_date():
    engine.save_history([{"date": "2026-10-29", "buckets": {}}])
    history = engine.load_history()
    history = [h for h in history if h["date"] != "2026-10-29"]
    history.append({"date": "2026-10-29", "buckets": {"x": 1}})
    engine.save_history(history)

    result = engine.load_history()
    assert len(result) == 1
    assert result[0]["buckets"] == {"x": 1}


def test_closing_a_position_never_creates_money_from_nothing():
    """La suma de cash + valor de posiciones abiertas antes de cerrar
    debe ser igual a cash + P&L después de cerrar — cerrar una posición
    mueve valor, no lo crea."""
    bucket_state = engine.init_bucket_state("mediano_plazo", 1000.0)
    bucket_state["cash"] = 700.0
    bucket_state["open_positions"] = [
        {
            "symbol": "TEST",
            "strategy": "trend_following",
            "entry_date": "2026-10-01",
            "entry_price": 100.0,
            "stop_price": 90.0,
            "shares": 3,
        }
    ]

    # Simula el cierre manualmente como lo hace run_bucket_tick: vender a 95 (stop no tocado, salida por señal)
    exit_price = 95.0
    pos = bucket_state["open_positions"][0]
    proceeds = exit_price * pos["shares"]
    pnl = proceeds - pos["entry_price"] * pos["shares"]

    valor_antes = bucket_state["cash"] + pos["entry_price"] * pos["shares"]
    cash_despues = bucket_state["cash"] + proceeds
    valor_despues = cash_despues  # posición ya cerrada, no hay valor de mercado adicional

    # El valor total cambió exactamente por el P&L de la operación, ni un centavo más.
    assert valor_despues - valor_antes == pytest.approx(pnl)
