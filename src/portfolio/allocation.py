"""Reparto del capital inyectado entre los 4 buckets de inversión.

    Largo plazo             28.17%  (antes 43.33%)
    Mediano plazo           21.67%  (antes 33.33%)
    Riesgo alto              15.17%  (antes 23.33%)
    Mean Reversion           35.00%  (nuevo, ver ADR 0019)

Se eliminó el bucket "Muy alta volatilidad" (cripto, 10%) por decisión
explícita del usuario tras comparar backtests de 2025-2026: el
backtest con cripto rindió consistentemente peor que sin él (ver
docs/adr/0006-elimina-bucket-cripto.md) en las 3 ventanas probadas
(6, 22 y 34 meses). El 10% liberado se repartió EQUITATIVAMENTE entre
los 3 buckets restantes (+3.33 puntos cada uno), no proporcional a su
tamaño — decisión explícita del usuario, distinta de la alternativa
"proporcional" que también se probó.

El 1-nov-2026 se agregó un 4to bucket, "mean_reversion" (ADR 0019):
35% del capital total, validado con datos reales congelados como el
peso que maximiza retorno y mejora drawdown simultáneamente vs. el
control (ver ADR 0019 para la curva completa de sensibilidad al peso).
Los 3 buckets originales se escalaron a 65% del total, MANTENIENDO su
proporción interna de siempre (13/10/7) — no se repartió equitativo.

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

import requests

EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"

BUCKETS = {
    "largo_plazo": 0.65 * 13.0 / 30.0,
    "mediano_plazo": 0.65 * 10.0 / 30.0,
    "riesgo_alto": 0.65 * 7.0 / 30.0,
    "mean_reversion": 0.35,
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


def get_usd_mxn_rate() -> float:
    """Tipo de cambio USD->MXN del día, vía open.er-api.com (gratuita,
    sin API key). Si falla, no inventa un número — propaga el error."""
    resp = requests.get(EXCHANGE_RATE_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("result") != "success":
        raise RuntimeError(f"La API de tipo de cambio no respondió 'success': {data}")
    rate = data["rates"].get("MXN")
    if not rate:
        raise RuntimeError("La respuesta de la API no trae MXN.")
    return float(rate)


def record_injection(
    amount: float,
    injection_date: str | None = None,
    original_currency: str | None = None,
    original_amount: float | None = None,
    exchange_rate: float | None = None,
) -> dict:
    """Registra una inyección de capital (en USD) y su reparto
    proporcional entre los 4 buckets. No toca el dinero ya repartido
    antes. Si la inyección se originó en otra moneda (ej. MXN
    convertido), guarda el monto y tipo de cambio originales para
    auditoría — ver record_injection_mxn()."""
    if amount <= 0:
        raise ValueError("El monto debe ser positivo")

    entry = {
        "date": injection_date or date.today().isoformat(),
        "amount": round(amount, 2),
        "split": {bucket: round(amount * pct, 2) for bucket, pct in BUCKETS.items()},
    }
    if original_currency:
        entry["original_currency"] = original_currency
        entry["original_amount"] = original_amount
        entry["exchange_rate"] = exchange_rate

    ledger = load_ledger()
    ledger.append(entry)
    save_ledger(ledger)
    return entry


def record_injection_mxn(amount_mxn: float, injection_date: str | None = None) -> dict:
    """Convierte MXN -> USD al tipo de cambio del día y registra la
    inyección. El tipo de cambio usado queda guardado en el ledger,
    nunca oculto."""
    rate = get_usd_mxn_rate()
    amount_usd = amount_mxn / rate
    return record_injection(
        amount_usd,
        injection_date,
        original_currency="MXN",
        original_amount=round(amount_mxn, 2),
        exchange_rate=round(rate, 4),
    )


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

    inject = sub.add_parser("inject", help="Registra una inyección de capital en USD")
    inject.add_argument("amount", type=float)
    inject.add_argument("--date", default=None)

    inject_mxn = sub.add_parser(
        "inject-mxn", help="Registra una inyección en MXN, convertida a USD al tipo de cambio del día"
    )
    inject_mxn.add_argument("amount_mxn", type=float)
    inject_mxn.add_argument("--date", default=None)

    sub.add_parser("balances", help="Muestra el total inyectado por bucket")

    args = parser.parse_args()

    if args.command == "inject":
        entry = record_injection(args.amount, args.date)
        print(f"Inyección registrada: ${entry['amount']} USD el {entry['date']}")
        for bucket, amount in entry["split"].items():
            print(f"  {bucket}: ${amount} ({BUCKETS[bucket]*100:.0f}%)")
    elif args.command == "inject-mxn":
        entry = record_injection_mxn(args.amount_mxn, args.date)
        print(
            f"Inyección registrada: ${entry['original_amount']} MXN -> "
            f"${entry['amount']} USD (tipo de cambio: {entry['exchange_rate']}) el {entry['date']}"
        )
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
