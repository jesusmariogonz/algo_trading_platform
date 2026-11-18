"""EXP-003 Capa 7 — Robustez a supuestos de ejecución (ver PREREGISTRATION.md).

Extiende el motor de simulación de harness.py (research/2026-11-
filtros-sizing-adr0033/harness.py) con dos supuestos pesimistas
combinados, sobre las 3 estrategias/buckets de producción:
  (a) llenado al OPEN del día siguiente a la señal (no al close del
      día de la señal — la señal solo se conoce al cierre, así que
      ejecutarla ese mismo close es optimista).
  (b) 2x la fricción actual (FRICCION_POR_LADO 0.001 -> 0.002).

NO importa ni modifica src/paper_trading/engine.py, live_engine.py ni
daily_signals.py — investigación pura, cero cambios de producción.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "2026-11-filtros-sizing-adr0033"))
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402

FRICCION_PESIMISTA = harness.FRICCION_POR_LADO * 2  # 0.002, supuesto (b)

CRITERIO = {
    "VALIDATED": "Sharpe>0 Y retorno neto positivo bajo AMBOS supuestos pesimistas combinados",
    "REJECTED": "Sharpe<=0 o retorno neto negativo bajo esos supuestos",
}


def _siguiente_dia_abierto(df_idx: pd.DataFrame, today: pd.Timestamp) -> pd.Timestamp | None:
    """Primer día de trading DESPUÉS de `today` en el índice de este
    símbolo, o None si `today` es el último día disponible."""
    pos = df_idx.index.get_indexer([today])[0]
    if pos == -1 or pos + 1 >= len(df_idx.index):
        return None
    return df_idx.index[pos + 1]


def simulate_bucket_fill_pesimista(
    universe: dict[str, pd.DataFrame],
    risk_pct: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    capital: float = 10_000.0,
    friccion: float = FRICCION_PESIMISTA,
) -> harness.SimResult:
    """Misma mecánica que harness.simulate_bucket (capital compartido,
    sizing por riesgo sobre equity actual, trailing stop) pero la
    señal detectada en el close de `today` se EJECUTA al open del
    siguiente día de trading (no al close de `today`) — si `today` es
    el último día de la ventana, esa operación se descarta (no hay
    día siguiente que ejecutarla, igual que pasaría en la realidad: la
    ventana de datos se acabó)."""
    idx = {s: df.set_index("date") for s, df in universe.items()}
    all_dates = sorted({d for df in idx.values() for d in df.index if start <= d <= end})

    cash = capital
    open_positions: dict[str, dict] = {}
    trades: list[harness.Trade] = []
    equity_rows = []

    for today in all_dates:
        # --- 1. detectar salidas en el close de hoy, ejecutar al open de mañana ---
        for symbol in list(open_positions):
            if symbol not in idx or today not in idx[symbol].index:
                continue
            row = idx[symbol].loc[today]
            pos = open_positions[symbol]
            pos["stop_price"] = max(pos["stop_price"], float(row["stop_price"]))
            close = float(row["close"])
            stop_hit = close <= pos["stop_price"]
            exit_signal = int(row["signal"]) == -1
            if not (stop_hit or exit_signal):
                continue

            siguiente = _siguiente_dia_abierto(idx[symbol], today)
            if siguiente is None or siguiente > end:
                continue  # sin día siguiente dentro de la ventana: no se puede ejecutar, se descarta

            exit_price = float(idx[symbol].loc[siguiente]["open"]) * (1 - friccion)
            proceeds = exit_price * pos["shares"]
            cost_entrada = pos["entry_price"] * pos["shares"]
            cash += proceeds
            trades.append(harness.Trade(
                symbol=symbol, entry_date=pos["entry_date"], exit_date=str(siguiente.date()),
                entry_price=pos["entry_price"], exit_price=exit_price, shares=pos["shares"],
                pnl=proceeds - cost_entrada, pnl_pct=(proceeds / cost_entrada - 1) * 100,
                multiplier=1.0,
            ))
            del open_positions[symbol]

        valor_posiciones = sum(
            float(idx[s].loc[today]["close"]) * p["shares"]
            for s, p in open_positions.items() if today in idx[s].index
        )
        equity_now = cash + valor_posiciones

        # --- 2. detectar entradas en el close de hoy, ejecutar al open de mañana ---
        for symbol, df in idx.items():
            if symbol in open_positions or today not in df.index:
                continue
            row = df.loc[today]
            if int(row["signal"]) != 1:
                continue
            siguiente = _siguiente_dia_abierto(df, today)
            if siguiente is None or siguiente > end:
                continue

            close = float(row["close"])
            stop_price = float(row["stop_price"])
            risk_per_share = close - stop_price  # el stop se fija con el dato conocido al momento de decidir
            if risk_per_share <= 0:
                continue
            risk_amount = equity_now * risk_pct
            shares = int(risk_amount // risk_per_share)
            if shares < 1:
                continue

            entry_price = float(df.loc[siguiente]["open"]) * (1 + friccion)
            cost = shares * entry_price
            if cost > cash:
                continue
            cash -= cost
            open_positions[symbol] = {
                "entry_date": str(siguiente.date()), "entry_price": entry_price,
                "stop_price": stop_price, "shares": shares,
            }

        valor_posiciones = sum(
            float(idx[s].loc[today]["close"]) * p["shares"]
            for s, p in open_positions.items() if today in idx[s].index
        )
        equity_rows.append({"date": today, "equity": cash + valor_posiciones})

    return harness.SimResult(equity_curve=pd.DataFrame(equity_rows), trades=trades)


def metrics_full_period(sim: harness.SimResult) -> dict:
    curve = sim.equity_curve
    if len(curve) < 2:
        return {"sharpe": None, "return_pct": None, "max_dd_pct": None, "n_trades": len(sim.trades)}
    rets = curve["equity"].pct_change().dropna()
    import numpy as np
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    return_pct = float((curve["equity"].iloc[-1] / curve["equity"].iloc[0] - 1) * 100)
    peak = curve["equity"].iloc[0]
    max_dd = 0.0
    for e in curve["equity"]:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    return {
        "sharpe": round(sharpe, 2), "return_pct": round(return_pct, 2),
        "max_dd_pct": round(max_dd * 100, 2), "n_trades": len(sim.trades),
    }


def clasificar(m_base: dict, m_pesimista: dict) -> str:
    if m_pesimista["sharpe"] is None:
        return "INCONCLUSIVE (datos insuficientes bajo supuestos pesimistas)"
    if m_pesimista["sharpe"] > 0 and (m_pesimista["return_pct"] or 0) > 0:
        return "VALIDATED"
    return "REJECTED"


def main():
    resultado = {}
    for bucket, cfg in harness.BUCKETS.items():
        universe = harness.signaled_universe(bucket)
        all_dates = sorted({d for df in universe.values() for d in df["date"]})
        start, end = all_dates[0], all_dates[-1]

        sim_base = harness.simulate_bucket(universe, cfg["risk_pct"], start, end, filter_fn=None)
        m_base = metrics_full_period(sim_base)

        sim_pesimista = simulate_bucket_fill_pesimista(universe, cfg["risk_pct"], start, end)
        m_pesimista = metrics_full_period(sim_pesimista)

        label = clasificar(m_base, m_pesimista)
        resultado[bucket] = {
            "periodo": {"start": str(start.date()), "end": str(end.date())},
            "baseline_close_mismo_dia": m_base,
            "pesimista_open_dia_siguiente_2x_friccion": m_pesimista,
            "label": label,
        }
        print(f"\n=== {bucket} ===")
        print(f"  Baseline (fill close, fricción normal): Sharpe={m_base['sharpe']}, "
              f"retorno={m_base['return_pct']}%, DD={m_base['max_dd_pct']}%, trades={m_base['n_trades']}")
        print(f"  Pesimista (fill open+1, 2x fricción):    Sharpe={m_pesimista['sharpe']}, "
              f"retorno={m_pesimista['return_pct']}%, DD={m_pesimista['max_dd_pct']}%, trades={m_pesimista['n_trades']}")
        print(f"  -> {label}")

    out_path = Path(__file__).parent / "resultados_capa7.json"
    out_path.write_text(json.dumps({"criterio": CRITERIO, "resultado": resultado}, indent=2, default=str))
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
