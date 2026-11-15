import pandas as pd
import pytest

from src.paper_trading import engine
from src.screening.daily_signals import BUCKET_CONFIG


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(engine, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(engine, "BLEND_LEDGER_PATH", tmp_path / "blend_ledger.json")
    yield


def test_bucket_config_sin_estrategia_ni_riesgo():
    config = BUCKET_CONFIG["benchmark_diversificado"]
    assert config["strategies"] == []
    assert config["risk_pct"] == 0.0


def test_pesos_del_blend_diversificado_suman_uno():
    assert sum(engine.BENCHMARK_DIVERSIFICADO_WEIGHTS.values()) == pytest.approx(1.0)
    assert engine.BENCHMARK_SYMBOL["benchmark_diversificado"] == "BLEND_DIVERSIFICADO"
    assert engine.BLEND_DEFINITIONS["BLEND_DIVERSIFICADO"] == engine.BENCHMARK_DIVERSIFICADO_WEIGHTS


def _universo_4_activos(fechas, spy, agg, gld, vnq):
    fechas = pd.to_datetime(fechas)
    return {
        "SPY": pd.DataFrame({"date": fechas, "close": spy}),
        "AGG": pd.DataFrame({"date": fechas, "close": agg}),
        "GLD": pd.DataFrame({"date": fechas, "close": gld}),
        "VNQ": pd.DataFrame({"date": fechas, "close": vnq}),
    }


def test_blend_diversificado_pondera_los_4_activos_correctamente(monkeypatch):
    universo = _universo_4_activos(
        ["2026-01-01", "2026-01-02"],
        spy=[100.0, 110.0],  # +10%
        agg=[100.0, 100.0],  # +0%
        gld=[100.0, 90.0],  # -10%
        vnq=[100.0, 120.0],  # +20%
    )
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo[s] for s in symbols})

    bucket_state = {}
    precio_dia1 = engine._blend_incremental_price(
        bucket_state, pd.Timestamp("2026-01-01"), engine.BENCHMARK_DIVERSIFICADO_WEIGHTS
    )
    assert precio_dia1 == pytest.approx(100.0)

    precio_dia2 = engine._blend_incremental_price(
        bucket_state, pd.Timestamp("2026-01-02"), engine.BENCHMARK_DIVERSIFICADO_WEIGHTS
    )
    # 40%*10% + 30%*0% + 20%*(-10%) + 10%*20% = 4% + 0% - 2% + 2% = 4%
    assert precio_dia2 == pytest.approx(104.0)


def test_benchmark_diversificado_nunca_abre_ni_cierra_posiciones(monkeypatch):
    """Es una canasta de 'comprar y mantener': sin estrategias (BUCKET_CONFIG),
    el 100% de su capital se queda siempre en el blend, pase lo que pase con
    los precios — nunca debe aparecer una posición abierta ni cerrada."""
    universo = _universo_4_activos(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        spy=[100.0, 90.0, 120.0],
        agg=[100.0, 95.0, 105.0],
        gld=[100.0, 110.0, 90.0],
        vnq=[100.0, 80.0, 130.0],
    )
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo[s] for s in symbols})
    monkeypatch.setattr(engine, "read_universe_file", lambda path: ["SPY"])
    monkeypatch.setattr(engine, "BUCKET_CONFIG", {
        "benchmark_diversificado": {
            "universe_file": "irrelevante.txt",
            "risk_pct": 0.0,
            "strategies": [],
        },
    })

    state = engine.init_bucket_state("benchmark_diversificado", 1000.0, pd.Timestamp("2026-01-01"))
    for dia in ("2026-01-02", "2026-01-03"):
        resultado = engine.run_bucket_tick("benchmark_diversificado", state, pd.Timestamp(dia))
        assert resultado["open_count"] == 0
        assert resultado["closed_today"] == 0
        assert resultado["discarded_candidates_today"] == []

    # Todo el capital sigue en el blend (nunca se movió a cash ni a una
    # posición): equity == bench_shares marcadas al precio final.
    precio_final = engine._blend_incremental_price(
        state, pd.Timestamp("2026-01-03"), engine.BENCHMARK_DIVERSIFICADO_WEIGHTS
    )
    assert resultado["equity"] == pytest.approx(state["bench_shares"] * precio_final, rel=1e-6)


def test_benchmark_symbol_spy_gld_existente_sigue_funcionando(monkeypatch):
    """Regresión: generalizar _blend_incremental_price para aceptar pesos
    por parámetro (ADR 0039) no debe cambiar el comportamiento default
    (BLEND_SPY_GLD) de los 3 buckets ya en producción."""
    universo = {
        "SPY": pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [100.0]}),
        "GLD": pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [50.0]}),
    }
    monkeypatch.setattr(engine, "load_universe", lambda symbols=None: {s: universo[s] for s in symbols})
    precio = engine._benchmark_price("largo_plazo", {}, pd.Timestamp("2026-01-01"))
    assert precio == pytest.approx(100.0)
