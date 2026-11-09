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


def test_desplegar_requiere_token(client):
    assert client.post("/admin/desplegar").status_code == 401


def test_desplegar_corre_git_pull_y_pytest_y_programa_reinicio(client, monkeypatch):
    llamadas = []

    monkeypatch.setattr(trading_api, "_git_pull", lambda: "Already up to date.")
    monkeypatch.setattr(trading_api, "_correr", lambda *args, **kwargs: llamadas.append(args))

    hilos_lanzados = []

    class HiloFalso:
        def __init__(self, target, daemon):
            self.target = target
            hilos_lanzados.append(self)

        def start(self):
            pass  # no lo ejecutamos de verdad: mataría el proceso de pytest

    monkeypatch.setattr(trading_api.threading, "Thread", HiloFalso)

    r = client.post("/admin/desplegar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["git_pull"] == "Already up to date."
    assert llamadas == [("pytest", "-q")]
    assert len(hilos_lanzados) == 1
    assert hilos_lanzados[0].target == trading_api._reiniciar_proceso_despues_de_responder


def test_desplegar_no_programa_reinicio_si_los_tests_fallan(client, monkeypatch):
    monkeypatch.setattr(trading_api, "_git_pull", lambda: "ok")

    def pytest_falla(*args, **kwargs):
        raise RuntimeError("Falló 'pytest -q' (exit 1): algo tronó")

    monkeypatch.setattr(trading_api, "_correr", pytest_falla)

    hilos_lanzados = []
    monkeypatch.setattr(
        trading_api.threading, "Thread",
        lambda target, daemon: hilos_lanzados.append(target) or pytest.fail("no debería llegar aquí"),
    )

    with pytest.raises(RuntimeError):
        client.post("/admin/desplegar", headers=HEADERS_OK)

    assert hilos_lanzados == []


def test_desplegar_propaga_error_si_git_pull_falla(client, monkeypatch):
    def git_falla():
        raise RuntimeError("git pull falló: conflicto")

    monkeypatch.setattr(trading_api, "_git_pull", git_falla)
    monkeypatch.setattr(
        trading_api, "_correr",
        lambda *a, **kw: pytest.fail("no debería correr pytest si git pull ya falló"),
    )

    with pytest.raises(RuntimeError):
        client.post("/admin/desplegar", headers=HEADERS_OK)


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
    assert set(llamadas["capital_por_bucket"]) == {"largo_plazo", "mediano_plazo", "riesgo_alto"}


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


def test_correr_lanza_runtimeerror_con_la_salida_si_el_subproceso_falla():
    with pytest.raises(RuntimeError, match="exit 1"):
        trading_api._correr("src.paper_trading._modulo_que_no_existe_de_verdad")


def test_refrescar_datos_y_ejecutar_corre_los_3_pasos_en_orden_y_luego_ejecuta(client, monkeypatch):
    llamadas = []

    def correr_falso(*args):
        llamadas.append(args)

    monkeypatch.setattr(trading_api, "_correr", correr_falso)
    monkeypatch.setattr(trading_api, "ejecutar_live", lambda authorization: {"date": "2026-11-05"})

    r = client.post("/live/refrescar-datos-y-ejecutar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["date"] == "2026-11-05"
    assert llamadas == [
        ("src.data.download", "--universe", str(trading_api.UNIVERSO_LIVE)),
        ("src.indicators.compute",),
        ("src.indicators.relative_strength", "--universe", str(trading_api.UNIVERSO_LIVE)),
    ]


def test_refrescar_datos_y_ejecutar_requiere_token(client):
    assert client.post("/live/refrescar-datos-y-ejecutar").status_code == 401


def test_refrescar_datos_y_ejecutar_no_llama_ejecutar_live_si_un_paso_falla(client, monkeypatch):
    def correr_que_falla(*args):
        if args[0] == "src.indicators.compute":
            raise RuntimeError("falló el cómputo de indicadores")

    def ejecutar_no_deberia_llamarse(authorization):
        pytest.fail("no debería ejecutar el motor si refrescar datos falló")

    monkeypatch.setattr(trading_api, "_correr", correr_que_falla)
    monkeypatch.setattr(trading_api, "ejecutar_live", ejecutar_no_deberia_llamarse)

    with pytest.raises(RuntimeError):
        client.post("/live/refrescar-datos-y-ejecutar", headers=HEADERS_OK)


def test_reiniciar_capital_live_requiere_token(client):
    assert client.post("/admin/live/reiniciar-capital?total_usd=2000").status_code == 401


def test_reiniciar_capital_live_rechaza_total_no_positivo(client):
    r = client.post("/admin/live/reiniciar-capital?total_usd=0", headers=HEADERS_OK)
    assert r.status_code == 400


def test_reiniciar_capital_live_reparte_por_bucket_e_invierte_en_blend(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))
    monkeypatch.setattr(live_engine, "load_state", lambda: {})

    def init_bucket_state_falso(bucket, starting_capital, ib):
        llamadas.setdefault("buckets", {})[bucket] = (starting_capital, ib)
        return {"starting_capital": round(starting_capital, 2), "cash": 0, "open_positions": []}

    guardados = {}
    monkeypatch.setattr(trading_api.live_engine, "init_bucket_state", init_bucket_state_falso)
    monkeypatch.setattr(trading_api.live_engine, "save_state", lambda state: guardados.setdefault("state", state))

    r = client.post("/admin/live/reiniciar-capital?total_usd=2000", headers=HEADERS_OK)

    assert r.status_code == 200
    assert set(llamadas["buckets"]) == {"largo_plazo", "mediano_plazo", "riesgo_alto"}
    assert llamadas["buckets"]["largo_plazo"][1] == "ib-falso"
    total_repartido = sum(cap for cap, _ in llamadas["buckets"].values())
    assert total_repartido == pytest.approx(2000.0)
    assert llamadas["desconectado"] == "ib-falso"
    assert guardados["state"] == r.json()


def test_reiniciar_capital_live_rechaza_si_hay_posiciones_abiertas(client, monkeypatch):
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)
    monkeypatch.setattr(
        live_engine,
        "load_state",
        lambda: {"largo_plazo": {"open_positions": [{"symbol": "SPY"}]}},
    )
    monkeypatch.setattr(
        trading_api.live_engine,
        "init_bucket_state",
        lambda *a, **kw: pytest.fail("no debería reinicializar si hay posiciones abiertas"),
    )

    r = client.post("/admin/live/reiniciar-capital?total_usd=2000", headers=HEADERS_OK)
    assert r.status_code == 409


def test_equity_live_requiere_token(client):
    assert client.get("/live/equity").status_code == 401


def test_equity_live_usa_usd_si_hay_segmento(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))
    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", lambda ib: 100000.0)
    monkeypatch.setattr(
        trading_api,
        "equity_de_cuenta",
        lambda ib: pytest.fail("no debería usarse MXN si equity_de_cuenta_usd ya respondió"),
    )

    r = client.get("/live/equity", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json() == {"equity_usd": 100000.0}
    assert llamadas["desconectado"] == "ib-falso"


def test_equity_live_cae_a_mxn_si_no_hay_segmento_usd(client, monkeypatch):
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)

    def sin_segmento_usd(ib):
        raise RuntimeError("No se encontró NetLiquidationByCurrency en USD")

    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", sin_segmento_usd)
    monkeypatch.setattr(trading_api, "equity_de_cuenta", lambda ib: 18866.36)
    monkeypatch.setattr(trading_api, "get_usd_mxn_rate", lambda: 18.4)

    r = client.get("/live/equity", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["equity_usd"] == pytest.approx(18866.36 / 18.4)


def test_equity_live_desconecta_aunque_falle(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", True))

    def falla(ib):
        raise RuntimeError("boom")

    monkeypatch.setattr(trading_api, "equity_de_cuenta_usd", falla)
    monkeypatch.setattr(trading_api, "equity_de_cuenta", falla)

    with pytest.raises(RuntimeError):
        client.get("/live/equity", headers=HEADERS_OK)

    assert llamadas.get("desconectado") is True


def test_fijar_estado_bucket_live_requiere_token(client):
    assert client.post("/admin/live/fijar-estado-bucket?bucket=largo_plazo&cash=100").status_code == 401


def test_fijar_estado_bucket_live_404_si_no_existe(client, monkeypatch):
    monkeypatch.setattr(live_engine, "load_state", lambda: {})
    r = client.post("/admin/live/fijar-estado-bucket?bucket=largo_plazo&cash=100", headers=HEADERS_OK)
    assert r.status_code == 404


def test_fijar_estado_bucket_live_rechaza_si_hay_posiciones_abiertas(client, monkeypatch):
    monkeypatch.setattr(
        live_engine, "load_state",
        lambda: {"largo_plazo": {"open_positions": [{"symbol": "SPY"}]}},
    )
    r = client.post("/admin/live/fijar-estado-bucket?bucket=largo_plazo&cash=100", headers=HEADERS_OK)
    assert r.status_code == 409


def test_fijar_estado_bucket_live_corrige_cash_y_shares(client, monkeypatch):
    guardados = {}
    monkeypatch.setattr(
        live_engine, "load_state",
        lambda: {"largo_plazo": {"cash": 866.67, "blend_spy_shares": 0, "blend_gld_shares": 0, "open_positions": []}},
    )
    monkeypatch.setattr(trading_api.live_engine, "save_state", lambda state: guardados.setdefault("state", state))

    r = client.post(
        "/admin/live/fijar-estado-bucket?bucket=largo_plazo&cash=490.55&blend_spy_shares=0&blend_gld_shares=1",
        headers=HEADERS_OK,
    )

    assert r.status_code == 200
    assert r.json() == {"cash": 490.55, "blend_spy_shares": 0, "blend_gld_shares": 1, "open_positions": []}
    assert guardados["state"]["largo_plazo"]["cash"] == 490.55


def test_limpiar_blend_ledger_live_requiere_token(client):
    assert client.post("/admin/live/limpiar-blend-ledger").status_code == 401


def test_limpiar_blend_ledger_live_vacia_el_archivo(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(
        trading_api.live_engine.blend_ledger, "save_ledger",
        lambda path, ledger: llamadas.setdefault("args", (path, ledger)),
    )

    r = client.post("/admin/live/limpiar-blend-ledger", headers=HEADERS_OK)

    assert r.status_code == 200
    assert llamadas["args"][1] == []


def test_blend_ledger_live_requiere_token(client):
    assert client.get("/live/blend-ledger").status_code == 401


def test_blend_ledger_live_devuelve_el_ledger(client, monkeypatch):
    renglones = [{"bucket": "largo_plazo", "simbolo": "GLD", "shares": 1}]
    monkeypatch.setattr(trading_api.live_engine.blend_ledger, "load_ledger", lambda path: renglones)

    r = client.get("/live/blend-ledger", headers=HEADERS_OK)
    assert r.status_code == 200
    assert r.json() == renglones


def test_liquidar_todo_live_requiere_token(client):
    assert client.post("/admin/live/liquidar-todo").status_code == 401


def test_liquidar_todo_live_vende_cada_posicion(client, monkeypatch):
    llamadas = []
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)
    monkeypatch.setattr(
        trading_api, "posiciones_reales_con_costo",
        lambda ib: {"AAPL": {"shares": 10, "avg_cost": 150.0}, "MSFT": {"shares": 0, "avg_cost": 0.0}},
    )

    def ejecutar_falso(ib, symbol, accion, shares):
        llamadas.append((symbol, accion, shares))
        from src.broker.ibkr_adapter import Fill
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=155.0)

    monkeypatch.setattr(trading_api, "ejecutar_orden_mercado", ejecutar_falso)

    r = client.post("/admin/live/liquidar-todo", headers=HEADERS_OK)

    assert r.status_code == 200
    assert llamadas == [("AAPL", "SELL", 10)]  # MSFT con 0 shares se ignora
    assert r.json()["AAPL"] == {"status": "vendido", "shares": 10, "precio": 155.0}


def test_liquidar_todo_live_reporta_falla_sin_detener_las_demas(client, monkeypatch):
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)
    monkeypatch.setattr(
        trading_api, "posiciones_reales_con_costo",
        lambda ib: {"AAPL": {"shares": 10, "avg_cost": 150.0}, "MSFT": {"shares": -5, "avg_cost": 300.0}},
    )

    def ejecutar_falso(ib, symbol, accion, shares):
        if symbol == "AAPL":
            raise trading_api.OrdenNoLlenada("AAPL SELL 10: estado final = 'Cancelled'")
        from src.broker.ibkr_adapter import Fill
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=300.0)

    monkeypatch.setattr(trading_api, "ejecutar_orden_mercado", ejecutar_falso)

    r = client.post("/admin/live/liquidar-todo", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["AAPL"]["status"] == "fallo"
    assert r.json()["MSFT"] == {"status": "vendido", "shares": 5, "precio": 300.0}


def test_vender_simbolo_live_requiere_token(client):
    assert client.post("/admin/live/vender-simbolo?symbol=FOXA&shares=1").status_code == 401


def test_vender_simbolo_live_vende_y_desconecta(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))

    def ejecutar_falso(ib, symbol, accion, shares):
        llamadas["orden"] = (symbol, accion, shares)
        from src.broker.ibkr_adapter import Fill
        return Fill(symbol=symbol, accion=accion, shares=shares, precio_promedio=42.0)

    monkeypatch.setattr(trading_api, "ejecutar_orden_mercado", ejecutar_falso)

    r = client.post("/admin/live/vender-simbolo?symbol=FOXA&shares=1", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json() == {"status": "vendido", "shares": 1, "precio": 42.0}
    assert llamadas["orden"] == ("FOXA", "SELL", 1)
    assert llamadas["desconectado"] == "ib-falso"


def test_vender_simbolo_live_reporta_encolada_en_vez_de_500(client, monkeypatch):
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: None)

    def orden_falla(ib, symbol, accion, shares):
        raise trading_api.OrdenNoLlenada("FOXA SELL 1: estado final = 'PreSubmitted'")

    monkeypatch.setattr(trading_api, "ejecutar_orden_mercado", orden_falla)

    r = client.post("/admin/live/vender-simbolo?symbol=FOXA&shares=1", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["status"] == "encolada_o_fallida"


def test_rebasar_y_recalcular_stops_live_requiere_token(client):
    assert client.post("/admin/live/rebasar-y-recalcular-stops").status_code == 401


def test_rebasar_y_recalcular_stops_live_delega_al_motor(client, monkeypatch):
    monkeypatch.setattr(
        trading_api.live_engine, "rebasar_y_recalcular_stops",
        lambda: {"largo_plazo": {"nuevo_starting_capital": 871.11, "stops_actualizados": []}},
    )

    r = client.post("/admin/live/rebasar-y-recalcular-stops", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json() == {"largo_plazo": {"nuevo_starting_capital": 871.11, "stops_actualizados": []}}


def test_posiciones_reales_live_requiere_token(client):
    assert client.get("/live/posiciones-reales").status_code == 401


def test_posiciones_reales_live_devuelve_posiciones_con_costo(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))
    monkeypatch.setattr(
        trading_api, "posiciones_reales_con_costo",
        lambda ib: {"AAPL": {"shares": 10, "avg_cost": 150.0}},
    )

    r = client.get("/live/posiciones-reales", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json() == {"AAPL": {"shares": 10, "avg_cost": 150.0}}
    assert llamadas["desconectado"] == "ib-falso"


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


def test_reconciliar_automatico_live_requiere_token(client):
    assert client.post("/admin/live/reconciliar-automatico").status_code == 401


def test_reconciliar_automatico_live_devuelve_lo_agregado(client, monkeypatch):
    llamadas = {}
    monkeypatch.setattr(trading_api, "conectar", lambda: "ib-falso")
    monkeypatch.setattr(trading_api, "desconectar", lambda ib: llamadas.setdefault("desconectado", ib))
    monkeypatch.setattr(
        trading_api.live_engine, "reconciliar_posiciones_automatico",
        lambda ib: {"largo_plazo": ["VOO"]},
    )

    r = client.post("/admin/live/reconciliar-automatico", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json() == {"largo_plazo": ["VOO"]}
    assert llamadas["desconectado"] == "ib-falso"


def test_exportar_live_requiere_token(client):
    assert client.get("/live/exportar").status_code == 401


def test_exportar_live_no_se_conecta_a_ibkr(client, monkeypatch):
    def falla_si_se_llama():
        raise AssertionError("exportar_live no debe conectarse a IBKR")

    monkeypatch.setattr(trading_api, "conectar", falla_si_se_llama)
    monkeypatch.setattr(
        "src.paper_trading.export_live.build_export_live",
        lambda: {"generated_at": "2026-01-01T00:00:00+00:00", "source": "motor EN VIVO", "buckets": {}},
    )

    r = client.get("/live/exportar", headers=HEADERS_OK)

    assert r.status_code == 200
    assert r.json()["buckets"] == {}
