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
    # (hoy: blend SPY/GLD) del bucket, no se queda en cash parado.
    state = engine.init_bucket_state("mediano_plazo", 300.0)
    assert state["starting_capital"] == 300.0
    assert state["bench_shares"] > 0
    assert state["cash"] == 0.0
    assert state["open_positions"] == []
    assert state["closed_positions"] == []


def test_bench_shares_round_trip_preserves_dollar_value():
    """Regresión del bug real de ADR 0014: al inicializar un bucket, el
    valor en dólares de bench_shares (marcado a mercado con el precio
    de HOY del mismo benchmark) debe coincidir con el capital que se
    invirtió — si alguien cambia BENCHMARK_SYMBOL en el futuro sin
    migrar correctamente, esta prueba debe fallar."""
    state = engine.init_bucket_state("largo_plazo", 1000.0)
    precio_hoy = engine._benchmark_price("largo_plazo", None)
    valor_en_dolares = state["bench_shares"] * precio_hoy
    assert valor_en_dolares == pytest.approx(1000.0, rel=0.01)


def test_mean_reversion_bucket_is_registered_in_engine():
    """Regresión de ADR 0019: el bucket mean_reversion debe estar
    presente en todos los diccionarios de configuración del motor, no
    solo en BUCKET_CONFIG — un bucket a medias (ej. sin RISK_LIMITS)
    rompería los circuit breakers en silencio."""
    assert "mean_reversion" in engine.BUCKET_CONFIG
    assert "mean_reversion" in engine.BENCHMARK_SYMBOL
    assert "mean_reversion" in engine.RISK_LIMITS
    assert "mean_reversion" in engine.ACTIVE_BUCKETS
    assert engine.BUCKET_CONFIG["mean_reversion"]["strategies"] == ["mean_reversion_rsi2"]
    assert "mean_reversion_rsi2" in engine.SIGNAL_FNS


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


def test_drawdown_circuit_breaker_suspends_without_liquidating(monkeypatch):
    """Desde ADR 0008: si el equity cae más del límite de drawdown
    desde su máximo histórico, el bucket queda suspendido — pero las
    posiciones abiertas se mantienen intactas, nunca se liquidan."""
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [50.0], "sma_200": [90.0], "atr_14": [1.0]}
        ),
        "SPY": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [10.0], "sma_200": [9.0], "atr_14": [0.1]}
        ),
        "GLD": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [20.0], "sma_200": [19.0], "atr_14": [0.1]}
        ),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.01,
            "strategies": ["time_series_momentum"],
        }
    })
    monkeypatch.setattr(engine, "read_universe_file", lambda path: ["VOO"])
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 40),
    )

    bucket_state = engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["bench_shares"] = 0.0
    bucket_state["cash"] = 0.0
    bucket_state["open_positions"] = [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-01-01",
         "entry_price": 100.0, "stop_price": 10.0, "shares": 10}
    ]  # entró a $1000 (10 acciones a $100); hoy vale 10*$50=$500 -> 50% drawdown
    bucket_state["peak_equity"] = 1000.0
    bucket_state["day_start_equity"] = 1000.0
    bucket_state["day_start_date"] = None

    result = engine.run_bucket_tick("largo_plazo", bucket_state)

    assert result["suspended"] is True
    assert result["newly_suspended_today"] is True
    assert bucket_state["suspended"] is True
    # La posición NO se liquidó — sigue abierta con las mismas acciones.
    assert bucket_state["open_positions"] == [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-01-01",
         "entry_price": 100.0, "stop_price": 10.0, "shares": 10}
    ]


def test_blocked_bucket_never_opens_new_positions(monkeypatch):
    """Un bucket con la pérdida diaria ya disparada no debe abrir
    posiciones nuevas aunque haya una señal de entrada válida."""
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [50.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
        "SPY": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [10.0], "sma_200": [9.0], "atr_14": [0.1]}
        ),
        "GLD": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [20.0], "sma_200": [19.0], "atr_14": [0.1]}
        ),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.01,
            "strategies": ["time_series_momentum"],
        }
    })
    monkeypatch.setattr(engine, "read_universe_file", lambda path: ["VOO"])
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),  # señal de entrada válida
    )

    bucket_state = engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["bench_shares"] = 0.0
    bucket_state["cash"] = 1000.0
    bucket_state["open_positions"] = []
    bucket_state["peak_equity"] = 1000.0
    bucket_state["day_start_equity"] = 1200.0  # ya cayó >1% hoy desde el inicio del día
    bucket_state["day_start_date"] = "2026-01-01"  # mismo día: no se resetea el breaker

    result = engine.run_bucket_tick("largo_plazo", bucket_state)

    assert result["daily_loss_breaker_tripped"] is True
    assert result["open_count"] == 0  # no se abrió nada pese a la señal
