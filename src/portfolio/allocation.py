"""Reparto del capital inyectado entre los 4 buckets de inversión.

    Largo plazo            40%
    Mediano plazo           30%
    Riesgo alto             20%
    Muy alta volatilidad    10%

IMPORTANTE — qué es y qué NO es este módulo todavía:

Esto es un LIBRO DE CONTRIBUCIONES (cuánto capital le has inyectado a
cada bucket), no un portafolio con valuación en vivo. No descuenta
pérdidas ni suma ganancias de operaciones — eso requiere el Portfolio
Management real (Fase 1+, con Postgres y reconciliación contra el
broker). Mezclar aquí "capital inyectado" con "valor actual de
mercado" sin datos de ejecución reales sería inventar un número.

Hoy solo el bucket `mediano_plazo` tiene una estrategia construida y
validada parcialmente (Trend Following / Momentum Breakout — ver
src/screening/daily_signals.py). Los otros tres existen como
estructura de asignación de capital, sin lógica de inversión detrás
todavía — ver README.md para el mapeo bucket -> estrategia propuesto.

El libro se guarda en data/portfolio/ledger.json (una lista de
inyecciones, nunca se sobrescribe — auditoría simple).
"""

import argparse
import json
from datetime import date
from pathlib import Path

BUCKETS = {
    "largo_plazo": 0.40,
    "mediano_plazo": 0.30,
    "riesgo_alto": 0.20,
    "muy_alta_volatilidad": 0.10,
}

assert abs(sum(BUCKETS.values()) - 1.0) < 1e-9, "Los buckets deben sumar 100%"

LEDGER_PATH = Path(__file__).resolve().parents[2] / "data" / "portfolio" / "ledger.json"


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return json.loads(LEDGER_PATH.read_text())


def save_ledger(entries: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def record_injection(amount: float, injection_date: str | None = None) -> dict:
    """Registra una inyección de capital y su reparto proporcional
    entre los 4 buckets. No toca el dinero ya repartido antes."""
    if amount <= 0:
        raise ValueError("El monto debe ser positivo")

    entry = {
        "date": injection_date or date.today().isoformat(),
        "amount": round(amount, 2),
        "split": {bucket: round(amount * pct, 2) for bucket, pct in BUCKETS.items()},
    }
    ledger = load_ledger()
    ledger.append(entry)
    save_ledger(ledger)
    return entry


def get_balances() -> dict:
    """Suma de todo lo inyectado a cada bucket hasta hoy (contribuciones,
    NO valor de mercado — ver docstring del módulo)."""
    ledger = load_ledger()
    balances = {bucket: 0.0 for bucket in BUCKETS}
    for entry in ledger:
        for bucket, amount in entry["split"].items():
            balances[bucket] += amount
    return {bucket: round(v, 2) for bucket, v in balances.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inject = sub.add_parser("inject", help="Registra una inyección de capital")
    inject.add_argument("amount", type=float)
    inject.add_argument("--date", default=None)

    sub.add_parser("balances", help="Muestra el total inyectado por bucket")

    args = parser.parse_args()

    if args.command == "inject":
        entry = record_injection(args.amount, args.date)
        print(f"Inyección registrada: ${entry['amount']} el {entry['date']}")
        for bucket, amount in entry["split"].items():
            print(f"  {bucket}: ${amount} ({BUCKETS[bucket]*100:.0f}%)")
    elif args.command == "balances":
        balances = get_balances()
        total = sum(balances.values())
        print(f"Total inyectado hasta hoy: ${total:.2f}\n")
        for bucket, amount in balances.items():
            print(f"  {bucket}: ${amount} ({BUCKETS[bucket]*100:.0f}% objetivo)")


if __name__ == "__main__":
    main()
