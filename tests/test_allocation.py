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
    # 3 buckets (ADR 0027 — Mean Reversion RSI(2) eliminado), 13/10/7.
    entry = allocation.record_injection(1000, "2026-01-01")
    assert entry["split"]["largo_plazo"] == pytest.approx(433.33, abs=0.01)
    assert entry["split"]["mediano_plazo"] == pytest.approx(333.33, abs=0.01)
    assert entry["split"]["riesgo_alto"] == pytest.approx(233.33, abs=0.01)
    assert sum(entry["split"].values()) == pytest.approx(1000.0, abs=0.01)


def test_record_injection_rejects_non_positive_amount():
    with pytest.raises(ValueError):
        allocation.record_injection(0)
    with pytest.raises(ValueError):
        allocation.record_injection(-50)


def test_get_balances_accumulates_across_injections():
    allocation.record_injection(1000, "2026-01-01")
    allocation.record_injection(500, "2026-02-01")
    balances = allocation.get_balances()
    assert balances["largo_plazo"] == pytest.approx(650.0)  # 43.33% de 1500
    assert balances["mediano_plazo"] == pytest.approx(500.0)  # 33.33% de 1500


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


def test_record_injection_mxn_converts_and_records_rate(monkeypatch):
    monkeypatch.setattr(allocation, "get_usd_mxn_rate", lambda: 20.0)
    entry = allocation.record_injection_mxn(3000, "2026-01-01")

    assert entry["original_currency"] == "MXN"
    assert entry["original_amount"] == 3000.0
    assert entry["exchange_rate"] == 20.0
    assert entry["amount"] == pytest.approx(150.0)  # 3000 / 20
    assert entry["split"]["largo_plazo"] == pytest.approx(65.0, abs=0.01)  # 43.33% de 150


def test_record_injection_without_mxn_has_no_currency_fields():
    entry = allocation.record_injection(100, "2026-01-01")
    assert "original_currency" not in entry


def test_get_usd_mxn_rate_raises_on_api_failure(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise ConnectionError("simulated network failure")

    monkeypatch.setattr(allocation.requests, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(ConnectionError):
        allocation.get_usd_mxn_rate()


def test_get_usd_mxn_rate_raises_if_mxn_missing(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": "success", "rates": {"EUR": 0.9}}

    monkeypatch.setattr(allocation.requests, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(RuntimeError):
        allocation.get_usd_mxn_rate()
