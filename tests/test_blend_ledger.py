import pytest

from src.paper_trading import blend_ledger


@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "blend_ledger.json"


def test_registrar_persiste_y_se_puede_releer(ledger_path):
    blend_ledger.registrar(
        ledger_path, bucket="largo_plazo", fecha="2026-11-05", tipo="compra",
        simbolo="SPY", monto_usd=100.0, precio=766.81, shares=0.1304, motivo="capital inicial",
    )
    ledger = blend_ledger.load_ledger(ledger_path)
    assert len(ledger) == 1
    assert ledger[0]["bucket"] == "largo_plazo"
    assert ledger[0]["tipo"] == "compra"
    assert ledger[0]["monto_usd"] == 100.0


def test_registrar_rechaza_tipo_invalido(ledger_path):
    with pytest.raises(ValueError):
        blend_ledger.registrar(
            ledger_path, bucket="largo_plazo", fecha="2026-11-05", tipo="otra_cosa",
            simbolo="SPY", monto_usd=100.0, precio=100.0, shares=1.0, motivo="x",
        )


def test_load_ledger_vacio_si_no_existe(tmp_path):
    assert blend_ledger.load_ledger(tmp_path / "no_existe.json") == []


def test_ganancia_por_bucket_compra_y_valor_sube():
    ledger = [
        {"bucket": "largo_plazo", "simbolo": "SPY", "tipo": "compra", "monto_usd": 100.0, "shares": 1.0},
    ]
    ganancia = blend_ledger.ganancia_por_bucket(ledger, {"SPY": 110.0})
    assert ganancia["largo_plazo"] == pytest.approx(10.0)


def test_ganancia_por_bucket_neta_compra_y_venta_parcial():
    ledger = [
        {"bucket": "largo_plazo", "simbolo": "SPY", "tipo": "compra", "monto_usd": 100.0, "shares": 2.0},
        {"bucket": "largo_plazo", "simbolo": "SPY", "tipo": "venta", "monto_usd": 55.0, "shares": 1.0},
    ]
    # Queda 1 share, costo base neto = 100-55 = 45. Si hoy vale 60/share:
    ganancia = blend_ledger.ganancia_por_bucket(ledger, {"SPY": 60.0})
    assert ganancia["largo_plazo"] == pytest.approx(15.0)


def test_ganancia_por_bucket_suma_spy_y_gld_del_mismo_bucket():
    ledger = [
        {"bucket": "riesgo_alto", "simbolo": "SPY", "tipo": "compra", "monto_usd": 50.0, "shares": 1.0},
        {"bucket": "riesgo_alto", "simbolo": "GLD", "tipo": "compra", "monto_usd": 50.0, "shares": 1.0},
    ]
    ganancia = blend_ledger.ganancia_por_bucket(ledger, {"SPY": 55.0, "GLD": 48.0})
    assert ganancia["riesgo_alto"] == pytest.approx(3.0)  # +5 en SPY, -2 en GLD


def test_ganancia_por_bucket_ignora_simbolo_sin_precio_hoy():
    ledger = [
        {"bucket": "largo_plazo", "simbolo": "BLEND_SPY_GLD", "tipo": "compra", "monto_usd": 100.0, "shares": 1.0},
    ]
    assert blend_ledger.ganancia_por_bucket(ledger, {}) == {}
