"""Ledger de transacciones del blend SPY/GLD (ADR 0028) — cada vez que
cash ocioso entra o sale del blend, en cualquiera de los dos motores
(simulado o en vivo), se registra aquí. Permite calcular con precisión
cuánto ha generado el blend, sin tener que reconstruirlo a mano
después (como se tuvo que hacer antes de que existiera este ledger).

No es un bucket de trading real — es puro registro, append-only, igual
que `history.json`."""

from __future__ import annotations

import json
from pathlib import Path


def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save_ledger(path: Path, ledger: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))


def registrar(
    path: Path,
    *,
    bucket: str,
    fecha: str,
    tipo: str,
    simbolo: str,
    monto_usd: float,
    precio: float,
    shares: float,
    motivo: str,
) -> None:
    """`tipo` es "compra" o "venta". `simbolo` es "SPY", "GLD", o
    "BLEND_SPY_GLD" para el motor simulado (que no distingue entre los
    dos componentes, solo mueve el índice combinado)."""
    if tipo not in ("compra", "venta"):
        raise ValueError(f"tipo debe ser 'compra' o 'venta', no {tipo!r}")

    ledger = load_ledger(path)
    ledger.append(
        {
            "bucket": bucket,
            "fecha": fecha,
            "tipo": tipo,
            "simbolo": simbolo,
            "monto_usd": round(monto_usd, 2),
            "precio": round(precio, 4),
            "shares": round(shares, 6),
            "motivo": motivo,
        }
    )
    save_ledger(path, ledger)


def ganancia_por_bucket(ledger: list[dict], precios_hoy: dict[str, float]) -> dict[str, float]:
    """Ganancia realizada+no realizada del blend, por bucket, a partir
    del ledger — sin necesitar reconstruir nada a mano. Para cada
    símbolo (SPY/GLD o BLEND_SPY_GLD), acumula shares netas y costo
    base neto; la ganancia es el valor de mercado de hoy menos el
    costo base neto (igual que cualquier posición de inversión)."""
    por_bucket_simbolo: dict[tuple[str, str], dict[str, float]] = {}

    for tx in ledger:
        clave = (tx["bucket"], tx["simbolo"])
        acc = por_bucket_simbolo.setdefault(clave, {"shares": 0.0, "costo_base": 0.0})
        signo = 1 if tx["tipo"] == "compra" else -1
        acc["shares"] += signo * tx["shares"]
        acc["costo_base"] += signo * tx["monto_usd"]

    ganancia: dict[str, float] = {}
    for (bucket, simbolo), acc in por_bucket_simbolo.items():
        precio_hoy = precios_hoy.get(simbolo)
        if precio_hoy is None:
            continue
        valor_hoy = acc["shares"] * precio_hoy
        ganancia[bucket] = ganancia.get(bucket, 0.0) + round(valor_hoy - acc["costo_base"], 2)

    return ganancia
