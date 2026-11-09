import pytest

from src.paper_trading import export_live


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    from src.paper_trading import live_engine

    monkeypatch.setattr(live_engine, "LIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(live_engine, "LIVE_HISTORY_PATH", tmp_path / "history.json")
    yield


def test_build_export_live_usa_el_estado_del_motor_en_vivo(monkeypatch):
    from src.paper_trading import live_engine

    live_engine.save_state({
        "largo_plazo": {
            "starting_capital": 1000.0,
            "open_positions": [],
            "closed_positions": [{"symbol": "AAPL", "entry_date": "2026-01-01", "entry_price": 100.0,
                                   "exit_date": "2026-01-05", "exit_price": 110.0, "shares": 1,
                                   "pnl": 10.0, "pnl_pct": 10.0, "reason": "signal_exit", "stop_price": 95.0}],
            "suspended": False,
        }
    })

    resultado = export_live.build_export_live()

    assert "generado" not in resultado  # no se inventa un campo que no existe
    assert resultado["source"].startswith("algo_trading_platform motor EN VIVO")
    assert resultado["buckets"]["largo_plazo"]["starting_capital"] == 1000.0
    assert len(resultado["buckets"]["largo_plazo"]["closed_positions"]) == 1
    assert resultado["buckets"]["largo_plazo"]["closed_positions"][0]["asset_type"] == "Stock"


def test_main_escribe_snapshot_historico_y_bitacora(tmp_path, monkeypatch):
    from src.paper_trading import live_engine

    live_engine.save_state({
        "largo_plazo": {
            "starting_capital": 500.0,
            "open_positions": [],
            "closed_positions": [{"symbol": "MSFT", "entry_date": "2026-01-01", "entry_price": 50.0,
                                   "exit_date": "2026-01-02", "exit_price": 45.0, "shares": 1,
                                   "pnl": -5.0, "pnl_pct": -10.0, "reason": "stop_hit", "stop_price": 45.0}],
            "suspended": False,
        }
    })

    snapshot_path = tmp_path / "snapshot.json"
    historico_path = tmp_path / "historico.json"
    bitacora_path = tmp_path / "bitacora.json"
    monkeypatch.setattr("sys.argv", ["export_live.py", str(snapshot_path), str(historico_path), str(bitacora_path)])

    export_live.main()

    assert snapshot_path.exists()
    assert historico_path.exists()
    assert bitacora_path.exists()
