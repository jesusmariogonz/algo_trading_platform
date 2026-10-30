"""Simulación Monte Carlo sobre la secuencia de operaciones de un
backtest — responde: "¿qué tan sensible es el resultado al ORDEN en
que cayeron las operaciones ganadoras y perdedoras?"

Mecánica: junta todas las operaciones (de todos los símbolos) de un
backtest ya corrido en una sola bolsa de retornos por operación.
Genera N secuencias aleatorias (remuestreo CON reemplazo, del mismo
tamaño que la secuencia original) y para cada una calcula el retorno
acumulado y el max drawdown. Reporta la distribución (percentiles),
no un único número.

LIMITACIÓN IMPORTANTE, no ocultarla: este método asume que las
operaciones son independientes e idénticamente distribuidas — ignora
que el mercado tiene regímenes (una racha perdedora real suele
concentrarse en un período malo del mercado, no distribuirse al
azar). Es una prueba de "riesgo de secuencia", no un reemplazo del
walk-forward (que sí prueba estabilidad a través del tiempo real).

Uso:
    python -m src.backtesting.monte_carlo --strategy trend_following --simulations 1000
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from src.backtesting.run import RESULTS_DIR, STRATEGIES, run_backtest

RNG_SEED = 42  # reproducibilidad del experimento — ver docs/vision.md § 5


def collect_trade_returns(results: dict) -> list[float]:
    """Junta los retornos de TODAS las operaciones de TODOS los
    símbolos del backtest en una sola lista (la "bolsa" de donde se
    remuestrea)."""
    returns = []
    for portfolio in results.values():
        trades = portfolio.trades.records_readable
        returns.extend(trades["Return"].tolist())
    return returns


def simulate(
    trade_returns: list[float],
    n_simulations: int,
    position_size_pct: float = 0.10,
    seed: int = RNG_SEED,
) -> dict:
    """IMPORTANTE: cada valor en `trade_returns` es el retorno de ESA
    posición individual (ej. +423% en una sola operación de NVDA) tal
    como lo reporta vectorbt, que simula cada símbolo con 100% de un
    capital aislado — no el impacto real de esa operación sobre tu
    cuenta total.

    Componer esos retornos completos secuencialmente (como si cada
    operación fuera el 100% de tu cuenta, una tras otra) produce
    números sin sentido (capital creciendo millones de %), porque en
    la práctica real mantienes VARIAS posiciones a la vez, cada una
    con una fracción del capital.

    `position_size_pct` aproxima esa fracción (default 10% ≈ asumir
    ~10 posiciones concurrentes en promedio, razonable para un
    universo de 12-30 símbolos con señales no sincronizadas). Es una
    simplificación declarada, no una medición exacta de tu exposición
    real — eso requeriría el Portfolio Management real (Fase 1+)."""
    if len(trade_returns) < 5:
        raise SystemExit(
            f"Solo hay {len(trade_returns)} operaciones en el backtest — muy pocas para "
            "que un remuestreo Monte Carlo diga algo útil (mínimo razonable: ~20-30)."
        )

    rng = np.random.default_rng(seed)
    returns_arr = np.array(trade_returns) * position_size_pct
    n_trades = len(returns_arr)

    final_returns = np.empty(n_simulations)
    max_drawdowns = np.empty(n_simulations)

    for i in range(n_simulations):
        sample = rng.choice(returns_arr, size=n_trades, replace=True)
        equity_curve = np.cumprod(1 + sample)
        final_returns[i] = equity_curve[-1] - 1

        running_max = np.maximum.accumulate(equity_curve)
        drawdowns = (equity_curve - running_max) / running_max
        max_drawdowns[i] = drawdowns.min()

    def pct(arr, p):
        return float(np.percentile(arr, p))

    return {
        "n_trades_in_sample": n_trades,
        "n_simulations": n_simulations,
        "total_return_pct": {
            "p5": round(pct(final_returns, 5) * 100, 2),
            "p25": round(pct(final_returns, 25) * 100, 2),
            "p50_mediana": round(pct(final_returns, 50) * 100, 2),
            "p75": round(pct(final_returns, 75) * 100, 2),
            "p95": round(pct(final_returns, 95) * 100, 2),
            "pct_simulaciones_positivas": round(float((final_returns > 0).mean() * 100), 1),
        },
        "max_drawdown_pct": {
            "p5_peor_caso": round(pct(max_drawdowns, 5) * 100, 2),
            "p50_mediana": round(pct(max_drawdowns, 50) * 100, 2),
            "p95_mejor_caso": round(pct(max_drawdowns, 95) * 100, 2),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, choices=STRATEGIES.keys())
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0005)
    parser.add_argument(
        "--position-size-pct",
        type=float,
        default=0.10,
        help="fracción del capital total que representa cada operación (ver docstring de simulate())",
    )
    args = parser.parse_args()

    results, params = run_backtest(args.strategy, args.fees, args.slippage)
    trade_returns = collect_trade_returns(results)
    sim = simulate(trade_returns, args.simulations, args.position_size_pct)

    print(f"\n=== Monte Carlo: {params.name} — {args.simulations} simulaciones sobre {sim['n_trades_in_sample']} operaciones ===")
    print(
        f"⚠ Asume operaciones independientes y ~{1/args.position_size_pct:.0f} posiciones "
        f"concurrentes ({args.position_size_pct*100:.0f}% de capital c/u) — no reemplaza al "
        "walk-forward (ver docstring del módulo).\n"
    )
    print("Retorno total acumulado (distribución):")
    for k, v in sim["total_return_pct"].items():
        print(f"  {k}: {v}")
    print("\nMax drawdown (distribución):")
    for k, v in sim["max_drawdown_pct"].items():
        print(f"  {k}: {v}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{run_id}_{params.id}_montecarlo.json"
    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy_id": params.id,
                "strategy_version": params.version,
                "seed": RNG_SEED,
                "fees": args.fees,
                "slippage": args.slippage,
                "position_size_pct": args.position_size_pct,
                "simulation": sim,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
