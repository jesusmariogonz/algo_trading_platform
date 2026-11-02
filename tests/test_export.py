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
