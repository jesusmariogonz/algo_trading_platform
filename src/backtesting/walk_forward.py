"""Walk-forward testing — valida una estrategia en varias ventanas
de tiempo consecutivas, cada una evaluada de forma independiente.

Importante — qué SÍ y qué NO hace esto en la Fase 0:

Las estrategias actuales (trend_following, momentum_breakout) son
reglas fijas, no parámetros ajustados por optimización. Por eso este
módulo NO hace el walk-forward clásico de "ajustar en ventana
in-sample, probar en ventana out-of-sample". Lo que SÍ hace es partir
el histórico completo en N ventanas consecutivas y correr la MISMA
estrategia, sin cambios, en cada una por separado — tratando cada
ventana como su propio período "fuera de muestra" frente a cualquier
ajuste manual que se haya hecho mirando el backtest completo.

Esto responde la pregunta real de validación en esta fase: ¿el
rendimiento es consistente a través de distintos regímenes de
mercado, o depende de que un par de operaciones ganadoras caigan en
el período correcto? Una estrategia que solo funciona en una ventana
y pierde en las demás es una señal de alerta, no de robustez.

El walk-forward CON optimización de parámetros (ajustar en cada
ventana in-sample y probar en la siguiente out-of-sample) es un paso
posterior, cuando exista un optimizador formal — ver docs/roadmap.md
Fase 3+.

Uso:
    python -m src.backtesting.walk_forward --strategy trend_following --windows 4
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.backtesting.run import RESULTS_DIR, STRATEGIES, load_universe, run_backtest


def split_windows(universe: dict[str, pd.DataFrame], n_windows: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Divide el rango de fechas común del universo en N ventanas
    consecutivas de igual duración (no superpuestas)."""
    all_dates = pd.concat([df["date"] for df in universe.values()])
    start, end = all_dates.min(), all_dates.max()
    edges = pd.date_range(start, end, periods=n_windows + 1)
    return [(edges[i], edges[i + 1]) for i in range(n_windows)]


def slice_universe(
    universe: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    """Recorta cada símbolo a [start, end], pero conserva suficiente
    historia PREVIA a `start` para que los indicadores de calentamiento
    (SMA 200, etc.) ya estén calculados al entrar a la ventana — si no,
    cada ventana perdería sus primeras ~200 sesiones por NaN y el
    resultado no sería comparable entre ventanas."""
    sliced = {}
    for symbol, df in universe.items():
        mask = df["date"] <= end
        sliced[symbol] = df[mask].copy()
    return sliced, start


def run_walk_forward(strategy_key: str, n_windows: int, fees: float, slippage: float):
    universe = load_universe()
    windows = split_windows(universe, n_windows)

    window_results = []
    for i, (w_start, w_end) in enumerate(windows, start=1):
        sliced, w_start = slice_universe(universe, w_start, w_end)
        results, params = run_backtest(strategy_key, fees, slippage, universe=sliced)

        # Solo nos interesan las operaciones DENTRO de esta ventana —
        # backtest_symbol ya incluye todo el histórico previo como
        # calentamiento, así que filtramos las métricas al cerrar.
        rows = []
        for symbol, portfolio in results.items():
            trades = portfolio.trades.records_readable
            in_window = trades[
                (trades["Entry Timestamp"] >= w_start) & (trades["Entry Timestamp"] <= w_end)
            ]
            if in_window.empty:
                continue
            total_pct = float((in_window["Return"]).sum() * 100)
            win_rate = float((in_window["Return"] > 0).mean() * 100)
            rows.append(
                {
                    "symbol": symbol,
                    "trades": len(in_window),
                    "total_return_pct_sum": round(total_pct, 2),
                    "win_rate_pct": round(win_rate, 2),
                }
            )

        window_df = pd.DataFrame(rows)
        window_results.append(
            {
                "window": i,
                "start": str(w_start.date()),
                "end": str(w_end.date()),
                "symbols_with_trades": len(window_df),
                "total_trades": int(window_df["trades"].sum()) if not window_df.empty else 0,
                "avg_return_pct_per_trade_sum": round(float(window_df["total_return_pct_sum"].mean()), 2)
                if not window_df.empty
                else None,
                "pct_symbols_profitable": round(
                    float((window_df["total_return_pct_sum"] > 0).mean() * 100), 2
                )
                if not window_df.empty
                else None,
                "detail": window_df.to_dict(orient="records"),
            }
        )

    return window_results, params


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, choices=STRATEGIES.keys())
    parser.add_argument("--windows", type=int, default=4, help="número de ventanas consecutivas no superpuestas")
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0005)
    args = parser.parse_args()

    window_results, params = run_walk_forward(args.strategy, args.windows, args.fees, args.slippage)

    print(f"\n=== Walk-forward: {params.name} (v{params.version}) — {args.windows} ventanas ===\n")
    for w in window_results:
        print(
            f"Ventana {w['window']} [{w['start']} -> {w['end']}]: "
            f"{w['total_trades']} operaciones, "
            f"{w['pct_symbols_profitable']}% de símbolos con retorno positivo "
            f"(retorno prom./símbolo: {w['avg_return_pct_per_trade_sum']}%)"
        )

    profitable_windows = [w for w in window_results if (w["pct_symbols_profitable"] or 0) >= 50]
    print(
        f"\nConsistencia: {len(profitable_windows)}/{len(window_results)} ventanas con "
        f"≥50% de símbolos en positivo."
    )
    if len(profitable_windows) < len(window_results) / 2:
        print(
            "⚠ Menos de la mitad de las ventanas son consistentemente positivas. "
            "Esto es una señal de alerta, no de robustez — no se recomienda avanzar "
            "a Fase 1 con esta estrategia tal como está."
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{run_id}_{params.id}_walkforward.json"
    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy_id": params.id,
                "strategy_version": params.version,
                "params": params.__dict__,
                "n_windows": args.windows,
                "fees": args.fees,
                "slippage": args.slippage,
                "windows": window_results,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
