"""Backtest de una estrategia sobre todo el universo procesado.

Incluye comisiones y slippage básicos (configurables por CLI).
Guarda los parámetros de cada corrida junto con sus métricas en
src/backtesting/results/<timestamp>_<strategy_id>.json para que cada
experimento sea reproducible (ver docs/vision.md § 5, "Backtesting").

Uso:
    python -m src.backtesting.run --strategy trend_following
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import vectorbt as vbt

from src.strategies.trend_following import TrendFollowingParams, generate_signals

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

STRATEGIES = {
    "trend_following": (TrendFollowingParams, generate_signals),
}


def load_universe() -> dict[str, pd.DataFrame]:
    files = sorted(PROCESSED_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit(
            "No hay datos procesados. Corre primero:\n"
            "  python -m src.data.download\n"
            "  python -m src.indicators.compute"
        )
    return {f.stem: pd.read_parquet(f) for f in files}


def run_backtest(strategy_key: str, fees: float, slippage: float):
    params_cls, signal_fn = STRATEGIES[strategy_key]
    params = params_cls()
    universe = load_universe()

    results = {}
    for symbol, df in universe.items():
        df = signal_fn(df, params)
        df = df.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
        if df.empty:
            continue

        close = df.set_index("date")["close"]
        entries = df.set_index("date")["signal"] == 1
        exits = df.set_index("date")["signal"] == -1

        portfolio = vbt.Portfolio.from_signals(
            close,
            entries,
            exits,
            fees=fees,
            slippage=slippage,
            freq="1D",
        )
        results[symbol] = portfolio

    return results, params


def summarize(results: dict, params) -> dict:
    rows = []
    for symbol, portfolio in results.items():
        stats = portfolio.stats()
        rows.append(
            {
                "symbol": symbol,
                "total_return_pct": round(float(stats.get("Total Return [%]", 0)), 2),
                "sharpe_ratio": round(float(stats.get("Sharpe Ratio", 0)), 2),
                "max_drawdown_pct": round(float(stats.get("Max Drawdown [%]", 0)), 2),
                "win_rate_pct": round(float(stats.get("Win Rate [%]", 0)), 2),
                "total_trades": int(stats.get("Total Trades", 0)),
            }
        )
    summary_df = pd.DataFrame(rows).sort_values("total_return_pct", ascending=False)
    return summary_df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, choices=STRATEGIES.keys())
    parser.add_argument("--fees", type=float, default=0.0005, help="comisión por operación (fracción, ej. 0.0005 = 5 bps)")
    parser.add_argument("--slippage", type=float, default=0.0005, help="slippage estimado (fracción)")
    args = parser.parse_args()

    results, params = run_backtest(args.strategy, args.fees, args.slippage)
    summary_df = summarize(results, params)

    print(f"\n=== Backtest: {params.name} (v{params.version}) ===")
    print(f"Comisión: {args.fees*100:.3f}% · Slippage: {args.slippage*100:.3f}%\n")
    print(summary_df.to_string(index=False))

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
                "fees": args.fees,
                "slippage": args.slippage,
                "universe_size": len(results),
                "summary": summary_df.to_dict(orient="records"),
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
