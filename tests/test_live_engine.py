import pandas as pd
import pytest

from src.broker.ibkr_adapter import Fill, OrdenNoLlenada
from src.paper_trading import blend_ledger, engine, live_engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(live_engine, "LIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(live_engine, "LIVE_HISTORY_PATH", tmp_path / "history.json")
    # Por default los tests corren como si el mercado estuviera
    # abierto (si no, correr la suite un fin de semana o de noche
    # rompería silenciosamente todos los tests de apertura de
    # posiciones) — ver ADR 0035. El test dedicado al candado mismo
    # lo sobreescribe explícitamente a False.
    monkeypatch.setattr(live_engine, "_mercado_regular_abierto_ahora", lambda: True)
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
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0], "return_126d": [0.1]}
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
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0], "return_126d": [0.1]}
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


def test_run_daily_tick_live_guarda_estado_aunque_un_bucket_posterior_truene(monkeypatch):
    """Regresión: si un bucket ya ejecutó una orden real y el SIGUIENTE
    bucket truena (ej. falta un indicador), el estado del primero debe
    quedar guardado — un fill real nunca debe perderse por un error en
    otro bucket del mismo día."""
    fake_universe_ok = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0], "return_126d": [0.1]}
        ),
    }
    fake_universe_blend = {
        "SPY": pd.DataFrame({"date": [pd.Timestamp("2026-01-01")], "close": [500.0]}),
        "GLD": pd.DataFrame({"date": [pd.Timestamp("2026-01-01")], "close": [300.0]}),
    }

    monkeypatch.setattr(
        live_engine,
        "BUCKET_CONFIG",
        {
            "largo_plazo": {"universe_file": "ok", "risk_pct": 0.01, "strategies": ["time_series_momentum"]},
            "mediano_plazo": {"universe_file": "roto", "risk_pct": 0.01, "strategies": ["time_series_momentum"]},
        },
    )

    def load_universe_falso(symbols=None):
        if symbols == ["VOO"]:
            return fake_universe_ok
        if symbols is not None and set(symbols) == {"SPY", "GLD"}:
            return fake_universe_blend
        raise ValueError("universo roto a propósito")

    monkeypatch.setattr(live_engine, "load_universe", load_universe_falso)
    monkeypatch.setattr(
        live_engine,
        "read_universe_file",
        lambda path: ["VOO"] if path == "ok" else ["ROTO"],
    )
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),
    )
    monkeypatch.setattr(
        live_engine, "ejecutar_orden_mercado",
        lambda ib, symbol, accion, shares: Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=101.0),
    )

    with pytest.raises(ValueError):
        live_engine.run_daily_tick_live(ib=object(), starting_capital_por_bucket={"largo_plazo": 1000.0, "mediano_plazo": 1000.0})

    # El bucket que SÍ alcanzó a correr (y mandar una orden real) debe
    # quedar persistido, aunque el segundo haya tronado.
    estado_guardado = live_engine.load_state()
    assert "largo_plazo" in estado_guardado
    assert len(estado_guardado["largo_plazo"]["open_positions"]) == 1


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


# --- ADR 0028: cash ocioso invertido en el blend, con órdenes reales ---

class _IBFalsoBlend:
    """Fake minimal para probar _invertir_en_blend / _liquidar_de_blend
    sin pasar por el adapter real — las funciones de blend llaman a
    live_engine.ejecutar_orden_mercado directamente (se monkeypatchea
    esa función, no el objeto `ib`), así que aquí `ib` es solo un
    marcador, nunca se usa de verdad."""
    pass


def _fill_falso_para(precios: dict):
    def fn(ib, symbol, accion, shares):
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=precios[symbol])
    return fn


def test_invertir_en_blend_compra_50_50_redondeado_a_enteros(monkeypatch, tmp_path):
    ledger_path = tmp_path / "blend_ledger.json"
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"SPY": 100.0, "GLD": 60.0}))

    bucket_state = {}
    invertido = live_engine._invertir_en_blend(
        object(), "largo_plazo", 1000.0, bucket_state, "2026-11-05", "capital inicial",
        {"SPY": 100.0, "GLD": 60.0}, [],
    )

    # 500 a SPY (5 acciones a $100), 500 a GLD (8 acciones a $60 = $480, resto no alcanza para una 9na)
    assert bucket_state["blend_spy_shares"] == 5
    assert bucket_state["blend_gld_shares"] == 8
    assert invertido == pytest.approx(5 * 100.0 + 8 * 60.0)

    ledger = blend_ledger.load_ledger(ledger_path)
    assert len(ledger) == 2
    assert {tx["simbolo"] for tx in ledger} == {"SPY", "GLD"}
    assert all(tx["tipo"] == "compra" for tx in ledger)


def test_invertir_en_blend_no_crashea_si_una_pata_no_alcanza_para_1_share(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"SPY": 10.0, "GLD": 10000.0}))

    bucket_state = {}
    invertido = live_engine._invertir_en_blend(
        object(), "largo_plazo", 100.0, bucket_state, "2026-11-05", "x", {"SPY": 10.0, "GLD": 10000.0}, [],
    )
    # 50 a SPY -> 5 acciones; 50 a GLD -> 0 acciones (no alcanza ni para 1)
    assert bucket_state["blend_spy_shares"] == 5
    assert bucket_state.get("blend_gld_shares", 0) == 0
    assert invertido == pytest.approx(50.0)


def test_invertir_en_blend_registra_orden_fallida_si_la_pata_no_se_llena(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")

    def fallo(ib, symbol, accion, shares):
        if symbol == "GLD":
            raise OrdenNoLlenada("simulado")
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=100.0)

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fallo)

    bucket_state = {}
    fallidas = []
    live_engine._invertir_en_blend(
        object(), "largo_plazo", 1000.0, bucket_state, "2026-11-05", "x", {"SPY": 100.0, "GLD": 60.0}, fallidas,
    )
    assert bucket_state["blend_spy_shares"] == 5
    assert "blend_gld_shares" not in bucket_state
    assert len(fallidas) == 1
    assert fallidas[0]["symbol"] == "GLD"


def test_liquidar_de_blend_levanta_al_menos_lo_necesario(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"SPY": 100.0, "GLD": 60.0}))

    bucket_state = {"blend_spy_shares": 10, "blend_gld_shares": 10}
    levantado = live_engine._liquidar_de_blend(
        object(), "largo_plazo", 150.0, bucket_state, "2026-11-05", "financia compra",
        {"SPY": 100.0, "GLD": 60.0}, [],
    )
    assert levantado >= 150.0
    assert bucket_state["blend_spy_shares"] < 10
    assert bucket_state["blend_gld_shares"] < 10

    ledger = blend_ledger.load_ledger(tmp_path / "blend_ledger.json")
    assert all(tx["tipo"] == "venta" for tx in ledger)


def test_liquidar_de_blend_nunca_vende_mas_shares_de_las_que_hay(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"SPY": 100.0, "GLD": 60.0}))

    bucket_state = {"blend_spy_shares": 1, "blend_gld_shares": 0}
    levantado = live_engine._liquidar_de_blend(
        object(), "largo_plazo", 10000.0, bucket_state, "2026-11-05", "x", {"SPY": 100.0, "GLD": 60.0}, [],
    )
    assert bucket_state["blend_spy_shares"] == 0
    assert levantado == pytest.approx(100.0)  # solo lo que había, no más


def test_init_bucket_state_live_con_ib_invierte_capital_inicial_en_blend(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    monkeypatch.setattr(live_engine, "_precios_blend_hoy", lambda as_of=None: {"SPY": 100.0, "GLD": 60.0})
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"SPY": 100.0, "GLD": 60.0}))

    estado = live_engine.init_bucket_state("largo_plazo", 1000.0, ib=object())

    assert estado["blend_spy_shares"] == 5
    assert estado["blend_gld_shares"] == 8
    assert estado["cash"] < 1000.0  # el resto, no invertible por redondeo, queda en cash


def test_init_bucket_state_live_sin_ib_sigue_siendo_cash_puro():
    """Compat hacia atrás: sin ib, el comportamiento es el de siempre."""
    estado = live_engine.init_bucket_state("largo_plazo", 1000.0)
    assert estado["cash"] == 1000.0
    assert estado["blend_spy_shares"] == 0
    assert estado["blend_gld_shares"] == 0


def test_filtro_cross_sectional_rechaza_simbolo_con_percentil_bajo_en_largo_plazo_vivo(monkeypatch):
    """Mismo filtro de ADR 0033/0034 aplicado al motor en vivo — AAA
    (return_126d más alto) debe abrir, BBB (percentil 0.5 con 2
    símbolos) debe quedar fuera."""
    fake_universe = {
        "AAA": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [100.0], "sma_200": [40.0],
             "atr_14": [1.0], "return_126d": [0.20]}
        ),
        "BBB": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [50.0], "sma_200": [20.0],
             "atr_14": [1.0], "return_126d": [0.05]}
        ),
        "SPY": pd.DataFrame({"date": [pd.Timestamp("2026-01-02")], "close": [500.0]}),
        "GLD": pd.DataFrame({"date": [pd.Timestamp("2026-01-02")], "close": [300.0]}),
    }
    monkeypatch.setattr(live_engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(live_engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.3,
            "strategies": ["time_series_momentum"],
        }
    })
    monkeypatch.setattr(live_engine, "read_universe_file", lambda path: ["AAA", "BBB"])
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 50),
    )
    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", _fill_falso_para({"AAA": 101.0}))

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    symbols_abiertos = {p["symbol"] for p in bucket_state["open_positions"]}
    assert symbols_abiertos == {"AAA"}
    assert result["open_count"] == 1


def test_no_abre_posiciones_nuevas_fuera_de_horario_regular(monkeypatch):
    """ADR 0035: fuera de horario, IBKR encola la orden en vez de
    rechazarla, y nuestro timeout nunca la ve llenarse — el motor no
    debe intentar entradas nuevas en esa ventana."""
    monkeypatch.setattr(live_engine, "_mercado_regular_abierto_ahora", lambda: False)
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0],
             "atr_14": [1.0], "return_126d": [0.1]}
        ),
    }
    _setup_bucket_unico(
        monkeypatch, fake_universe, "VOO",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 5),
    )

    def fallaria_si_se_llama(ib, symbol, accion, shares):
        pytest.fail("no debería mandar ninguna orden fuera de horario regular")

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fallaria_si_se_llama)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["open_count"] == 0
    assert bucket_state["cash"] == 1000.0


def test_reconciliar_posiciones_automatico_agrega_lo_que_el_motor_no_sabia(monkeypatch):
    """Una posición real de IBKR (ej. orden encolada fuera de horario
    que se llenó después) que el estado local no conoce debe quedar
    agregada al bucket correcto, con costo real y stop recalculado."""
    monkeypatch.setattr(live_engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.02,
            "strategies": ["time_series_momentum"],
        },
    })
    monkeypatch.setattr(live_engine, "read_universe_file", lambda path: ["VOO", "EFA"])
    monkeypatch.setattr(
        live_engine, "posiciones_reales_con_costo",
        lambda ib: {"VOO": {"shares": 3, "avg_cost": 100.0}},
    )
    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [105.0], "sma_200": [40.0],
             "atr_14": [1.0], "return_126d": [0.1]}
        ),
    }
    monkeypatch.setattr(live_engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 10),
    )

    state = {"largo_plazo": {"cash": 1000.0, "open_positions": []}}
    live_engine.save_state(state)

    resultado = live_engine.reconciliar_posiciones_automatico(ib=object())

    assert resultado == {"largo_plazo": ["VOO"]}
    estado_guardado = live_engine.load_state()
    pos = estado_guardado["largo_plazo"]["open_positions"][0]
    assert pos == {
        "symbol": "VOO", "strategy": "time_series_momentum", "entry_date": pos["entry_date"],
        "entry_price": 100.0, "stop_price": 95.0, "initial_stop_price": 95.0, "shares": 3,
    }
    assert estado_guardado["largo_plazo"]["cash"] == pytest.approx(1000.0 - 3 * 100.0)


def test_reconciliar_posiciones_automatico_no_toca_simbolos_ya_conocidos(monkeypatch):
    monkeypatch.setattr(live_engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.02,
            "strategies": ["time_series_momentum"],
        },
    })
    monkeypatch.setattr(live_engine, "read_universe_file", lambda path: ["VOO"])
    monkeypatch.setattr(
        live_engine, "posiciones_reales_con_costo",
        lambda ib: {"VOO": {"shares": 3, "avg_cost": 100.0}},
    )
    monkeypatch.setattr(
        live_engine, "load_universe",
        lambda symbols=None: pytest.fail("no debería consultar universo si no hay candidatos"),
    )

    state = {"largo_plazo": {"cash": 1000.0, "open_positions": [
        {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2026-01-01",
         "entry_price": 99.0, "stop_price": 90.0, "shares": 3},
    ]}}
    live_engine.save_state(state)

    resultado = live_engine.reconciliar_posiciones_automatico(ib=object())

    assert resultado == {}
    assert live_engine.load_state() == state


def test_rebasar_y_recalcular_stops_sube_el_stop_y_rebasa_capital(monkeypatch):
    monkeypatch.setattr(live_engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.02,
            "strategies": ["time_series_momentum"],
        },
    })
    monkeypatch.setattr(live_engine, "_precios_blend_hoy", lambda as_of=None: {"SPY": 100.0, "GLD": 60.0})

    def load_universe_falso(symbols=None):
        if symbols and set(symbols) <= {"VOO"}:
            return {
                "VOO": pd.DataFrame(
                    {"date": [pd.Timestamp("2026-01-05")], "close": [110.0], "sma_200": [40.0], "atr_14": [1.0]}
                ),
            }
        return {}

    monkeypatch.setattr(live_engine, "load_universe", load_universe_falso)
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=0, stop_price=df["close"] - 5),  # 110-5=105, más alto que el guardado (90)
    )

    state = {"largo_plazo": {
        "cash": 200.0, "blend_spy_shares": 0, "blend_gld_shares": 0,
        "starting_capital": 500.0, "peak_equity": 500.0, "day_start_equity": 500.0,
        "day_start_date": "2026-01-04", "start_date": "2026-01-01",
        "open_positions": [
            {"symbol": "VOO", "strategy": "time_series_momentum", "entry_date": "2026-01-01",
             "entry_price": 95.0, "stop_price": 90.0, "shares": 3},
        ],
    }}
    live_engine.save_state(state)

    resultado = live_engine.rebasar_y_recalcular_stops()

    estado = live_engine.load_state()
    pos = estado["largo_plazo"]["open_positions"][0]
    assert pos["stop_price"] == 105.0  # subió de 90 a 105, nunca baja

    equity_esperado = 200.0 + 110.0 * 3  # cash + valor de mercado de la posición
    assert estado["largo_plazo"]["starting_capital"] == equity_esperado
    assert estado["largo_plazo"]["peak_equity"] == equity_esperado
    assert estado["largo_plazo"]["day_start_equity"] == equity_esperado
    assert estado["largo_plazo"]["day_start_date"] is None

    assert resultado["largo_plazo"]["nuevo_starting_capital"] == equity_esperado
    assert resultado["largo_plazo"]["stops_actualizados"] == [{"symbol": "VOO", "antes": 90.0, "despues": 105.0}]


def test_nunca_abre_posicion_nueva_en_spy_o_gld(monkeypatch):
    """SPY y GLD están reservados para el blend de cash ocioso (ADR
    0028) — abrir una posición real de estrategia en el mismo símbolo
    colisiona contra la MISMA posición real de IBKR, dejando el ledger
    del blend creyendo que tiene acciones que en realidad vendió otra
    parte del motor. Bug real encontrado el 9-nov-2026: el ledger
    creía tener 24 acciones de SPY y 24 de GLD que la cuenta real no
    tenía."""
    fake_universe = {
        "SPY": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0], "return_126d": [0.1]}
        ),
        "GLD": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-01")], "close": [50.0], "sma_200": [20.0], "atr_14": [0.5], "return_126d": [0.1]}
        ),
    }
    monkeypatch.setattr(live_engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(live_engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.01,
            "strategies": ["time_series_momentum"],
        }
    })
    monkeypatch.setattr(live_engine, "read_universe_file", lambda path: ["SPY", "GLD"])
    monkeypatch.setitem(engine.SIGNAL_FNS, "time_series_momentum", lambda df: df.assign(signal=1, stop_price=df["close"] - 5))

    def fill_que_nunca_deberia_llamarse(ib, symbol, accion, shares):
        raise AssertionError(f"no debería colocar una orden de estrategia en {symbol}")

    monkeypatch.setattr(live_engine, "ejecutar_orden_mercado", fill_que_nunca_deberia_llamarse)

    bucket_state = live_engine.init_bucket_state("largo_plazo", 1000.0)
    result = live_engine.run_bucket_tick_live("largo_plazo", bucket_state, ib=object())

    assert result["open_count"] == 0
    assert bucket_state["open_positions"] == []


def test_reconciliar_blend_automatico_escala_shares_al_total_real(monkeypatch, tmp_path):
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    """Bug real del 9-nov-2026: el ledger creía tener 24 SPY/24 GLD
    repartidos en 2 buckets, IBKR reportaba 0 reales. La corrección
    debe escalar las shares de cada bucket proporcionalmente (aquí a
    0, ya que el real es 0) y dejar un ajuste auditable en el ledger."""
    monkeypatch.setattr(live_engine, "posiciones_reales", lambda ib: {"SPY": 0, "GLD": 0})
    monkeypatch.setattr(live_engine, "_precios_blend_hoy", lambda as_of=None: {"SPY": 650.0, "GLD": 380.0})

    state = {
        "largo_plazo": {"blend_spy_shares": 16, "blend_gld_shares": 16, "cash": 0.0, "open_positions": []},
        "mediano_plazo": {"blend_spy_shares": 8, "blend_gld_shares": 8, "cash": 0.0, "open_positions": []},
    }
    live_engine.save_state(state)

    ajustes = live_engine.reconciliar_blend_automatico(ib=object())

    assert ajustes["SPY"]["total_creido_antes"] == 24
    assert ajustes["SPY"]["total_real"] == 0
    assert ajustes["SPY"]["por_bucket"]["largo_plazo"] == {"antes": 16, "despues": 0.0}
    assert ajustes["SPY"]["por_bucket"]["mediano_plazo"] == {"antes": 8, "despues": 0.0}

    estado = live_engine.load_state()
    assert estado["largo_plazo"]["blend_spy_shares"] == 0.0
    assert estado["mediano_plazo"]["blend_gld_shares"] == 0.0

    ledger = blend_ledger.load_ledger(live_engine.LIVE_BLEND_LEDGER_PATH)
    ajuste_spy = [t for t in ledger if t["simbolo"] == "SPY" and t["bucket"] == "_reconciliacion"]
    assert len(ajuste_spy) == 1
    assert ajuste_spy[0]["tipo"] == "venta"
    assert ajuste_spy[0]["shares"] == 24
    assert ajuste_spy[0]["monto_usd"] == pytest.approx(24 * 650.0)


def test_reconciliar_blend_automatico_no_toca_nada_si_ya_cuadra(monkeypatch, tmp_path):
    ledger_path = tmp_path / "blend_ledger.json"
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(live_engine, "posiciones_reales", lambda ib: {"SPY": 5, "GLD": 5})
    monkeypatch.setattr(live_engine, "_precios_blend_hoy", lambda as_of=None: {"SPY": 650.0, "GLD": 380.0})

    state = {"largo_plazo": {"blend_spy_shares": 5, "blend_gld_shares": 5, "open_positions": []}}
    live_engine.save_state(state)
    # El ledger también tiene que cuadrar con lo real para que este
    # caso sea "ya está todo bien" de verdad en ambas fuentes de datos.
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-01", tipo="compra",
        simbolo="SPY", monto_usd=3250.0, precio=650.0, shares=5, motivo="capital inicial",
    )
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-01", tipo="compra",
        simbolo="GLD", monto_usd=1900.0, precio=380.0, shares=5, motivo="capital inicial",
    )

    ajustes = live_engine.reconciliar_blend_automatico(ib=object())

    assert ajustes == {}
    ledger = blend_ledger.load_ledger(ledger_path)
    assert len(ledger) == 2  # no se agregó ningún ajuste de más, solo quedan las 2 originales


def test_reconciliar_blend_automatico_corrige_tambien_el_ledger_desincronizado(monkeypatch, tmp_path):
    """Caso real del bug: el contador operativo (state) ya estaba bien,
    pero el LEDGER (lo que lee el reporte del usuario) tenía entradas
    duplicadas de corridas viejas que lo dejaban sobreestimado — esta
    desincronización necesita su propio ajuste, independiente del de
    arriba."""
    ledger_path = tmp_path / "blend_ledger.json"
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(live_engine, "posiciones_reales", lambda ib: {"SPY": 0, "GLD": 0})
    monkeypatch.setattr(live_engine, "_precios_blend_hoy", lambda as_of=None: {"SPY": 650.0, "GLD": 380.0})

    state = {"largo_plazo": {"blend_spy_shares": 0, "blend_gld_shares": 0, "open_positions": []}}
    live_engine.save_state(state)
    # 3 entradas "capital inicial" duplicadas (bug real: la inicialización
    # del bucket se corrió varias veces) — el ledger cree tener 3 acciones
    # que la cuenta real nunca tuvo.
    for _ in range(3):
        blend_ledger.registrar(
            ledger_path, bucket="largo_plazo", fecha="2026-11-05", tipo="compra",
            simbolo="SPY", monto_usd=650.0, precio=650.0, shares=1, motivo="capital inicial del bucket",
        )

    ajustes = live_engine.reconciliar_blend_automatico(ib=object())

    assert "SPY" not in ajustes or "total_creido_antes" not in ajustes.get("SPY", {})  # el state ya estaba bien
    assert ajustes["SPY"]["ledger_neto_antes"] == 3
    assert ajustes["SPY"]["ledger_total_real"] == 0

    ledger = blend_ledger.load_ledger(ledger_path)
    ajuste_ledger = [t for t in ledger if t["bucket"] == "_reconciliacion_ledger"]
    assert len(ajuste_ledger) == 1
    assert ajuste_ledger[0]["tipo"] == "venta"
    assert ajuste_ledger[0]["shares"] == 3

    # Después del ajuste, el neto del ledger completo sí cuadra con la realidad.
    neto_final = sum((t["shares"] if t["tipo"] == "compra" else -t["shares"]) for t in ledger if t["simbolo"] == "SPY")
    assert neto_final == 0
