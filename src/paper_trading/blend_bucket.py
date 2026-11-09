"""Bucket informativo (no es un bucket de trading real) que agrega el
cash ocioso invertido en el blend SPY/GLD (ADR 0028) a través de TODOS
los buckets reales, para poder ver su ganancia/pérdida por separado en
vez de que quede escondida dentro del equity de cada bucket.

Motor EN VIVO: el ledger (blend_ledger.py) tiene fidelidad completa
desde el día 1 de cada bucket (cada compra/venta real de SPY/GLD queda
registrada), así que el costo base se calcula directo del ledger.

Motor simulado: el ledger histórico de este motor quedó incompleto —
`init_bucket_state` solo empezó a registrar la compra inicial en el
ledger después de que los 3 buckets ya llevaban días corriendo, así
que no hay costo base confiable que reconstruir. En vez de reportar un
número que sabemos que está mal, este bucket arranca su propio
tracking HOY (capital inicial = valor de mercado de hoy) — la misma
decisión que ya se tomó para el rebase del motor en vivo. El baseline
se persiste en state["_blend_tracking"] para no resetearse en cada
corrida."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.paper_trading import blend_ledger

BLEND_BUCKET_KEY = "blend_spy_gld"
BLEND_TRACKING_STATE_KEY = "_blend_tracking"


def resumen_blend_live(ledger_path: Path, precios_hoy: dict[str, float]) -> dict | None:
    """Ganancia/pérdida real del blend en vivo, calculada directo del
    ledger (costo base exacto, sin aproximar)."""
    ledger = blend_ledger.load_ledger(ledger_path)
    if not ledger:
        return None

    costo_base_total = 0.0
    shares_por_simbolo: dict[str, float] = {}
    for tx in ledger:
        signo = 1 if tx["tipo"] == "compra" else -1
        shares_por_simbolo[tx["simbolo"]] = shares_por_simbolo.get(tx["simbolo"], 0.0) + signo * tx["shares"]
        costo_base_total += signo * tx["monto_usd"]

    if costo_base_total <= 0:
        return None

    valor_hoy = sum(
        shares * precios_hoy.get(simbolo, 0.0)
        for simbolo, shares in shares_por_simbolo.items()
    )
    hoy = datetime.now(timezone.utc).date().isoformat()

    return {
        "starting_capital": round(costo_base_total, 2),
        "open_positions": [
            {
                "symbol": simbolo, "entry_date": None, "entry_price": None, "stop_price": None,
                "shares": round(shares, 6), "current_price": precios_hoy.get(simbolo),
                "unrealized_pnl": None,
            }
            for simbolo, shares in sorted(shares_por_simbolo.items()) if abs(shares) > 1e-9
        ],
        "closed_positions": [],
        "daily_history": [
            {
                "date": hoy,
                "equity": round(valor_hoy, 2),
                "cumulative_return_pct": round((valor_hoy / costo_base_total - 1) * 100, 2),
                "drawdown_pct": 0.0,
            }
        ],
        "suspended": False,
    }


def resumen_blend_simulado(state: dict, precios_por_bucket: dict[str, float]) -> dict | None:
    """`precios_por_bucket`: {bucket: blend_last_price} — cada bucket
    del motor simulado trae su propio índice incremental (pueden
    divergir levemente entre sí, por diseño — ver ADR 0020), así que
    el valor combinado se suma bucket por bucket, no con un solo
    precio global."""
    valor_hoy = 0.0
    shares_totales = 0.0
    for bucket, bucket_state in state.items():
        if bucket.startswith("_"):
            continue
        shares = bucket_state.get("bench_shares", 0.0)
        precio = precios_por_bucket.get(bucket)
        if precio:
            valor_hoy += shares * precio
            shares_totales += shares

    if shares_totales <= 0:
        return None

    valor_hoy = round(valor_hoy, 2)
    hoy = datetime.now(timezone.utc).date().isoformat()

    tracking = state.setdefault(BLEND_TRACKING_STATE_KEY, {})
    if "starting_capital" not in tracking:
        tracking["starting_capital"] = valor_hoy
        tracking["start_date"] = hoy
        tracking["peak_equity"] = valor_hoy

    starting_capital = tracking["starting_capital"]
    tracking["peak_equity"] = max(tracking.get("peak_equity", valor_hoy), valor_hoy)
    peak_equity = tracking["peak_equity"]
    drawdown_pct = (peak_equity - valor_hoy) / peak_equity * 100 if peak_equity else 0.0

    return {
        "starting_capital": starting_capital,
        "open_positions": [
            {
                "symbol": "BLEND_SPY_GLD", "entry_date": tracking["start_date"],
                "entry_price": None, "stop_price": None,
                "shares": round(shares_totales, 6), "current_price": None,
                "unrealized_pnl": round(valor_hoy - starting_capital, 2),
            }
        ],
        "closed_positions": [],
        "daily_history": [
            {
                "date": hoy,
                "equity": valor_hoy,
                "cumulative_return_pct": round((valor_hoy / starting_capital - 1) * 100, 2) if starting_capital else 0.0,
                "drawdown_pct": round(drawdown_pct, 2),
            }
        ],
        "suspended": False,
    }
