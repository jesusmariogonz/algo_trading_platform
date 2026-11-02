"""Exporta el estado de paper trading a un JSON que jesus-site
consume (misma idea que el snapshot manual de backtest — ver
docs/adr/0002-dashboard-hosting.md). Corre esto después de
run_daily_tick para que el dashboard de /trading se vea al día.

Uso:
    python -m src.paper_trading.export /ruta/a/jesus-site/lib/paper-trading-snapshot.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.backtesting.run import load_universe
from src.paper_trading.engine import load_history, load_state


def _con_precio_en_vivo(open_positions: list[dict]) -> list[dict]:
    """Agrega precio actual y P&L no realizado a cada posición abierta,
    usando el mismo dato procesado (data/processed/<symbol>.parquet)
    que ya usa el motor para el tick del día — no descarga nada nuevo,
    no inventa un precio: si falta el dato procesado de algún símbolo,
    esa posición se exporta sin precio en vivo en vez de fallar el
    export completo."""
    if not open_positions:
        return open_positions

    symbols = sorted({p["symbol"] for p in open_positions})
    try:
        universe = load_universe(symbols=symbols)
    except SystemExit:
        return open_positions  # faltan datos procesados para algún símbolo: no bloquea el export

    enriquecidas = []
    for pos in open_positions:
        df = universe.get(pos["symbol"])
        precio_actual = float(df.sort_values("date")["close"].iloc[-1]) if df is not None and not df.empty else None
        nueva = dict(pos)
        if precio_actual is not None:
            valor_actual = precio_actual * pos["shares"]
            costo_entrada = pos["entry_price"] * pos["shares"]
            nueva["current_price"] = round(precio_actual, 4)
            nueva["unrealized_pnl"] = round(valor_actual - costo_entrada, 2)
            nueva["unrealized_pnl_pct"] = round((valor_actual / costo_entrada - 1) * 100, 2)
        enriquecidas.append(nueva)
    return enriquecidas


def build_export() -> dict:
    state = load_state()
    history = load_history()

    buckets = {}
    for bucket, bucket_state in state.items():
        history_for_bucket = [
            {"date": h["date"], **h["buckets"][bucket]}
            for h in history
            if bucket in h["buckets"]
        ]
        buckets[bucket] = {
            "starting_capital": bucket_state["starting_capital"],
            "start_date": bucket_state["start_date"],
            "open_positions": _con_precio_en_vivo(bucket_state["open_positions"]),
            "closed_positions": bucket_state["closed_positions"],
            "daily_history": history_for_bucket,
            "suspended": bucket_state.get("suspended", False),
            "suspended_reason": bucket_state.get("suspended_reason"),
            "suspended_since": bucket_state.get("suspended_since"),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "algo_trading_platform paper trading engine (simulado, sin dinero real)",
        "buckets": buckets,
    }


def main():
    export = build_export()
    payload = json.dumps(export, indent=2, ensure_ascii=False)

    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload)
        print(f"Exportado a {out_path}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
