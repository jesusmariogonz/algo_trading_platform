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

from src.strategies.momentum_breakout import MomentumBreakoutParams
from src.strategies.momentum_breakout import generate_signals as momentum_breakout_signals
from src.strategies.trend_following import TrendFollowingParams
from src.strategies.trend_following import generate_signals as trend_following_signals

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

STRATEGIES = {
    "trend_following": (TrendFollowingParams, trend_following_signals),
    "momentum_breakout": (MomentumBreakoutParams, momentum_breakout_signals),
}


def load_universe(symbols: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Si `symbols` se da, solo carga esos símbolos (deben tener Parquet
    ya procesado) — lo usa daily_signals.py para limitar el universo
    por bucket (ej. Riesgo Alto vs. Mediano Plazo)."""
    files = sorted(PROCESSED_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit(
            "No hay datos procesados. Corre primero:\n"
            "  python -m src.data.download\n"
            "  python -m src.indicators.compute"
        )
    universe = {f.stem: pd.read_parquet(f) for f in files}
    if symbols is not None:
        faltantes = set(symbols) - set(universe)
        if faltantes:
            raise SystemExit(
                f"Faltan datos procesados para: {', '.join(sorted(faltantes))}. "
                "Corre src.data.download con ese universo primero."
            )
        universe = {s: universe[s] for s in symbols}
    return universe


def backtest_symbol(df: pd.DataFrame, params, signal_fn, fees: float, slippage: float):
    """Genera señales y corre vectorbt sobre un único símbolo.
    Devuelve None si, tras recortar el período de calentamiento de los
    indicadores, no queda suficiente historia para operar.
    """
    df = signal_fn(df, params)
    df = df.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
    if df.empty:
        return None

    close = df.set_index("date")["close"]
    entries = df.set_index("date")["signal"] == 1
    exits = df.set_index("date")["signal"] == -1

    return vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        fees=fees,
        slippage=slippage,
        freq="1D",
    )


def run_backtest(
    strategy_key: str,
    fees: float,
    slippage: float,
    universe: dict[str, pd.DataFrame] | None = None,
):
    """Corre una estrategia sobre todo el universo (o uno ya recortado
    por fecha, si `universe` viene dado — lo usa walk_forward.py).
    """
    params_cls, signal_fn = STRATEGIES[strategy_key]
    params = params_cls()
    if universe is None:
        universe = load_universe()

    results = {}
    for symbol, df in universe.items():
        portfolio = backtest_symbol(df, params, signal_fn, fees, slippage)
        if portfolio is not None:
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
