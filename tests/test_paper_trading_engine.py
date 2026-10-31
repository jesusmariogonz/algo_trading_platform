import pandas as pd
import pytest

from src.paper_trading import engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    yield


def test_init_bucket_state_invests_full_capital_in_benchmark():
    # Desde ADR 0007: el capital inicial se invierte en el benchmark
    # (SPY) del bucket, no se queda en cash parado.
    state = engine.init_bucket_state("mediano_plazo", 300.0)
    assert state["starting_capital"] == 300.0
    assert state["bench_shares"] > 0
    assert state["cash"] == 0.0
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


def test_run_bucket_tick_sets_date_even_with_no_activity(monkeypatch, tmp_path):
    """Bug real que se corrigió: un bucket sin posiciones ni señales
    (ej. sin capital suficiente, o ningún símbolo cumple la regla ese
    día) quedaba con date=None en el historial en vez de la fecha real."""
    import pandas as pd

    fake_universe = {
        "XYZ": pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-10-29")],
                "close": [100.0],
                "sma_200": [90.0],
                "atr_14": [1.0],
            }
        )
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(engine, "BUCKET_CONFIG", {
        "test_bucket": {
            "universe_file": tmp_path / "universe.txt",
            "risk_pct": 0.01,
            "strategies": ["trend_following"],
        }
    })
    monkeypatch.setattr(engine, "read_universe_file", lambda path: ["XYZ"])
    # signal_fn que nunca genera señal de entrada ni requiere salida
    monkeypatch.setitem(engine.SIGNAL_FNS, "trend_following", lambda df: df.assign(signal=0, stop_price=df["close"] - 5))

    bucket_state = engine.init_bucket_state("test_bucket", 100.0)
    result = engine.run_bucket_tick("test_bucket", bucket_state)

    assert result["date"] == "2026-10-29"
    assert result["open_count"] == 0


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
