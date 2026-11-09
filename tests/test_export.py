import pandas as pd
import pytest

from src.paper_trading import export


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    from src.paper_trading import engine

    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    yield


def test_con_precio_en_vivo_agrega_precio_y_pnl_no_realizado(monkeypatch):
    fake_universe = {
        "AAPL": pd.DataFrame({"date": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")], "close": [100.0, 110.0]}),
    }
    monkeypatch.setattr(export, "load_universe", lambda symbols=None: fake_universe)

    open_positions = [{"symbol": "AAPL", "entry_date": "2025-12-01", "entry_price": 100.0, "stop_price": 90.0, "shares": 2}]
    resultado = export._con_precio_en_vivo(open_positions)

    assert resultado[0]["current_price"] == 110.0
    assert resultado[0]["unrealized_pnl"] == pytest.approx(20.0)  # (110-100)*2
    assert resultado[0]["unrealized_pnl_pct"] == pytest.approx(10.0)


def test_con_precio_en_vivo_no_falla_si_faltan_datos_de_un_simbolo(monkeypatch):
    def load_universe_falla(symbols=None):
        raise SystemExit("faltan datos procesados")

    monkeypatch.setattr(export, "load_universe", load_universe_falla)

    open_positions = [{"symbol": "ZZZ", "entry_date": "2025-12-01", "entry_price": 50.0, "stop_price": 45.0, "shares": 1}]
    resultado = export._con_precio_en_vivo(open_positions)

    assert resultado == open_positions  # se exporta sin precio en vivo, no truena


def test_con_precio_en_vivo_respeta_lista_vacia():
    assert export._con_precio_en_vivo([]) == []


def test_tipo_de_cambio_hoy_incluye_rate_real(monkeypatch):
    monkeypatch.setattr(export, "get_usd_mxn_rate", lambda: 18.5)
    resultado = export._tipo_de_cambio_hoy()
    assert resultado["usd_mxn_rate"] == 18.5
    assert resultado["usd_mxn_rate_fecha"] is not None


def test_tipo_de_cambio_hoy_no_inventa_rate_si_la_api_falla(monkeypatch):
    def falla():
        raise ConnectionError("simulado")

    monkeypatch.setattr(export, "get_usd_mxn_rate", falla)
    resultado = export._tipo_de_cambio_hoy()
    assert resultado["usd_mxn_rate"] is None
    assert resultado["usd_mxn_rate_fecha"] is None


def test_build_export_incluye_campos_de_tipo_de_cambio(monkeypatch):
    monkeypatch.setattr(export, "get_usd_mxn_rate", lambda: 18.5)
    from src.paper_trading import engine

    engine.save_state({})
    resultado = export.build_export()
    assert resultado["usd_mxn_rate"] == 18.5
    assert "usd_mxn_rate_fecha" in resultado


def _buckets_con_una_abierta_y_una_cerrada():
    return {
        "largo_plazo": {
            "open_positions": [
                {"symbol": "AAPL", "entry_date": "2026-01-01", "entry_price": 100.0,
                 "initial_stop_price": 90.0, "stop_price": 95.0, "current_price": 102.0,
                 "unrealized_pnl": 4.0, "unrealized_pnl_pct": 2.0, "asset_type": "Stock"},
            ],
            "closed_positions": [
                {"symbol": "MSFT", "entry_date": "2025-12-01", "entry_price": 50.0,
                 "exit_date": "2026-01-05", "exit_price": 45.0, "stop_price": 45.0,
                 "pnl": -5.0, "pnl_pct": -10.0, "reason": "stop_hit", "asset_type": "Stock"},
            ],
        }
    }


def test_append_historico_crea_archivo_nuevo(tmp_path):
    destino = tmp_path / "historico.json"
    filas = export.append_historico(_buckets_con_una_abierta_y_una_cerrada(), destino)

    assert destino.exists()
    assert len(filas) == 2
    abierta = next(f for f in filas if f["symbol"] == "AAPL")
    cerrada = next(f for f in filas if f["symbol"] == "MSFT")
    assert abierta["estado"] == "Abierta"
    assert abierta["pnl"] == 4.0
    assert cerrada["estado"] == "Cerrada"
    assert cerrada["pnl"] == -5.0
    assert cerrada["reason"] == "stop_hit"


def test_append_historico_actualiza_posicion_abierta_sin_duplicar(tmp_path):
    destino = tmp_path / "historico.json"
    export.append_historico(_buckets_con_una_abierta_y_una_cerrada(), destino)

    buckets_actualizados = _buckets_con_una_abierta_y_una_cerrada()
    buckets_actualizados["largo_plazo"]["open_positions"][0]["current_price"] = 110.0
    buckets_actualizados["largo_plazo"]["open_positions"][0]["unrealized_pnl"] = 20.0

    filas = export.append_historico(buckets_actualizados, destino)
    assert len(filas) == 2  # sigue habiendo 2 filas, no se duplicó
    abierta = next(f for f in filas if f["symbol"] == "AAPL")
    assert abierta["current_price"] == 110.0
    assert abierta["pnl"] == 20.0


def test_append_historico_preserva_filas_viejas_que_ya_no_vienen_en_el_export(tmp_path):
    destino = tmp_path / "historico.json"
    export.append_historico(_buckets_con_una_abierta_y_una_cerrada(), destino)

    # una corrida futura donde la posición de largo_plazo ya no aparece
    # (ej. bucket vacío momentáneamente) no debe borrar el histórico ya escrito
    filas = export.append_historico({"largo_plazo": {"open_positions": [], "closed_positions": []}}, destino)
    assert len(filas) == 2


def test_append_historico_ignora_archivo_corrupto(tmp_path):
    destino = tmp_path / "historico.json"
    destino.write_text("esto no es json valido")

    filas = export.append_historico(_buckets_con_una_abierta_y_una_cerrada(), destino)
    assert len(filas) == 2


def _buckets_para_bitacora():
    return {
        "largo_plazo": {
            "starting_capital": 1000.0,
            "open_positions": [{"symbol": "AAPL"}, {"symbol": "NVDA"}],
            "closed_positions": [{"symbol": "MSFT", "pnl": 10.0}, {"symbol": "TSLA", "pnl": -5.0}],
            "daily_history": [{"equity": 1050.0, "cumulative_return_pct": 5.0, "drawdown_pct": 1.2}],
            "suspended": False,
        },
        "riesgo_alto": {
            "starting_capital": 500.0,
            "open_positions": [],
            "closed_positions": [],
            "daily_history": [],
            "suspended": False,
        },
    }


def test_append_bitacora_crea_un_renglon_por_bucket(tmp_path):
    destino = tmp_path / "bitacora.json"
    filas = export.append_bitacora(_buckets_para_bitacora(), destino, fecha="2026-11-09")

    assert len(filas) == 2
    largo = next(f for f in filas if f["bucket"] == "largo_plazo")
    assert largo["equity"] == 1050.0
    assert largo["ganancia_perdida"] == 50.0
    assert largo["retorno_pct"] == 5.0
    assert largo["abiertas"] == 2
    assert largo["cerradas"] == 2
    assert largo["win_rate_pct"] == 50.0

    riesgo = next(f for f in filas if f["bucket"] == "riesgo_alto")
    assert riesgo["equity"] == 500.0  # sin daily_history, usa starting_capital
    assert riesgo["win_rate_pct"] is None  # sin cerradas, no hay win rate


def test_append_bitacora_no_duplica_el_mismo_dia(tmp_path):
    destino = tmp_path / "bitacora.json"
    export.append_bitacora(_buckets_para_bitacora(), destino, fecha="2026-11-09")

    buckets_tarde = _buckets_para_bitacora()
    buckets_tarde["largo_plazo"]["daily_history"] = [{"equity": 1080.0, "cumulative_return_pct": 8.0, "drawdown_pct": 0.5}]
    filas = export.append_bitacora(buckets_tarde, destino, fecha="2026-11-09")

    assert len(filas) == 2  # sigue siendo 1 renglón por bucket ese día
    largo = next(f for f in filas if f["bucket"] == "largo_plazo")
    assert largo["equity"] == 1080.0  # la corrida de la tarde actualizó el renglón de hoy


def test_append_bitacora_acumula_dias_distintos(tmp_path):
    destino = tmp_path / "bitacora.json"
    export.append_bitacora(_buckets_para_bitacora(), destino, fecha="2026-11-06")
    filas = export.append_bitacora(_buckets_para_bitacora(), destino, fecha="2026-11-09")

    assert len(filas) == 4  # 2 buckets x 2 días distintos


def test_append_bitacora_ignora_archivo_corrupto(tmp_path):
    destino = tmp_path / "bitacora.json"
    destino.write_text("esto no es json valido")

    filas = export.append_bitacora(_buckets_para_bitacora(), destino, fecha="2026-11-09")
    assert len(filas) == 2
