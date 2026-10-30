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

from src.paper_trading.engine import load_history, load_state


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
            "open_positions": bucket_state["open_positions"],
            "closed_positions": bucket_state["closed_positions"],
            "daily_history": history_for_bucket,
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
