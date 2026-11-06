"""Adapter delgado sobre ib_async para hablar con IB Gateway (paper
trading) corriendo en la misma VM, vía IBC (ver docs/adr/0022).

No contiene lógica de estrategia ni de riesgo — solo las operaciones
de broker que el motor necesita: conectar, consultar cuenta/posiciones
reales, y colocar una orden de mercado esperando su fill real.

Gateway corre en localhost:4002 (modo paper) dentro de la misma VM —
nunca se expone a la red, así que host/puerto son fijos por diseño,
no configurables desde fuera.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ib_async import IB, MarketOrder, Stock

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 4002
FILL_TIMEOUT_SEGUNDOS = 30


class OrdenNoLlenada(RuntimeError):
    """La orden se mandó pero no se llenó dentro del timeout."""


@dataclass
class Fill:
    symbol: str
    accion: str  # "BUY" o "SELL"
    shares: int
    precio_promedio: float


def conectar(client_id: int = 1) -> IB:
    ib = IB()
    ib.connect(GATEWAY_HOST, GATEWAY_PORT, clientId=client_id, timeout=15)
    return ib


def desconectar(ib: IB) -> None:
    ib.disconnect()


def cuenta_activa(ib: IB) -> str:
    cuentas = ib.managedAccounts()
    if not cuentas:
        raise RuntimeError("Gateway no reporta ninguna cuenta administrada")
    return cuentas[0]


def equity_de_cuenta(ib: IB) -> float:
    """NetLiquidation de la cuenta activa, en la moneda base de la cuenta
    (puede ser MXN — ver `equity_de_cuenta_usd` para sizing de
    posiciones en acciones de EE.UU., que cotizan en USD)."""
    resumen = ib.accountSummary()
    for item in resumen:
        if item.tag == "NetLiquidation":
            return float(item.value)
    raise RuntimeError("No se encontró NetLiquidation en accountSummary()")


def equity_de_cuenta_usd(ib: IB) -> float:
    """NetLiquidation específico en USD, vía el desglose por moneda de
    `accountValues()` — distinto de `equity_de_cuenta()` si la moneda
    base de la cuenta no es USD (la cuenta paper real de este proyecto
    reporta en MXN por default). Es el valor correcto para dimensionar
    posiciones en acciones de EE.UU."""
    for v in ib.accountValues():
        if v.tag == "NetLiquidationByCurrency" and v.currency == "USD":
            return float(v.value)
    raise RuntimeError("No se encontró NetLiquidationByCurrency en USD en accountValues()")


def posiciones_reales(ib: IB) -> dict[str, int]:
    """symbol -> shares netas, solo para acciones (Stock)."""
    out: dict[str, int] = {}
    for pos in ib.positions():
        if pos.contract.secType != "STK":
            continue
        out[pos.contract.symbol] = out.get(pos.contract.symbol, 0) + int(pos.position)
    return out


def posiciones_reales_con_costo(ib: IB) -> dict[str, dict]:
    """symbol -> {"shares": int, "avg_cost": float}, solo para
    acciones (Stock). `avgCost` de IBKR incluye comisiones promediadas
    — es el costo base real para calcular P&L, no un precio de
    mercado."""
    out: dict[str, dict] = {}
    for pos in ib.positions():
        if pos.contract.secType != "STK":
            continue
        symbol = pos.contract.symbol
        shares = int(pos.position)
        costo = float(pos.avgCost)
        if symbol in out:
            total_shares_previas = out[symbol]["shares"]
            costo_total = out[symbol]["avg_cost"] * total_shares_previas + costo * shares
            nuevo_total = total_shares_previas + shares
            out[symbol] = {
                "shares": nuevo_total,
                "avg_cost": costo_total / nuevo_total if nuevo_total else 0.0,
            }
        else:
            out[symbol] = {"shares": shares, "avg_cost": costo}
    return out


def ejecutar_orden_mercado(ib: IB, symbol: str, accion: str, shares: int) -> Fill:
    """Manda una orden de mercado y espera a que se llene por completo.

    `accion` es "BUY" o "SELL". Lanza OrdenNoLlenada si de verdad no se
    llenó dentro de FILL_TIMEOUT_SEGUNDOS — el motor decide qué hacer
    con eso (reintentar, registrar como fallida, etc.), este adapter
    no toma esa decisión.

    IMPORTANTE: `trade.orderStatus.status` NO es confiable por sí solo
    (ver docs/adr/0031 y 0032) — versiones de ib_async pueden reportar
    "Cancelled"/"Inactive" para una orden que en realidad SÍ se llenó
    en IBKR. Por eso esta función nunca decide "no se llenó" solo con
    el status: primero revisa `trade.fills` (las ejecuciones reales
    que llegan de IBKR, independientes del campo de status), y si
    tampoco hay fills ahí, compara las posiciones reales de la cuenta
    antes/después como última verificación antes de declarar la orden
    como no llenada."""
    if accion not in ("BUY", "SELL"):
        raise ValueError(f"accion debe ser BUY o SELL, no {accion!r}")
    if shares < 1:
        raise ValueError(f"shares debe ser >= 1, no {shares}")

    contrato = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contrato)

    shares_antes = posiciones_reales(ib).get(symbol, 0)

    orden = MarketOrder(accion, shares)
    # Si `tif` se deja vacío, TWS aplica el default de su "order
    # preset" y manda el aviso Error 10349 ("Order TIF was set to DAY
    # based on order preset") — versiones de ib_async anteriores al
    # fix en la rama `next` lo malinterpretan como cancelación real de
    # la orden, aunque en realidad pudo seguir viva. Fijar `tif`
    # explícitamente evita que TWS mande ese aviso.
    # Ver: https://github.com/ib-api-reloaded/ib_async/discussions/190
    orden.tif = "DAY"
    trade = ib.placeOrder(contrato, orden)

    limite = time.monotonic() + FILL_TIMEOUT_SEGUNDOS
    while not trade.isDone() and time.monotonic() < limite:
        ib.waitOnUpdate(timeout=1)

    if trade.isDone() and trade.orderStatus.status == "Filled":
        return Fill(
            symbol=symbol, accion=accion, shares=shares,
            precio_promedio=float(trade.orderStatus.avgFillPrice),
        )

    # El status dice que no se llenó — no confiar todavía. Revisar
    # `trade.fills`: IBKR puede mandar ejecuciones reales aunque el
    # status quede mal reportado.
    if trade.fills:
        total_shares = sum(f.execution.shares for f in trade.fills)
        if total_shares > 0:
            precio_promedio = (
                sum(f.execution.shares * f.execution.price for f in trade.fills) / total_shares
            )
            return Fill(
                symbol=symbol, accion=accion, shares=int(total_shares),
                precio_promedio=precio_promedio,
            )

    # Última verificación: comparar posiciones reales antes/después.
    # Si la cuenta cambió exactamente lo esperado, la orden SÍ se
    # ejecutó pese al status — usamos el último precio de mercado
    # como aproximación del precio real (no hay fill reportado del
    # que sacar el precio exacto).
    ib.sleep(2)
    shares_despues = posiciones_reales(ib).get(symbol, 0)
    delta_esperado = shares if accion == "BUY" else -shares
    if shares_despues - shares_antes == delta_esperado:
        [ticker] = ib.reqTickers(contrato)
        precio_aprox = ticker.marketPrice() or ticker.close
        return Fill(
            symbol=symbol, accion=accion, shares=shares,
            precio_promedio=float(precio_aprox),
        )

    raise OrdenNoLlenada(
        f"{symbol} {accion} {shares}: estado final = {trade.orderStatus.status!r}"
    )
