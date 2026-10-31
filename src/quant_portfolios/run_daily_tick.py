"""CLI del motor de Quant Portfolios — corre un día para los 3
portafolios (Conservative Alpha, Balanced Growth, Aggressive Momentum).

Uso:
    python -m src.quant_portfolios.run_daily_tick
"""

from src.quant_portfolios.definitions import PORTFOLIOS
from src.quant_portfolios.engine import run_daily_tick_all


def main():
    snapshot = run_daily_tick_all()

    if not snapshot["date"]:
        print("Sin datos disponibles. Nada que hacer.")
        return

    print(f"\n=== Quant Portfolios — {snapshot['date']} ===\n")
    for portfolio_id, r in snapshot["portfolios"].items():
        name = PORTFOLIOS[portfolio_id].name
        print(f"--- {name} ---")
        print(f"  Equity: ${r['equity']} (retorno acumulado: {r['cumulative_return_pct']}%)")
        print(f"  Pérdida diaria: {r['daily_loss_pct']}% · Drawdown: {r['drawdown_pct']}%")
        if r["daily_loss_breaker_tripped"]:
            print("  ⚠ CIRCUIT BREAKER: pérdida diaria máxima alcanzada — sin nuevas entradas hoy.")
        if r["suspended"]:
            marca = "🆕 " if r["newly_suspended_today"] else ""
            print(f"  🛑 {marca}SUSPENDIDO: {r['suspended_reason']}")
        if r["rebalanced_today"]:
            print("  ↻ Rebalanceado hoy.")
        print()


if __name__ == "__main__":
    main()
