"""Exporta el estado de los Quant Portfolios a un JSON que jesus-site
consume, en páginas separadas del dashboard de buckets (decisión
explícita del usuario de que coexistan).

Uso:
    python -m src.quant_portfolios.export /ruta/a/jesus-site/lib/quant-portfolios-snapshot.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.quant_portfolios.definitions import PORTFOLIOS
from src.quant_portfolios.engine import load_history, load_state


def build_export() -> dict:
    state = load_state()
    history = load_history()

    portfolios = {}
    for portfolio_id, portfolio_state in state.items():
        portfolio_def = PORTFOLIOS[portfolio_id]
        history_for_portfolio = [
            {"date": h["date"], **h["portfolios"][portfolio_id]}
            for h in history
            if portfolio_id in h["portfolios"]
        ]
        portfolios[portfolio_id] = {
            "name": portfolio_def.name,
            "tagline": portfolio_def.tagline,
            "weights": portfolio_def.weights,
            "benchmark": portfolio_def.benchmark,
            "design_volatility_target_pct": portfolio_def.design_volatility_target_pct,
            "risk_per_trade_pct": portfolio_def.risk_per_trade_pct,
            "daily_loss_limit_pct": portfolio_def.daily_loss_limit_pct,
            "drawdown_review_pct": portfolio_def.drawdown_review_pct,
            "rebalance_frequency": portfolio_def.rebalance_frequency,
            "starting_capital": portfolio_state["starting_capital"],
            "start_date": portfolio_state["start_date"],
            "suspended": portfolio_state["suspended"],
            "suspended_reason": portfolio_state["suspended_reason"],
            "suspended_since": portfolio_state["suspended_since"],
            "holdings": portfolio_state["holdings"],
            "cash": portfolio_state["cash"],
            "daily_history": history_for_portfolio,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "algo_trading_platform quant portfolios engine (simulado, sin dinero real)",
        "portfolios": portfolios,
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
