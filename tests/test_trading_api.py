import os

os.environ.setdefault("TRADING_API_TOKEN", "token-de-prueba")

import pytest
from fastapi.testclient import TestClient

from src.api import trading_api
from src.paper_trading import live_engine

HEADERS_OK = {"Authorization": "Bearer token-de-prueba"}
HEADERS_MAL = {"Authorization": "Bearer token-incorrecto"}


@pytest.fixture
def client():
    return TestClient(trading_api.app)


def test_health_requiere_token(client):
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=HEADERS_MAL).status_code == 401


def test_health_responde_ok_con_token_correcto(client):
    r = client.get("/health", headers=HEADERS_OK)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_estado_live_sin_historial_devuelve_vacio(client, monkeypatch):
    monkeypatch.setattr(live_engine, "load_history", lambda: [])
    r = client.get("/live/estado", headers=HEADERS_OK)
    assert r.status_code == 200
    assert r.json() == {"date": None, "buckets": {}, "alertas": []}


def test_estado_live_devuelve_el_ultimo_snapshot(client, monkeypatch):
    historial = [
        {"date": "2026-11-04", "buckets": {}, "alertas": []},
        {"date": "2026-11-05", "buckets": {"largo_plazo": {}}, "alertas": ["algo"]},
    ]
    monkeypatch.setattr(live_engine, "load_history", lambda: historial)
    r = client.get("/live/estado", headers=HEADERS_OK)
    assert r.json()["date"] == "2026-11-05"


def test_ejecutar_live_primera_corrida_reparte_equity_usd_por_buckets(client, monkeypatch):
    llamadas = {}

    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))
    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", lambda ib: 1000.0)
    monkeypatch.setattr(live_engine, "load_state", lambda: {})  # estado vacío: primera corrida
    monkeypatch.setattr(
        trading_api,
        "equity_de_cuenta",
        lambda ib: pytest.fail("no debería usarse MXN si equity_de_cuenta_usd ya respondió"),
    )

    def run_daily_tick_live_falso(ib, capital_por_bucket):
        llamadas["ib"] = ib
        llamadas["capital_por_bucket"] = capital_por_bucket
        return {"date": "2026-11-04", "buckets": {}, "alertas": []}

    monkeypatch.setattr(trading_api.live_engine, "run_daily_tick_live", run_daily_tick_live_falso)

    r = client.post("/live/ejecutar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["date"] == "2026-11-04"
    assert llamadas["ib"] == "ib-falso"
    assert llamadas["desconectado"] == "ib-falso"  # siempre desconecta, incluso si todo sale bien
    # El equity (1000) se repartió en las mismas proporciones que BUCKETS
    assert sum(llamadas["capital_por_bucket"].values()) == pytest.approx(1000.0)
    assert set(llamadas["capital_por_bucket"]) == {"largo_plazo", "mediano_plazo", "riesgo_alto", "mean_reversion"}


def test_ejecutar_live_sin_segmento_usd_convierte_desde_mxn(client, monkeypatch):
    """La cuenta paper real de este proyecto no tiene segmento en USD
    (nunca se ha comprado nada en dólares) — equity_de_cuenta_usd lanza
    RuntimeError y el fallback debe convertir desde MXN."""
    llamadas = {}

    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)

    def sin_segmento_usd(ib):
        raise RuntimeError("No se encontró NetLiquidationByCurrency en USD")

    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", sin_segmento_usd)
    monkeypatch.setattr(trading_api, "equity_de_cuenta", lambda ib: 18866.36)  # MXN
    monkeypatch.setattr(trading_api, "get_usd_mxn_rate", lambda: 18.4)
    monkeypatch.setattr(live_engine, "load_state", lambda: {})

    def run_daily_tick_live_falso(ib, capital_por_bucket):
        llamadas["capital_por_bucket"] = capital_por_bucket
        return {"date": "2026-11-04", "buckets": {}, "alertas": []}

    monkeypatch.setattr(trading_api.live_engine, "run_daily_tick_live", run_daily_tick_live_falso)

    r = client.post("/live/ejecutar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert sum(llamadas["capital_por_bucket"].values()) == pytest.approx(18866.36 / 18.4)


def test_ejecutar_live_corridas_siguientes_no_vuelve_a_pedir_equity(client, monkeypatch):
    llamadas = {}

    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)

    def equity_no_deberia_llamarse(ib):
        pytest.fail("no debería pedirse equity si el estado ya existe")

    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", equity_no_deberia_llamarse)
    monkeypatch.setattr(live_engine, "load_state", lambda: {"largo_plazo": {"open_positions": []}})

    def run_daily_tick_live_falso(ib, capital_por_bucket):
        llamadas["capital_por_bucket"] = capital_por_bucket
        return {"date": "2026-11-05", "buckets": {}, "alertas": []}

    monkeypatch.setattr(trading_api.live_engine, "run_daily_tick_live", run_daily_tick_live_falso)

    r = client.post("/live/ejecutar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert llamadas["capital_por_bucket"] == {}


def test_ejecutar_live_desconecta_aunque_falle(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", True))
    monkeypatch.setattr(live_engine, "load_state", lambda: {"largo_plazo": {}})

    def falla(ib, capital_por_bucket):
        raise RuntimeError("boom")

    monkeypatch.setattr(trading_api.live_engine, "run_daily_tick_live", falla)

    with pytest.raises(RuntimeError):
        client.post("/live/ejecutar", headers=HEADERS_OK)

    assert llamadas.get("desconectado") is True


def test_reconciliar_live(client, monkeypatch):
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)
    monkeypatch.setattr(
        trading_api.live_engine,
        "posiciones_reconciliadas",
        lambda ib: {"esperado": {}, "real": {}, "divergencias": {}},
    )

    r = client.get("/live/reconciliar", headers=HEADERS_OK)
    assert r.status_code == 200
    assert r.json()["divergencias"] == {}
