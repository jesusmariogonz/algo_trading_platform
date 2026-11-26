import pytest

from src.paper_trading import engine, live_engine


@pytest.fixture(autouse=True)
def _aislar_archivos_de_estado_en_vivo(tmp_path, monkeypatch):
    # Un test que olvide parchear estas rutas escribiría en el estado REAL
    # del motor (en la VM, /admin/desplegar corre pytest ahí): así se
    # contaminó el blend ledger con compras a $101 (ADR 0028, 0030).
    monkeypatch.setattr(live_engine, "LIVE_STATE_PATH", tmp_path / "live_state.json")
    monkeypatch.setattr(live_engine, "LIVE_HISTORY_PATH", tmp_path / "live_history.json")
    monkeypatch.setattr(live_engine, "LIVE_BLEND_LEDGER_PATH", tmp_path / "live_blend_ledger.json")
    monkeypatch.setattr(engine, "BLEND_LEDGER_PATH", tmp_path / "paper_blend_ledger.json")
