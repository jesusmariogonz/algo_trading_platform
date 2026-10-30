"""Backtest de Cross-Sectional Momentum — rebalanceo mensual de una
canasta equiponderada, no señales individuales por símbolo.

No reutiliza vectorbt.Portfolio.from_signals (pensado para una
posición por símbolo con entradas/salidas propias) porque esto es
fundamentalmente distinto: cada mes se selecciona un SUBCONJUNTO del
universo y se reparte el capital entre ellos por igual.

Mecánica:
  1. En cada fecha de rebalanceo (1er día de trading de cada mes),
     rankear el universo con rank_universe() y tomar los
     `selected=True` (top 20% por retorno de 6m, filtrados por SMA 200).
  2. Repartir el capital en partes iguales entre los seleccionados.
  3. Mantener hasta el siguiente rebalanceo; el retorno del período es
     el promedio simple de los retornos individuales (equiponderado).
  4. Aplicar un costo de turnover aproximado (no exacto: no rastrea
     posiciones individuales entre meses) en cada rebalanceo.

Uso:
    python -m src.backtesting.cross_sectional_backtest
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting.run import RESULTS_DIR, load_universe
from src.strategies.cross_sectional_momentum import CrossSectionalMomentumParams, rank_universe

TURNOVER_COST_PCT = 0.002  # aproximación: 0.2% del capital en cada rebalanceo (comisión + slippage de reconstruir la canasta)


def monthly_rebalance_dates(universe: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    all_dates = pd.concat([df["date"] for df in universe.values()]).drop_duplicates().sort_values()
    df = pd.DataFrame({"date": all_dates})
    df["month"] = df["date"].dt.to_period("M")
    return df.groupby("month")["date"].min().tolist()


def run_cross_sectional_backtest(params: CrossSectionalMomentumParams = CrossSectionalMomentumParams()):
    universe = load_universe()
    rebalance_dates = monthly_rebalance_dates(universe)

    monthly_returns = []
    holdings_log = []

    for i in range(len(rebalance_dates) - 1):
        as_of = rebalance_dates[i]
        next_rebalance = rebalance_dates[i + 1]

        ranking = rank_universe(universe, as_of, params)
        selected = ranking[ranking["selected"]]["symbol"].tolist() if not ranking.empty else []

        if not selected:
            monthly_returns.append({"date": as_of, "return": 0.0, "n_positions": 0})
            continue

        period_returns = []
        for symbol in selected:
            df = universe[symbol]
            window = df[(df["date"] >= as_of) & (df["date"] <= next_rebalance)]
            if len(window) < 2:
                continue
            start_price = window.iloc[0]["adj_close"]
            end_price = window.iloc[-1]["adj_close"]
            period_returns.append(end_price / start_price - 1)

        if not period_returns:
            monthly_returns.append({"date": as_of, "return": 0.0, "n_positions": 0})
            continue

        avg_return = float(np.mean(period_returns)) - TURNOVER_COST_PCT
        monthly_returns.append({"date": as_of, "return": avg_return, "n_positions": len(period_returns)})
        holdings_log.append({"date": str(as_of.date()), "selected": selected})

    returns_df = pd.DataFrame(monthly_returns)
    return returns_df, holdings_log, params


def summarize(returns_df: pd.DataFrame) -> dict:
    returns = returns_df["return"].values
    equity_curve = np.cumprod(1 + returns)
    total_return_pct = float((equity_curve[-1] - 1) * 100) if len(equity_curve) else 0.0

    n_months = len(returns)
    cagr_pct = (
        float(((equity_curve[-1]) ** (12 / n_months) - 1) * 100) if n_months > 0 and equity_curve[-1] > 0 else None
    )

    running_max = np.maximum.accumulate(equity_curve) if len(equity_curve) else np.array([1.0])
    drawdowns = (equity_curve - running_max) / running_max if len(equity_curve) else np.array([0.0])
    max_drawdown_pct = float(drawdowns.min() * 100) if len(drawdowns) else 0.0

    sharpe = None
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(12))

    return {
        "n_months": n_months,
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2) if cagr_pct is not None else None,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio_annualized": round(sharpe, 2) if sharpe is not None else None,
        "avg_positions_per_month": round(float(returns_df["n_positions"].mean()), 1),
    }


def benchmark_spy(universe: dict[str, pd.DataFrame]) -> dict:
    if "SPY" not in universe:
        return {}
    df = universe["SPY"].dropna(subset=["adj_close"])
    start_price = df.iloc[0]["adj_close"]
    end_price = df.iloc[-1]["adj_close"]
    total_return_pct = float((end_price / start_price - 1) * 100)
    years = (df.iloc[-1]["date"] - df.iloc[0]["date"]).days / 365.25
    cagr_pct = float(((end_price / start_price) ** (1 / years) - 1) * 100) if years > 0 else None
    return {"total_return_pct": round(total_return_pct, 2), "cagr_pct": round(cagr_pct, 2) if cagr_pct else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-pct", type=float, default=0.20)
    args = parser.parse_args()

    params = CrossSectionalMomentumParams(top_pct=args.top_pct)
    returns_df, holdings_log, params = run_cross_sectional_backtest(params)
    summary = summarize(returns_df)
    universe = load_universe()
    spy_benchmark = benchmark_spy(universe)

    print(f"\n=== Cross-Sectional Momentum — top {params.top_pct*100:.0f}%, rebalanceo mensual ===")
    print(f"Costo de turnover aproximado por mes: {TURNOVER_COST_PCT*100:.2f}%\n")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if spy_benchmark:
        print(f"\n  Benchmark SPY (buy & hold, mismo período): {spy_benchmark}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{run_id}_{params.id}.json"
    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy_id": params.id,
                "strategy_version": params.version,
                "params": params.__dict__,
                "turnover_cost_pct": TURNOVER_COST_PCT,
                "summary": summary,
                "benchmark_spy": spy_benchmark,
                "monthly_returns": returns_df.assign(date=returns_df["date"].astype(str)).to_dict(orient="records"),
                "holdings_log": holdings_log,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
