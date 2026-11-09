"""Bucket informativo (no es un bucket de trading real) que agrega el
cash ocioso invertido en el blend SPY/GLD (ADR 0028) a través de TODOS
los buckets reales, para poder ver su ganancia/pérdida por separado en
vez de que quede escondida dentro del equity de cada bucket.

Motor EN VIVO: el ledger (blend_ledger.py) tiene fidelidad completa
desde el día 1 de cada bucket (cada compra/venta real de SPY/GLD queda
registrada), así que el costo base se calcula directo del ledger.

Motor simulado: el ledger (blend_ledger.py) de este motor quedó
incompleto para fines de costo base, pero hay una fuente confiable de
historia completa: `init_bucket_state` invierte el 100% del capital
inicial de cada bucket en el blend desde el día 1, y cada entrada del
historial diario (`daily_history`) ya trae el campo `cash` — el valor
real del blend ese día en dólares (bench_shares * precio del día). Se
usa para mostrar el valor en dólares (siempre real).

El % de RETORNO, en cambio, NO se calcula como (valor_hoy / capital
inicial - 1): el cash entra y sale del blend todo el tiempo para
financiar entradas/salidas de posiciones de los buckets reales —
comparar el valor de hoy contra el capital inicial total mezclaría el
desempeño real del blend con esos flujos (ej. un bucket que sacó casi
todo su capital del blend el día 1 para abrir posiciones mostraría un
"-85%" que no es una pérdida real, es dinero que nunca estuvo
invertido ahí). En vez de eso, el retorno se calcula sobre el ÍNDICE
sintético del blend (`engine._blend_price_series`, base 100,
rebalanceado diario SPY/GLD) — el mismo precio que ya usa el motor
para marcar a mercado, pero leído como serie completa en vez de
incremental, así que no le afecta ningún flujo de cash, solo el
desempeño real de SPY/GLD."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.paper_trading import blend_ledger

BLEND_BUCKET_KEY = "blend_spy_gld"


def _retorno_indice_por_fecha(fechas: list[str]) -> dict[str, float] | None:
    """{fecha: nivel del índice ese día} para las fechas pedidas,
    usando el último nivel conocido en o antes de esa fecha (el índice
    solo tiene nivel en días de mercado) — None si no hay datos."""
    from src.paper_trading.engine import BLEND_WEIGHTS, _blend_price_series

    try:
        serie = _blend_price_series(BLEND_WEIGHTS)
    except SystemExit:
        return None
    if serie.empty:
        return None

    serie = serie.sort_values("date")
    niveles = dict(zip(serie["date"].dt.strftime("%Y-%m-%d"), serie["close"]))
    resultado = {}
    ultimo = None
    fechas_disponibles = sorted(niveles)
    for fecha in fechas:
        candidatas = [f for f in fechas_disponibles if f <= fecha]
        if candidatas:
            ultimo = niveles[candidatas[-1]]
        if ultimo is not None:
            resultado[fecha] = ultimo
    return resultado or None


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


def resumen_blend_simulado(buckets: dict) -> dict | None:
    """`buckets`: el mismo dict que build_export() ya arma para los
    buckets reales (starting_capital, start_date, daily_history con
    campo "cash" por día) — se reusa tal cual, sin volver a tocar
    state.json ni el ledger.

    Reconstruye la curva de equity del blend día por día, sumando el
    campo "cash" de cada bucket real (carga hacia adelante el último
    valor conocido de un bucket si ese día no tiene registro propio,
    igual que la curva de equity combinada del frontend — nunca
    inventa un valor nuevo)."""
    items = [(k, v) for k, v in buckets.items() if not k.startswith("_") and v.get("starting_capital")]
    if not items:
        return None

    starting_capital = round(sum(b["starting_capital"] for _, b in items), 2)
    if starting_capital <= 0:
        return None

    todas_fechas = sorted({
        h["date"] for _, b in items for h in b.get("daily_history", []) if h.get("cash") is not None
    })
    if not todas_fechas:
        return None

    ultimo_conocido = {k: b["starting_capital"] for k, b in items}
    por_fecha = {k: {h["date"]: h["cash"] for h in b.get("daily_history", []) if h.get("cash") is not None} for k, b in items}

    indice_por_fecha = _retorno_indice_por_fecha(todas_fechas)
    nivel_base = indice_por_fecha.get(todas_fechas[0]) if indice_por_fecha else None
    peak_indice = nivel_base

    historial = []
    for fecha in todas_fechas:
        for k, _ in items:
            if fecha in por_fecha[k]:
                ultimo_conocido[k] = por_fecha[k][fecha]
        equity = round(sum(ultimo_conocido.values()), 2)

        nivel_hoy = indice_por_fecha.get(fecha) if indice_por_fecha else None
        if nivel_hoy is not None and nivel_base:
            retorno_pct = round((nivel_hoy / nivel_base - 1) * 100, 2)
            peak_indice = max(peak_indice or nivel_hoy, nivel_hoy)
            drawdown_pct = round((peak_indice - nivel_hoy) / peak_indice * 100, 2) if peak_indice else 0.0
        else:
            # No se pudo leer el índice (ej. faltan datos procesados de
            # SPY/GLD) — nunca se inventa un retorno, se omite ese día.
            retorno_pct = None
            drawdown_pct = None

        historial.append({
            "date": fecha,
            "equity": equity,
            "cumulative_return_pct": retorno_pct,
            "drawdown_pct": drawdown_pct,
        })

    start_date = min((b["start_date"] for _, b in items if b.get("start_date")), default=todas_fechas[0])

    return {
        "starting_capital": starting_capital,
        "start_date": start_date,
        "open_positions": [
            {
                "symbol": "BLEND_SPY_GLD", "entry_date": start_date,
                "entry_price": None, "stop_price": None,
                "shares": None, "current_price": None,
                # No se reporta un P&L en dólares de esta posición
                # sintética: con cash entrando y saliendo todo el
                # tiempo, cualquier número aquí sería una aproximación
                # forzada. cumulative_return_pct (abajo, basado en el
                # índice, no en el flujo de cash) es la cifra confiable.
                "unrealized_pnl": None,
            }
        ],
        "closed_positions": [],
        "daily_history": historial,
        "suspended": False,
    }
