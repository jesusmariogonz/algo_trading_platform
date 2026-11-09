import pytest

from src.paper_trading import blend_bucket


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    from src.paper_trading import engine

    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    yield


def test_resumen_blend_live_calcula_costo_base_del_ledger(tmp_path):
    from src.paper_trading import blend_ledger

    ledger_path = tmp_path / "ledger.json"
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-01", tipo="compra",
        simbolo="SPY", monto_usd=100.0, precio=100.0, shares=1.0, motivo="capital inicial",
    )
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-01", tipo="compra",
        simbolo="GLD", monto_usd=100.0, precio=50.0, shares=2.0, motivo="capital inicial",
    )

    resumen = blend_bucket.resumen_blend_live(ledger_path, {"SPY": 110.0, "GLD": 55.0})

    assert resumen["starting_capital"] == 200.0
    assert resumen["daily_history"][0]["equity"] == pytest.approx(110.0 + 110.0)  # 1*110 + 2*55
    assert resumen["daily_history"][0]["cumulative_return_pct"] == pytest.approx(10.0)


def test_resumen_blend_live_sin_ledger_devuelve_none(tmp_path):
    assert blend_bucket.resumen_blend_live(tmp_path / "no-existe.json", {"SPY": 100.0}) is None


def test_resumen_blend_live_vende_todo_devuelve_none(tmp_path):
    from src.paper_trading import blend_ledger

    ledger_path = tmp_path / "ledger.json"
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-01", tipo="compra",
        simbolo="SPY", monto_usd=100.0, precio=100.0, shares=1.0, motivo="x",
    )
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-02", tipo="venta",
        simbolo="SPY", monto_usd=105.0, precio=105.0, shares=1.0, motivo="x",
    )

    assert blend_bucket.resumen_blend_live(ledger_path, {"SPY": 105.0}) is None


def test_resumen_blend_simulado_establece_baseline_la_primera_vez():
    state = {"largo_plazo": {"bench_shares": 2.0}, "mediano_plazo": {"bench_shares": 1.0}}
    precios = {"largo_plazo": 100.0, "mediano_plazo": 50.0}

    resumen = blend_bucket.resumen_blend_simulado(state, precios)

    assert resumen["starting_capital"] == 250.0  # 2*100 + 1*50, baseline = valor de hoy
    assert resumen["daily_history"][0]["equity"] == 250.0
    assert resumen["daily_history"][0]["cumulative_return_pct"] == 0.0
    assert blend_bucket.BLEND_TRACKING_STATE_KEY in state  # quedó persistido


def test_resumen_blend_simulado_no_resetea_el_baseline_en_corridas_siguientes():
    state = {"largo_plazo": {"bench_shares": 2.0}}
    blend_bucket.resumen_blend_simulado(state, {"largo_plazo": 100.0})  # baseline = 200.0

    resumen = blend_bucket.resumen_blend_simulado(state, {"largo_plazo": 110.0})

    assert resumen["starting_capital"] == 200.0  # sigue siendo el baseline original
    assert resumen["daily_history"][0]["equity"] == 220.0
    assert resumen["daily_history"][0]["cumulative_return_pct"] == 10.0


def test_resumen_blend_simulado_sin_shares_devuelve_none():
    assert blend_bucket.resumen_blend_simulado({"largo_plazo": {"bench_shares": 0.0}}, {"largo_plazo": 100.0}) is None


def test_resumen_blend_simulado_ignora_claves_internas_al_sumar_shares():
    # _blend_tracking no es un bucket real — no debe sumarse como si
    # tuviera bench_shares, aunque ya exista de una corrida anterior.
    state = {"largo_plazo": {"bench_shares": 1.0}}
    blend_bucket.resumen_blend_simulado(state, {"largo_plazo": 100.0})  # crea _blend_tracking

    resumen = blend_bucket.resumen_blend_simulado(state, {"largo_plazo": 110.0})

    assert resumen["daily_history"][0]["equity"] == 110.0  # solo largo_plazo, _blend_tracking no cuenta
