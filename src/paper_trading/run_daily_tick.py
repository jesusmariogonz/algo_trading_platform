"""CLI del motor de paper trading — corre UN día (hoy) para todos los
buckets activos y muestra el resumen.

Requiere datos frescos (corre primero download/compute/relative_strength
del día, igual que daily_signals.py).

Uso:
    python -m src.paper_trading.run_daily_tick
"""

from src.paper_trading.engine import run_daily_tick


def main():
    snapshot = run_daily_tick()

    if not snapshot["date"]:
        print("No hay buckets con capital registrado y datos disponibles. Nada que hacer.")
        return

    print(f"\n=== Paper Trading — {snapshot['date']} ===\n")
    for bucket, r in snapshot["buckets"].items():
        print(f"--- {bucket} ---")
        print(f"  Equity: ${r['equity']} (retorno acumulado: {r['cumulative_return_pct']}%)")
        print(f"  Posiciones abiertas: {r['open_count']} · cerradas hoy: {r['closed_today']}")
        if r["closed_today"]:
            print(f"  P&L realizado hoy: ${r['realized_pnl_today']}")
            for c in r["closed_today_detail"]:
                print(f"    {c['symbol']}: {c['pnl_pct']}% ({c['reason']})")
        print()

    if snapshot.get("alertas"):
        print("=" * 60)
        print("ALERTAS — revisar antes de confiar en este snapshot:")
        for a in snapshot["alertas"]:
            print(f"  {a}")
        print("=" * 60)


if __name__ == "__main__":
    main()
