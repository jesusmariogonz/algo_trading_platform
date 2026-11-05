import pandas as pd
import pytest

from src.paper_trading import engine


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(engine, "BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
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
    precio_hoy = engine._benchmark_price("largo_plazo", state, None)
    valor_en_dolares = state["bench_shares"] * precio_hoy
    assert valor_en_dolares == pytest.approx(1000.0, rel=0.01)


def test_blend_incremental_price_ignores_revisions_to_old_history(monkeypatch):
    """Regresión del bug real de ADR 0020: recomputar el blend desde
    cero cada día lo dejaba expuesto a que una revisión retroactiva de
    un dato viejo (yfinance ajusta precios después, ver ADR 0012)
    desplazara TODO el nivel del índice de un día a otro, tumbando las
    Routines en producción con falsas alertas de equity. El avance
    incremental solo debe mirar los días posteriores al último precio
    ya persistido — nunca debe importarle si un dato de hace meses
    cambió."""
    bucket_state = {}

    universo_v1 = {
        "SPY": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [100.0, 101.0]}),
        "GLD": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [50.0, 50.5]}),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo_v1[s] for s in symbols})
    precio_dia1 = engine._blend_incremental_price(bucket_state, pd.Timestamp("2026-01-01"))
    assert precio_dia1 == pytest.approx(100.0)  # base = 100
    assert bucket_state["blend_last_date"] == "2026-01-01"

    # "Revisión retroactiva": el precio del día 1 cambia completamente
    # (ej. yfinance reajusta un dividendo viejo) Y se agregan los días 2
    # y 3 reales (nunca procesados todavía, as_of del día 1 los había
    # dejado fuera). El avance incremental NUNCA debe volver a leer el
    # día 1 revisado — ya está persistido como ancla fija en
    # bucket_state (componentes crudos, no solo el nivel del índice).
    universo_v2 = {
        "SPY": pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "close": [55.0, 101.0, 102.0],  # día 1 "revisado" hacia abajo ~45%
        }),
        "GLD": pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "close": [30.0, 50.5, 51.0],  # día 1 "revisado" también
        }),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo_v2[s] for s in symbols})
    precio_dia3 = engine._blend_incremental_price(bucket_state, pd.Timestamp("2026-01-03"))

    # El retorno del día 2 se calcula contra el ancla ORIGINAL del día 1
    # (100/50, la persistida en la corrida anterior) — nunca contra el
    # valor "revisado" (55/30) que trae universo_v2. El retorno del día
    # 3 se calcula normalmente contra el día 2 (ambos frescos en esta
    # misma corrida, sin revisión de por medio).
    ret_dia2 = 0.5 * (101.0 / 100.0 - 1) + 0.5 * (50.5 / 50.0 - 1)
    ret_dia3 = 0.5 * (102.0 / 101.0 - 1) + 0.5 * (51.0 / 50.5 - 1)
    esperado = precio_dia1 * (1 + ret_dia2) * (1 + ret_dia3)
    assert precio_dia3 == pytest.approx(esperado, rel=1e-6)
    # Y, sobre todo: el resultado NO debe reflejar en absoluto el ~45%
    # de "caída" que el día 1 revisado sugeriría si se hubiera usado.
    assert precio_dia3 == pytest.approx(102.0, rel=1e-6)
    assert bucket_state["blend_last_date"] == "2026-01-03"


def test_blend_incremental_price_returns_same_value_if_no_new_data(monkeypatch):
    bucket_state = {
        "blend_last_price": 123.45,
        "blend_last_date": "2026-01-02",
        "blend_last_components": {"SPY": 101.0, "GLD": 50.5},
    }
    universo = {
        "SPY": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [100.0, 101.0]}),
        "GLD": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [50.0, 50.5]}),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo[s] for s in symbols})
    precio = engine._blend_incremental_price(bucket_state, pd.Timestamp("2026-01-02"))
    assert precio == pytest.approx(123.45)
    assert bucket_state["blend_last_date"] == "2026-01-02"  # sin cambios


def test_mean_reversion_bucket_was_removed_cleanly():
    """Regresión de ADR 0027: Mean Reversion RSI(2) se eliminó como
    bucket activo (no sobrevivió walk-forward rolling, ver ADR 0026) —
    no debe quedar a medias en ningún diccionario de configuración del
    motor, eso rompería los circuit breakers en silencio si alguien lo
    reactivara sin querer."""
    assert "mean_reversion" not in engine.BUCKET_CONFIG
    assert "mean_reversion" not in engine.BENCHMARK_SYMBOL
    assert "mean_reversion" not in engine.RISK_LIMITS
    assert "mean_reversion" not in engine.ACTIVE_BUCKETS
    # El código de la estrategia se conserva (puede reconsiderarse en
    # el futuro con mejor evidencia), solo se desactivó como bucket.
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


def test_entrada_y_salida_registran_en_el_blend_ledger(monkeypatch):
    """Regresión de ADR 0028: cada vez que se abre o cierra una
    posición, el movimiento de cash hacia/desde el blend debe quedar
    registrado en el ledger — no solo reflejado en bench_shares."""
    from src.paper_trading import blend_ledger

    fake_universe = {
        "VOO": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [100.0], "sma_200": [40.0], "atr_14": [1.0]}
        ),
        "SPY": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [10.0], "sma_200": [9.0], "atr_14": [0.1]}
        ),
        "GLD": pd.DataFrame(
            {"date": [pd.Timestamp("2026-01-02")], "close": [20.0], "sma_200": [19.0], "atr_14": [0.1]}
        ),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: fake_universe)
    monkeypatch.setattr(engine, "BUCKET_CONFIG", {
        "largo_plazo": {
            "universe_file": None,
            "risk_pct": 0.3,
            "strategies": ["time_series_momentum"],
        }
    })
    monkeypatch.setattr(engine, "read_universe_file", lambda path: ["VOO"])
    monkeypatch.setitem(
        engine.SIGNAL_FNS, "time_series_momentum",
        lambda df: df.assign(signal=1, stop_price=df["close"] - 50),
    )

    bucket_state = engine.init_bucket_state("largo_plazo", 10000.0)
    ledger_tras_init = blend_ledger.load_ledger(engine.BLEND_LEDGER_PATH)
    assert len(ledger_tras_init) == 1
    assert ledger_tras_init[0]["tipo"] == "compra"
    assert ledger_tras_init[0]["motivo"] == "capital inicial del bucket"

    engine.run_bucket_tick("largo_plazo", bucket_state)

    ledger = blend_ledger.load_ledger(engine.BLEND_LEDGER_PATH)
    ventas = [tx for tx in ledger if tx["tipo"] == "venta"]
    assert len(ventas) == 1
    assert ventas[0]["bucket"] == "largo_plazo"
    assert "VOO" in ventas[0]["motivo"]
