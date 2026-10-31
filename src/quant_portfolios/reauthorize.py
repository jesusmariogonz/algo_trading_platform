"""Levanta la suspensión de un Quant Portfolio después de que el
circuit breaker de drawdown lo detuvo. Es una acción MANUAL a
propósito — el motor nunca se reactiva solo (regla del usuario:
"exige autorización para reactivarse").

No liquida ni modifica posiciones — solo permite que el próximo
rebalanceo vuelva a poder AUMENTAR exposición si la tendencia lo
justifica. No borra el historial de por qué se suspendió.

Uso:
    python -m src.quant_portfolios.reauthorize conservative_alpha
"""

import argparse
import sys

from src.quant_portfolios.definitions import PORTFOLIOS
from src.quant_portfolios.engine import load_state, save_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("portfolio_id", choices=list(PORTFOLIOS.keys()))
    args = parser.parse_args()

    state = load_state()
    portfolio_state = state.get(args.portfolio_id)
    if portfolio_state is None:
        print(f"'{args.portfolio_id}' no tiene estado todavía (no ha corrido ningún tick).", file=sys.stderr)
        sys.exit(1)

    if not portfolio_state["suspended"]:
        print(f"'{args.portfolio_id}' no está suspendido — nada que reautorizar.")
        return

    print(f"Suspendido desde {portfolio_state['suspended_since']} por: {portfolio_state['suspended_reason']}")
    portfolio_state["suspended"] = False
    portfolio_state["suspended_reason"] = None
    portfolio_state["suspended_since"] = None
    save_state(state)
    print(f"'{args.portfolio_id}' reautorizado — puede volver a aumentar exposición en el próximo rebalanceo.")


if __name__ == "__main__":
    main()
