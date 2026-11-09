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


def _bucket_export(starting_capital, start_date, historial):
    return {"starting_capital": starting_capital, "start_date": start_date, "daily_history": historial}


def test_resumen_blend_simulado_reconstruye_el_valor_en_dolares_desde_el_dia_1(monkeypatch):
    monkeypatch.setattr(blend_bucket, "_retorno_indice_por_fecha", lambda fechas: None)  # sin índice en este test
    buckets = {
        "largo_plazo": _bucket_export(100.0, "2026-10-30", [
            {"date": "2026-10-30", "cash": 100.0},
            {"date": "2026-10-31", "cash": 105.0},
            {"date": "2026-11-01", "cash": 0.0},  # todo el blend se vendió para abrir una posición
        ]),
        "riesgo_alto": _bucket_export(50.0, "2026-10-30", [
            {"date": "2026-10-30", "cash": 50.0},
            {"date": "2026-10-31", "cash": 52.0},
            {"date": "2026-11-01", "cash": 53.0},  # nunca abrió posiciones, todo sigue en blend
        ]),
    }

    resumen = blend_bucket.resumen_blend_simulado(buckets)

    assert resumen["starting_capital"] == 150.0  # 100+50, el baseline oficial de cada bucket
    assert resumen["start_date"] == "2026-10-30"
    assert len(resumen["daily_history"]) == 3
    assert resumen["daily_history"][0]["equity"] == 150.0  # 100+50
    assert resumen["daily_history"][1]["equity"] == 157.0  # 105+52
    assert resumen["daily_history"][2]["equity"] == 53.0   # 0+53
    # sin índice disponible, nunca se inventa un retorno
    assert resumen["daily_history"][2]["cumulative_return_pct"] is None


def test_resumen_blend_simulado_el_retorno_viene_del_indice_no_del_flujo_de_cash(monkeypatch):
    """Caso real: casi todo el capital de un bucket se va el día 1 a
    abrir posiciones, dejando poco en el blend — comparar valor_hoy
    contra el capital TOTAL del bucket daría un "-85%" que no es una
    pérdida real. El retorno debe venir del índice SPY/GLD, no de ese
    flujo de cash."""
    monkeypatch.setattr(
        blend_bucket, "_retorno_indice_por_fecha",
        lambda fechas: {"2026-10-30": 100.0, "2026-10-31": 102.0, "2026-11-01": 90.0},
    )
    buckets = {
        "largo_plazo": _bucket_export(1000.0, "2026-10-30", [
            {"date": "2026-10-30", "cash": 5.0},  # casi todo se fue a posiciones el mismo día
            {"date": "2026-10-31", "cash": 5.1},
            {"date": "2026-11-01", "cash": 4.5},
        ]),
    }

    resumen = blend_bucket.resumen_blend_simulado(buckets)

    # el retorno sigue al índice (100 -> 90 = -10%), NUNCA a (4.5/1000-1)*100 = -99.55%
    assert resumen["daily_history"][2]["cumulative_return_pct"] == pytest.approx(-10.0)
    assert resumen["daily_history"][1]["cumulative_return_pct"] == pytest.approx(2.0)


def test_resumen_blend_simulado_drawdown_del_indice(monkeypatch):
    monkeypatch.setattr(
        blend_bucket, "_retorno_indice_por_fecha",
        lambda fechas: {"2026-10-30": 100.0, "2026-10-31": 110.0, "2026-11-01": 99.0},
    )
    buckets = {"largo_plazo": _bucket_export(100.0, "2026-10-30", [
        {"date": "2026-10-30", "cash": 100.0},
        {"date": "2026-10-31", "cash": 110.0},
        {"date": "2026-11-01", "cash": 99.0},
    ])}

    resumen = blend_bucket.resumen_blend_simulado(buckets)

    assert resumen["daily_history"][1]["drawdown_pct"] == 0.0  # nuevo máximo, sin drawdown
    assert resumen["daily_history"][2]["drawdown_pct"] == pytest.approx((110 - 99) / 110 * 100)


def test_resumen_blend_simulado_carga_hacia_adelante_dias_sin_registro_propio(monkeypatch):
    monkeypatch.setattr(blend_bucket, "_retorno_indice_por_fecha", lambda fechas: None)
    buckets = {
        "largo_plazo": _bucket_export(100.0, "2026-10-30", [{"date": "2026-10-30", "cash": 100.0}]),
        "riesgo_alto": _bucket_export(50.0, "2026-10-30", [
            {"date": "2026-10-30", "cash": 50.0},
            {"date": "2026-10-31", "cash": 55.0},  # largo_plazo no tiene registro este día
        ]),
    }

    resumen = blend_bucket.resumen_blend_simulado(buckets)

    # 2026-10-31: riesgo_alto=55 (real), largo_plazo carga el último conocido (100, no inventa uno nuevo)
    assert resumen["daily_history"][1]["equity"] == 155.0


def test_resumen_blend_simulado_sin_buckets_devuelve_none():
    assert blend_bucket.resumen_blend_simulado({}) is None


def test_resumen_blend_simulado_ignora_claves_internas(monkeypatch):
    monkeypatch.setattr(blend_bucket, "_retorno_indice_por_fecha", lambda fechas: None)
    buckets = {
        "_algo_interno": {"starting_capital": 999.0, "start_date": "2026-01-01", "daily_history": []},
        "largo_plazo": _bucket_export(100.0, "2026-10-30", [{"date": "2026-10-30", "cash": 100.0}]),
    }

    resumen = blend_bucket.resumen_blend_simulado(buckets)

    assert resumen["starting_capital"] == 100.0  # no sumó la clave interna
