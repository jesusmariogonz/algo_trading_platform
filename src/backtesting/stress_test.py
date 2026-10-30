"""Stress testing — dos pruebas distintas, ambas con datos/supuestos
honestos (no escenarios fabricados):

1. COSTOS ELEVADOS: re-corre el backtest multiplicando comisión y
   slippage (simula un bróker más caro, o condiciones de mercado con
   spreads anchos). Si la estrategia deja de ser rentable con 3-5x el
   costo base, su margen real es más frágil de lo que parece.

2. PEOR VENTANA HISTÓRICA REAL: encuentra la caída más grande de
   SPY (peak-to-trough) DENTRO de los datos que ya tenemos descargados
   (no asume "2022 fue el peor año" — lo calcula). Corre la estrategia
   solo en esa ventana. Con ~5 años de historia esto NO cubre crisis
   mayores (2008, COVID 2020) — se documenta explícitamente, no se
   finge que sí.

Uso:
    python -m src.backtesting.stress_test --strategy trend_following
"""

import argparse
import json
from datetime import datetime

import numpy as np
import pandas as pd

from src.backtesting.run import RESULTS_DIR, STRATEGIES, load_universe, run_backtest


def find_worst_drawdown_window(benchmark_df: pd.DataFrame) -> dict:
    """Encuentra la ventana peak-to-trough de mayor caída en los datos
    disponibles del benchmark (normalmente SPY)."""
    df = benchmark_df.sort_values("date").reset_index(drop=True)
    prices = df["adj_close"].values
    dates = df["date"].values

    running_max = np.maximum.accumulate(prices)
    drawdowns = (prices - running_max) / running_max

    trough_idx = int(np.argmin(drawdowns))
    # El pico es el último máximo histórico ANTES del valle.
    peak_idx = int(np.argmax(prices[: trough_idx + 1]))

    return {
        "peak_date": str(pd.Timestamp(dates[peak_idx]).date()),
        "trough_date": str(pd.Timestamp(dates[trough_idx]).date()),
        "drawdown_pct": round(float(drawdowns[trough_idx] * 100), 2),
    }


def summarize_results(results: dict) -> pd.DataFrame:
    rows = []
    for symbol, portfolio in results.items():
        stats = portfolio.stats()
        rows.append(
            {
                "symbol": symbol,
                "total_return_pct": round(float(stats.get("Total Return [%]", 0)), 2),
                "total_trades": int(stats.get("Total Trades", 0)),
            }
        )
    return pd.DataFrame(rows).sort_values("total_return_pct", ascending=False)


def run_elevated_costs(strategy_key: str, base_fees: float, base_slippage: float, multiplier: float) -> dict:
    results, params = run_backtest(strategy_key, base_fees * multiplier, base_slippage * multiplier)
    df = summarize_results(results)
    profitable = int((df["total_return_pct"] > 0).sum())
    return {
        "fees": base_fees * multiplier,
        "slippage": base_slippage * multiplier,
        "multiplier": multiplier,
        "symbols_profitable": profitable,
        "symbols_total": len(df),
        "avg_return_pct": round(float(df["total_return_pct"].mean()), 2) if not df.empty else None,
    }


def run_worst_window(strategy_key: str, fees: float, slippage: float, benchmark: str = "SPY") -> dict:
    universe = load_universe()
    if benchmark not in universe:
        raise SystemExit(f"'{benchmark}' no está en el universo descargado — no se puede calcular la ventana de estrés.")

    window = find_worst_drawdown_window(universe[benchmark])
    start, end = pd.Timestamp(window["peak_date"]), pd.Timestamp(window["trough_date"])

    sliced = {
        symbol: df[df["date"] <= end].copy()  # conserva historia previa para el calentamiento de indicadores
        for symbol, df in universe.items()
    }
    results, params = run_backtest(strategy_key, fees, slippage, universe=sliced)

    # Igual que en walk_forward.py: solo nos interesan operaciones DENTRO de la ventana de estrés.
    rows = []
    for symbol, portfolio in results.items():
        trades = portfolio.trades.records_readable
        in_window = trades[(trades["Entry Timestamp"] >= start) & (trades["Entry Timestamp"] <= end)]
        if in_window.empty:
            continue
        rows.append({"symbol": symbol, "trades": len(in_window), "total_return_pct_sum": float(in_window["Return"].sum() * 100)})

    df = pd.DataFrame(rows)
    return {
        "window": window,
        "total_trades": int(df["trades"].sum()) if not df.empty else 0,
        "symbols_with_trades": len(df),
        "avg_return_pct_per_symbol": round(float(df["total_return_pct_sum"].mean()), 2) if not df.empty else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, choices=STRATEGIES.keys())
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0005)
    args = parser.parse_args()

    print(f"\n=== Stress test: {args.strategy} ===\n")

    print("--- 1. Costos elevados ---")
    cost_results = []
    for mult in (1, 3, 5):
        r = run_elevated_costs(args.strategy, args.fees, args.slippage, mult)
        cost_results.append(r)
        print(
            f"  {mult}x costos (comisión {r['fees']*100:.3f}%, slippage {r['slippage']*100:.3f}%): "
            f"{r['symbols_profitable']}/{r['symbols_total']} símbolos rentables, "
            f"retorno promedio {r['avg_return_pct']}%"
        )

    print("\n--- 2. Peor ventana histórica real (SPY, dentro de los datos disponibles) ---")
    worst_window = run_worst_window(args.strategy, args.fees, args.slippage)
    w = worst_window["window"]
    print(f"  Ventana: {w['peak_date']} -> {w['trough_date']} (SPY cayó {w['drawdown_pct']}%)")
    print(f"  Operaciones en esa ventana: {worst_window['total_trades']} en {worst_window['symbols_with_trades']} símbolos")
    print(f"  Retorno promedio por símbolo en la ventana: {worst_window['avg_return_pct_per_symbol']}%")
    print(
        "\n  ⚠ Con ~5 años de historia esto NO cubre crisis mayores (2008, COVID 2020). "
        "No se debe interpretar como prueba de resistencia a una crisis severa."
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{run_id}_{args.strategy}_stresstest.json"
    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy_id": args.strategy,
                "elevated_costs": cost_results,
                "worst_window": worst_window,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
