import pandas as pd
import pytest

from src.broker.ibkr_adapter import Fill, OrdenNoLlenada
from src.paper_trading import engine, live_engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(live_engine, "LIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(live_engine, "LIVE_HISTORY_PATH", tmp_path / "history.json")
    yield


def _setup_bucket_unico(monkeypatch, fake_universe, simbolo_universo, signal_fn):
    monkeypatch.setattr(live_engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(
        live_engine,
        "BUCKET_CONFIG",
        {
            "largo_plazo": {
                "universe_file": None,
                "risk_pct": 0.01,
                "strategies": ["time_series_momentum"],
            }
        },
    )
    monkeypatch.setattr(live_engine, "read_universe_file", lambda path: [simbolo_universo])
    monkeypatch.setitem(engine.SIGNAL_FNS, "time_series_momentum", signal_fn)


def test_init_bucket_state_live_starts_as_cash_sin_benchmark():
    """A diferencia del motor simulado, aquí NO se invierte en
    benchmark — el cash se queda como cash real (ver docstring del
    módulo)."""
    state = live_engine.init_bucket_state("mediano_plazo", 300.0)
    assert state["starting_capital"] == 300.0
    assert state["cash"] == 300.0
    assert state["open_positions"] == []
    assert "bench_shares" not in state


def test_abre_posicion_usa_el_fill_real_no_el_precio_de_cierre(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),
    )

    def fill_falso(ib, symbol, accion, shares):
        assert accion == "BUY"
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=101.37)

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fill_falso)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["open_count"] == 1
    pos = bucket_state["open_positions"][0]
    # El precio de entrada registrado es el FILL real (101.37), no el
    # close (100.0) que se usó solo para decidir el tamaño.
    assert pos["entry_price"] == 101.37
    assert bucket_state["cash"] == pytest.approx(1000.0 - 101.37 * pos["shares"])


def test_cierra_posicion_usa_el_fill_real_no_el_stop_guardado(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [80.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 100),  # stop muy bajo: no se toca por fórmula
    )

    def fill_falso(ib, symbol, accion, shares):
        assert accion == "SELL"
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=84.5)

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fill_falso)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["cash"] = 200.0
    bucket_state["open_positions"] = [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-12-01",
         "entry_price": 90.0, "stop_price": 85.0, "shares": 10}
    ]  # stop guardado = 85.0, close de hoy = 80.0 -> stop SÍ se toca por precio

    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["closed_today"] == 1
    cerrada = bucket_state["closed_positions"][0]
    # exit_price es el FILL real (84.5), no el stop_price guardado (85.0)
    assert cerrada["exit_price"] == 84.5
    assert cerrada["pnl"] == pytest.approx(84.5 * 10 - 90.0 * 10)
    assert bucket_state["cash"] == pytest.approx(200.0 + 84.5 * 10)
    assert bucket_state["open_positions"] == []


def test_orden_no_llenada_al_cerrar_deja_la_posicion_abierta(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [80.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 100),
    )

    def orden_falla(ib, symbol, accion, shares):
        raise OrdenNoLlenada("simulado: Gateway no confirmó el fill")

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", orden_falla)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["open_positions"] = [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-12-01",
         "entry_price": 90.0, "stop_price": 85.0, "shares": 10}
    ]

    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["closed_today"] == 0
    assert len(bucket_state["open_positions"]) == 1  # sigue abierta, no se asume cerrada
    assert len(result["ordenes_fallidas_hoy"]) == 1
    assert result["ordenes_fallidas_hoy"][0]["symbol"] == "VOO"
    assert result["ordenes_fallidas_hoy"][0]["accion"] == "SELL"


def test_orden_no_llenada_al_abrir_no_crea_posicion(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),
    )

    def orden_falla(ib, symbol, accion, shares):
        raise OrdenNoLlenada("simulado: Gateway no confirmó el fill")

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", orden_falla)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["open_count"] == 0
    assert bucket_state["cash"] == 1000.0  # nada se descontó
    assert len(result["ordenes_fallidas_hoy"]) == 1


def test_drawdown_circuit_breaker_suspende_sin_liquidar(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [50.0], "sma_200": [90.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 40),
    )

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["cash"] = 0.0
    bucket_state["open_positions"] = [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-01-01",
         "entry_price": 100.0, "stop_price": 10.0, "shares": 10}
    ]  # entró a $1000; hoy vale 10*$50=$500 -> 50% drawdown
    bucket_state["peak_equity"] = 1000.0
    bucket_state["day_start_equity"] = 1000.0

    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["suspended"] is True
    assert result["newly_suspended_today"] is True
    # La posición no se liquidó — nunca se mandó ninguna orden de venta.
    assert bucket_state["open_positions"] == [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2025-01-01",
         "entry_price": 100.0, "stop_price": 10.0, "shares": 10}
    ]


def test_bucket_bloqueado_no_abre_posiciones_nuevas(monkeypatch):
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [50.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),
    )

    def fill_falso(ib, symbol, accion, shares):
        pytest.fail("no debería mandarse ninguna orden: el bucket está bloqueado")

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fill_falso)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    bucket_state["cash"] = 1000.0
    bucket_state["peak_equity"] = 1000.0
    bucket_state["day_start_equity"] = 1200.0  # ya cayó >1% hoy
    bucket_state["day_start_date"] = "2026-01-01"

    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["open_count"] == 0
    assert result["daily_loss_breaker_tripped"] is True


def test_posiciones_reconciliadas_detecta_divergencia(monkeypatch, tmp_path):
    state = {
        "largo_plazo": {
            "open_positions": [{"symbol": "AAPL", "shares": 10}],
        },
        "mediano_plazo": {
            "open_positions": [{"symbol": "MSFT", "shares": 5}],
        },
    }
    monkeypatch.setattr(live_engine, "load_state", lambda: state)
    monkeypatch.setattr(live_engine, "posiciones_reales", lambda ib: {"AAPL": 10, "MSFT": 3})

    resultado = live_engine.posiciones_reconciliadas(ib=object())

    assert resultado["divergencias"] == {"MSFT": {"esperado": 5, "real": 3}}
