import json

import pytest

from src.portfolio import allocation


@pytest.fixture(autouse=True)
def temp_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    monkeypatch.setattr(allocation, "LEDGER_PATH", path)
    yield path


def test_buckets_sum_to_100_percent():
    assert abs(sum(allocation.BUCKETS.values()) - 1.0) < 1e-9


def test_record_injection_splits_proportionally():
    entry = allocation.record_injection(1000, "2026-01-01")
    assert entry["split"]["largo_plazo"] == 400.0
    assert entry["split"]["mediano_plazo"] == 300.0
    assert entry["split"]["riesgo_alto"] == 200.0
    assert entry["split"]["muy_alta_volatilidad"] == 100.0
    assert sum(entry["split"].values()) == pytest.approx(1000.0)


def test_record_injection_rejects_non_positive_amount():
    with pytest.raises(ValueError):
        allocation.record_injection(0)
    with pytest.raises(ValueError):
        allocation.record_injection(-50)


def test_get_balances_accumulates_across_injections():
    allocation.record_injection(1000, "2026-01-01")
    allocation.record_injection(500, "2026-02-01")
    balances = allocation.get_balances()
    assert balances["largo_plazo"] == pytest.approx(600.0)  # 400 + 200
    assert balances["mediano_plazo"] == pytest.approx(450.0)  # 300 + 150


def test_ledger_persists_to_disk(temp_ledger):
    allocation.record_injection(100, "2026-01-01")
    assert temp_ledger.exists()
    data = json.loads(temp_ledger.read_text())
    assert len(data) == 1
    assert data[0]["amount"] == 100.0


def test_ledger_never_overwrites_previous_entries():
    allocation.record_injection(100, "2026-01-01")
    allocation.record_injection(200, "2026-01-02")
    ledger = allocation.load_ledger()
    assert len(ledger) == 2
    assert ledger[0]["amount"] == 100.0
    assert ledger[1]["amount"] == 200.0
