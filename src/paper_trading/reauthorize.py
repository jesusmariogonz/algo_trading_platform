"""Levanta la suspensión de un bucket después de que el circuit
breaker de drawdown lo detuvo. Es una acción MANUAL a propósito — el
motor nunca se reactiva solo (misma regla que en Quant Portfolios:
"exige autorización para reactivarse").

No liquida ni modifica posiciones abiertas — solo permite que vuelvan
a abrirse posiciones NUEVAS si hay señal. No borra el historial de por
qué se suspendió.

Uso:
    python -m src.paper_trading.reauthorize largo_plazo
"""

import argparse
import sys

from src.paper_trading.engine import ACTIVE_BUCKETS, load_state, save_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bucket", choices=ACTIVE_BUCKETS)
    args = parser.parse_args()

    state = load_state()
    bucket_state = state.get(args.bucket)
    if bucket_state is None:
        print(f"'{args.bucket}' no tiene estado todavía (no ha corrido ningún tick).", file=sys.stderr)
        sys.exit(1)

    if not bucket_state.get("suspended"):
        print(f"'{args.bucket}' no está suspendido — nada que reautorizar.")
        return

    print(f"Suspendido desde {bucket_state['suspended_since']} por: {bucket_state['suspended_reason']}")
    bucket_state["suspended"] = False
    bucket_state["suspended_reason"] = None
    bucket_state["suspended_since"] = None
    save_state(state)
    print(f"'{args.bucket}' reautorizado — puede volver a abrir posiciones nuevas desde el próximo tick.")


if __name__ == "__main__":
    main()
