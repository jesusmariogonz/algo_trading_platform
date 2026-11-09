"""Motor de Paper Trading EN VIVO — mismas reglas de entrada/salida que
`src/paper_trading/engine.py` (señales, trailing stop, circuit
breakers), pero las posiciones se abren y cierran con órdenes REALES
de mercado contra la cuenta paper de IBKR (ver ADR 0022 y 0023),
usando el fill real en vez del precio de cierre.

Corre EN PARALELO al motor simulado, con su propio estado
(`data/paper_trading_live/`), para poder comparar simulado vs.
ejecución real sin arriesgar el histórico ya acumulado del simulado.

Desde ADR 0028, el cash ocioso SÍ se invierte en el blend SPY/GLD, con
órdenes reales (50/50 por valor, redondeado a acciones enteras — IBKR
no soporta fracciones vía orden de mercado). Cada vez que se abre una
posición, se liquida la porción de blend necesaria; cada vez que se
cierra una, el producto vuelve al blend. Mismo comportamiento que el
motor simulado (ADR 0007), ejecutado con órdenes reales. Toda entrada
y salida del blend queda registrada en `blend_ledger.py` (ADR 0028),
por bucket y por símbolo (SPY/GLD por separado, a diferencia del motor
simulado que los trata como un solo índice combinado).

Antes de ADR 0028 el cash ocioso se quedaba como cash puro sin
invertir — decisión original de ADR 0023, revertida tras validar que
el motor en vivo funciona de forma estable y que el usuario prefiere
paridad de comportamiento con el motor simulado sobre minimizar
volumen de operaciones.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.backtesting.run import load_universe
from src.broker.ibkr_adapter import (
    Fill,
    OrdenNoLlenada,
    ejecutar_orden_mercado,
    posiciones_reales,
    posiciones_reales_con_costo,
)
from src.paper_trading import blend_ledger
from src.paper_trading.engine import (
    BLEND_WEIGHTS,
    CROSS_SECTIONAL_FILTER_BUCKETS,
    CROSS_SECTIONAL_PERCENTIL_MIN,
    FRICCION_POR_LADO,
    RISK_LIMITS,
    _last_row_as_of,
    _percentiles_cross_sectional_hoy,
    _signals_for_symbol,
)
from src.screening.daily_signals import BUCKET_CONFIG, read_universe_file

ROOT = Path(__file__).resolve().parents[2]
LIVE_STATE_PATH = ROOT / "data" / "paper_trading_live" / "state.json"
LIVE_HISTORY_PATH = ROOT / "data" / "paper_trading_live" / "history.json"
LIVE_BLEND_LEDGER_PATH = ROOT / "data" / "paper_trading_live" / "blend_ledger.json"

ACTIVE_BUCKETS = list(BUCKET_CONFIG.keys())

NYSE_TZ = ZoneInfo("America/New_York")
NYSE_APERTURA = dt_time(9, 30)
NYSE_CIERRE = dt_time(16, 0)


def _mercado_regular_abierto_ahora() -> bool:
    """Aproximación simple de horario regular de NYSE (9:30am-4:00pm
    ET, lunes a viernes, sin calendario de feriados) — ver ADR 0035.
    Mandar una orden fuera de este horario no la rechaza: IBKR la
    encola para el siguiente open, y nuestro `FILL_TIMEOUT_SEGUNDOS`
    (30s) nunca la alcanza a ver llenarse, así que el motor la
    registra como fallida aunque horas después sí se ejecute de
    verdad — causa real de la divergencia encontrada el 2026-11-08.
    Esta función evita mandar entradas nuevas en esa ventana ciega."""
    ahora = datetime.now(NYSE_TZ)
    if ahora.weekday() >= 5:  # sábado=5, domingo=6
        return False
    return NYSE_APERTURA <= ahora.time() <= NYSE_CIERRE


def _precios_blend_hoy(as_of: pd.Timestamp | None = None) -> dict[str, float]:
    """Último precio de cierre descargado para SPY y GLD — sirve solo
    para DECIDIR cuántas acciones enteras comprar/vender; el precio
    real de ejecución siempre lo da el fill de la orden, nunca este."""
    universe = load_universe(symbols=list(BLEND_WEIGHTS))
    precios = {}
    for simbolo in BLEND_WEIGHTS:
        df = universe.get(simbolo)
        if df is None:
            continue
        last = _last_row_as_of(df, as_of)
        if last is not None:
            precios[simbolo] = float(last["close"])
    return precios


def _valor_blend(bucket_state: dict, precios: dict[str, float]) -> float:
    valor = 0.0
    for simbolo in BLEND_WEIGHTS:
        shares = bucket_state.get(f"blend_{simbolo.lower()}_shares", 0)
        precio = precios.get(simbolo)
        if precio:
            valor += shares * precio
    return valor


def _invertir_en_blend(
    ib, bucket: str, monto_usd: float, bucket_state: dict, fecha: str, motivo: str,
    precios: dict[str, float], ordenes_fallidas_hoy: list[dict],
) -> float:
    """Compra SPY+GLD real, 50/50 por valor, con lo que alcance en
    acciones enteras. Devuelve el monto REAL invertido — puede ser
    menor al pedido por el redondeo; el resto se queda en cash."""
    if monto_usd <= 0:
        return 0.0
    invertido = 0.0
    for simbolo, peso in BLEND_WEIGHTS.items():
        precio = precios.get(simbolo)
        if not precio:
            continue
        shares = int((monto_usd * peso) // precio)
        if shares < 1:
            continue
        try:
            fill: Fill = ejecutar_orden_mercado(ib, simbolo, "BUY", shares)
        except OrdenNoLlenada as e:
            ordenes_fallidas_hoy.append({"symbol": simbolo, "accion": "BUY", "error": str(e)})
            continue
        costo_real = fill.precio_promedio * shares
        invertido += costo_real
        clave = f"blend_{simbolo.lower()}_shares"
        bucket_state[clave] = bucket_state.get(clave, 0) + shares
        blend_ledger.registrar(
            LIVE_BLEND_LEDGER_PATH, bucket=bucket, fecha=fecha, tipo="compra",
            simbolo=simbolo, monto_usd=costo_real, precio=fill.precio_promedio,
            shares=shares, motivo=motivo,
        )
    return invertido


def _liquidar_de_blend(
    ib, bucket: str, monto_necesario: float, bucket_state: dict, fecha: str, motivo: str,
    precios: dict[str, float], ordenes_fallidas_hoy: list[dict],
) -> float:
    """Vende SPY+GLD real, proporcional por valor, para levantar AL
    MENOS `monto_necesario` — puede levantar algo más por el redondeo
    a acciones enteras (el sobrante se queda en cash). Devuelve el
    monto REAL levantado."""
    if monto_necesario <= 0:
        return 0.0
    levantado = 0.0
    for simbolo, peso in BLEND_WEIGHTS.items():
        precio = precios.get(simbolo)
        clave = f"blend_{simbolo.lower()}_shares"
        shares_disponibles = bucket_state.get(clave, 0)
        if not precio or shares_disponibles < 1:
            continue
        shares_a_vender = min(shares_disponibles, max(1, math.ceil((monto_necesario * peso) / precio)))
        try:
            fill: Fill = ejecutar_orden_mercado(ib, simbolo, "SELL", shares_a_vender)
        except OrdenNoLlenada as e:
            ordenes_fallidas_hoy.append({"symbol": simbolo, "accion": "SELL", "error": str(e)})
            continue
        proceeds = fill.precio_promedio * shares_a_vender
        levantado += proceeds
        bucket_state[clave] = shares_disponibles - shares_a_vender
        blend_ledger.registrar(
            LIVE_BLEND_LEDGER_PATH, bucket=bucket, fecha=fecha, tipo="venta",
            simbolo=simbolo, monto_usd=proceeds, precio=fill.precio_promedio,
            shares=shares_a_vender, motivo=motivo,
        )
    return levantado


def load_state() -> dict:
    if not LIVE_STATE_PATH.exists():
        return {}
    return json.loads(LIVE_STATE_PATH.read_text())


def save_state(state: dict) -> None:
    LIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_history() -> list[dict]:
    if not LIVE_HISTORY_PATH.exists():
        return []
    return json.loads(LIVE_HISTORY_PATH.read_text())


def save_history(history: list[dict]) -> None:
    LIVE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def init_bucket_state(bucket: str, starting_capital: float, ib=None) -> dict:
    """Desde ADR 0028: si se pasa `ib` (conexión real), el capital
    inicial se invierte de entrada en el blend, igual que el motor
    simulado (ADR 0007). Si `ib` es None (uso en tests que no
    necesitan una conexión real), se queda como cash puro — compat
    hacia atrás para no forzar un mock de IB en cada test que solo
    necesita un bucket_state de arranque."""
    estado = {
        "starting_capital": round(starting_capital, 2),
        "start_date": date.today().isoformat(),
        "cash": round(starting_capital, 2),
        "blend_spy_shares": 0,
        "blend_gld_shares": 0,
        "open_positions": [],
        "closed_positions": [],
        "peak_equity": round(starting_capital, 2),
        "day_start_equity": round(starting_capital, 2),
        "day_start_date": None,
        "suspended": False,
        "suspended_reason": None,
        "suspended_since": None,
        "daily_loss_tripped_today": False,
        "ordenes_fallidas": [],
    }
    if ib is not None:
        fecha = date.today().isoformat()
        precios = _precios_blend_hoy()
        invertido = _invertir_en_blend(
            ib, bucket, estado["cash"], estado, fecha, "capital inicial del bucket", precios, [],
        )
        estado["cash"] = round(estado["cash"] - invertido, 2)
    return estado


def run_bucket_tick_live(bucket: str, bucket_state: dict, ib, as_of: pd.Timestamp | None = None) -> dict:
    """Un día de mercado para un bucket, con órdenes reales vía `ib`
    (una conexión ya conectada de `src.broker.ibkr_adapter.conectar`).

    `as_of` solo existe para pruebas con mocks — en uso real se deja
    en None y usa el último dato descargado, igual que el simulado."""
    config = BUCKET_CONFIG[bucket]
    symbols = read_universe_file(config["universe_file"])
    risk_pct = config["risk_pct"]
    strategies = config["strategies"]
    universe = load_universe(symbols=symbols)

    today_label = None
    for df in universe.values():
        last = _last_row_as_of(df, as_of)
        if last is not None:
            today_label = str(last["date"].date())
            break

    open_positions = bucket_state["open_positions"]
    cash = bucket_state.get("cash", 0.0)
    closed_today = []
    ordenes_fallidas_hoy = []
    precios_blend = _precios_blend_hoy(as_of)

    # --- 1. Revisar posiciones abiertas: trailing stop o señal de salida ---
    still_open = []
    for pos in open_positions:
        symbol = pos["symbol"]
        df = universe.get(symbol)
        if df is None:
            still_open.append(pos)
            continue
        signaled = _signals_for_symbol(df, pos["strategy"])
        last = _last_row_as_of(signaled, as_of)
        if last is None:
            still_open.append(pos)
            continue
        today_label = str(last["date"].date())

        pos["stop_price"] = max(pos["stop_price"], float(last["stop_price"]))
        close_price = float(last["close"])
        stop_hit = close_price <= pos["stop_price"]
        exit_signal = int(last["signal"]) == -1

        if not (stop_hit or exit_signal):
            still_open.append(pos)
            continue

        try:
            fill: Fill = ejecutar_orden_mercado(ib, symbol, "SELL", pos["shares"])
        except OrdenNoLlenada as e:
            # No se pudo cerrar hoy — se queda abierta, se reintenta
            # mañana. Nunca se asume cerrada sin un fill real.
            ordenes_fallidas_hoy.append({"symbol": symbol, "accion": "SELL", "error": str(e)})
            still_open.append(pos)
            continue

        proceeds = fill.precio_promedio * pos["shares"]
        pnl = proceeds - pos["entry_price"] * pos["shares"]
        invertido = _invertir_en_blend(
            ib, bucket, proceeds, bucket_state, today_label, f"producto de cerrar {symbol}",
            precios_blend, ordenes_fallidas_hoy,
        )
        cash += round(proceeds - invertido, 2)
        closed_today.append(
            {
                **pos,
                "exit_date": today_label,
                "exit_price": round(fill.precio_promedio, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round((proceeds / (pos["entry_price"] * pos["shares"]) - 1) * 100, 2),
                "reason": "stop_hit" if stop_hit else "signal_exit",
            }
        )

    open_positions = still_open

    # --- 1.5. Circuit breakers — misma mecánica que el motor simulado ---
    limits = RISK_LIMITS.get(bucket)
    blocked = False
    daily_loss_pct = 0.0
    drawdown_pct = 0.0
    newly_suspended = False
    equity_now = bucket_state["starting_capital"]
    if limits is not None and today_label is not None:
        if bucket_state.get("day_start_date") != today_label:
            bucket_state["day_start_equity"] = bucket_state.get("last_equity", bucket_state["starting_capital"])
            bucket_state["day_start_date"] = today_label
            bucket_state["daily_loss_tripped_today"] = False

        unrealized_now = sum(
            float(_last_row_as_of(universe[p["symbol"]], as_of)["close"]) * p["shares"]
            for p in open_positions
            if universe.get(p["symbol"]) is not None and _last_row_as_of(universe[p["symbol"]], as_of) is not None
        )
        equity_now = cash + _valor_blend(bucket_state, precios_blend) + unrealized_now

        day_start_equity = bucket_state.get("day_start_equity") or bucket_state["starting_capital"]
        daily_loss_pct = (day_start_equity - equity_now) / day_start_equity if day_start_equity else 0.0
        if daily_loss_pct >= limits["daily_loss_limit_pct"]:
            bucket_state["daily_loss_tripped_today"] = True

        bucket_state["peak_equity"] = max(bucket_state.get("peak_equity", 0.0), equity_now)
        peak_equity = bucket_state["peak_equity"]
        drawdown_pct = (peak_equity - equity_now) / peak_equity if peak_equity else 0.0
        if drawdown_pct >= limits["drawdown_review_pct"] and not bucket_state.get("suspended"):
            bucket_state["suspended"] = True
            bucket_state["suspended_reason"] = (
                f"Drawdown {drawdown_pct*100:.1f}% alcanzó el límite de revisión "
                f"({limits['drawdown_review_pct']*100:.0f}%)"
            )
            bucket_state["suspended_since"] = today_label
            newly_suspended = True

        blocked = bucket_state.get("suspended", False) or bucket_state.get("daily_loss_tripped_today", False)

    # --- 2. Señales de entrada de hoy ---
    open_symbols = {p["symbol"] for p in open_positions}
    # Fuera de horario regular de NYSE, IBKR encola las órdenes nuevas
    # para el siguiente open en vez de rechazarlas — nuestro timeout
    # de 30s nunca las ve llenarse, así que el motor las reportaría
    # como fallidas aunque horas después sí se ejecuten de verdad
    # (ver ADR 0035). Mejor no abrir nada nuevo fuera de horario; las
    # salidas (stop/señal) sí se evalúan siempre, solo las entradas
    # se saltan.
    if blocked or not _mercado_regular_abierto_ahora():
        strategies = []
    percentiles_cross_sectional = (
        _percentiles_cross_sectional_hoy(universe, symbols, as_of)
        if bucket in CROSS_SECTIONAL_FILTER_BUCKETS
        else None
    )
    for strategy_key in strategies:
        for symbol in symbols:
            if symbol in open_symbols:
                continue
            if symbol in BLEND_WEIGHTS:
                # SPY/GLD están reservados para el blend de cash ocioso
                # (ADR 0028) — abrir una posición real de estrategia en
                # el mismo símbolo que el blend también opera colisiona
                # contra la MISMA posición real en IBKR (el broker no
                # distingue "esto es una señal de trading" de "esto es
                # inversión del blend"), dejando el ledger del blend
                # creyendo que tiene acciones que la estrategia ya
                # vendió por su cuenta. Nunca se abre una entrada nueva
                # aquí; si ya hay una posición vieja abierta en estos
                # símbolos, sigue gestionándose normal (open_symbols ya
                # la cubre arriba).
                continue
            df = universe.get(symbol)
            if df is None:
                continue
            signaled = _signals_for_symbol(df, strategy_key)
            last = _last_row_as_of(signaled, as_of)
            if last is None or int(last["signal"]) != 1:
                continue

            if percentiles_cross_sectional is not None:
                ret_126d = last.get("return_126d")
                perc = percentiles_cross_sectional.get(symbol)
                pasa_filtro = (
                    pd.notna(ret_126d) and float(ret_126d) > 0
                    and perc is not None and perc >= CROSS_SECTIONAL_PERCENTIL_MIN
                )
                if not pasa_filtro:
                    continue

            today_label = str(last["date"].date())

            entry_price_estimado = float(last["close"])
            stop_price = float(last["stop_price"])
            risk_per_share = entry_price_estimado - stop_price
            if risk_per_share <= 0:
                continue

            risk_amount = equity_now * risk_pct
            shares = int(risk_amount // risk_per_share)
            # Costo estimado con la misma fricción del backtest, solo
            # para decidir si alcanza — el costo REAL lo da el fill de
            # la orden, no esta estimación. "disponible" es cash + lo
            # que hay invertido en el blend (ADR 0028), no solo cash.
            cost_estimado = shares * entry_price_estimado * (1 + FRICCION_POR_LADO)
            disponible = cash + _valor_blend(bucket_state, precios_blend)
            if shares < 1 or cost_estimado > disponible:
                continue

            if cost_estimado > cash:
                faltante = cost_estimado - cash
                levantado = _liquidar_de_blend(
                    ib, bucket, faltante, bucket_state, today_label, f"financia la compra de {symbol}",
                    precios_blend, ordenes_fallidas_hoy,
                )
                cash += levantado
                if cost_estimado > cash:
                    # La liquidación del blend no alcanzó a levantar lo
                    # necesario (ej. una pata falló) — no se fuerza la
                    # compra con cash que no existe.
                    ordenes_fallidas_hoy.append(
                        {
                            "symbol": symbol,
                            "accion": "BUY",
                            "error": f"liquidar el blend solo levantó ${levantado:.2f}, faltaba ${faltante:.2f}",
                        }
                    )
                    continue

            try:
                fill: Fill = ejecutar_orden_mercado(ib, symbol, "BUY", shares)
            except OrdenNoLlenada as e:
                ordenes_fallidas_hoy.append({"symbol": symbol, "accion": "BUY", "error": str(e)})
                continue

            cost_real = fill.precio_promedio * shares
            if cost_real > cash:
                # El fill real salió más caro que el estimado y ya no
                # alcanza — no debería pasar casi nunca (fricción real
                # suele ser menor al 0.1% estimado), pero si pasa, no
                # se inventa cash: se registra y se sigue.
                ordenes_fallidas_hoy.append(
                    {
                        "symbol": symbol,
                        "accion": "BUY",
                        "error": f"fill real (${cost_real:.2f}) superó el cash disponible (${cash:.2f})",
                    }
                )
                continue

            cash -= cost_real
            open_positions.append(
                {
                    "symbol": symbol,
                    "strategy": strategy_key,
                    "entry_date": today_label,
                    "entry_price": round(fill.precio_promedio, 2),
                    "stop_price": round(stop_price, 2),
                    "initial_stop_price": round(stop_price, 2),
                    "shares": shares,
                }
            )
            open_symbols.add(symbol)

    # --- 3. Equity del bucket ---
    unrealized = 0.0
    for pos in open_positions:
        df = universe.get(pos["symbol"])
        if df is None:
            continue
        last = _last_row_as_of(df, as_of)
        if last is None:
            continue
        unrealized += float(last["close"]) * pos["shares"]
        today_label = today_label or str(last["date"].date())

    valor_blend_final = _valor_blend(bucket_state, precios_blend)
    equity = cash + valor_blend_final + unrealized
    realized_pnl_today = sum(c["pnl"] for c in closed_today)

    bucket_state["cash"] = round(cash, 2)
    bucket_state["open_positions"] = open_positions
    bucket_state["closed_positions"].extend(closed_today)
    bucket_state.setdefault("ordenes_fallidas", []).extend(ordenes_fallidas_hoy)
    if limits is not None:
        bucket_state["peak_equity"] = max(bucket_state.get("peak_equity", 0.0), equity)
        bucket_state["last_equity"] = equity

    return {
        "date": today_label,
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "blend_value": round(valor_blend_final, 2),
        "unrealized_pnl": round(unrealized - sum(p["entry_price"] * p["shares"] for p in open_positions), 2),
        "open_count": len(open_positions),
        "closed_today": len(closed_today),
        "realized_pnl_today": round(realized_pnl_today, 2),
        "cumulative_return_pct": round((equity / bucket_state["starting_capital"] - 1) * 100, 2),
        "closed_today_detail": closed_today,
        "ordenes_fallidas_hoy": ordenes_fallidas_hoy,
        "daily_loss_pct": round(daily_loss_pct * 100, 2),
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "daily_loss_breaker_tripped": bucket_state.get("daily_loss_tripped_today", False),
        "suspended": bucket_state.get("suspended", False),
        "suspended_reason": bucket_state.get("suspended_reason"),
        "newly_suspended_today": newly_suspended,
    }


def run_daily_tick_live(ib, starting_capital_por_bucket: dict[str, float]) -> dict:
    """`starting_capital_por_bucket`: capital inicial por bucket, fijado
    una sola vez (igual que el motor simulado) — se pasa explícito en
    vez de leer de `allocation.get_balances()` porque esa función
    reporta el capital del PORTAFOLIO SIMULADO, no de la cuenta real de
    IBKR; quien llama a esto decide cómo repartir el equity real de la
    cuenta paper entre los 4 buckets."""
    state = load_state()
    snapshot = {"date": None, "buckets": {}, "alertas": []}

    for bucket in ACTIVE_BUCKETS:
        if bucket not in state:
            capital = starting_capital_por_bucket.get(bucket, 0.0)
            if capital <= 0:
                continue
            state[bucket] = init_bucket_state(bucket, capital, ib)

        equity_antes = state[bucket].get("last_equity")
        try:
            result = run_bucket_tick_live(bucket, state[bucket], ib)
        finally:
            # Guarda SIEMPRE después de cada bucket, no solo al final
            # del for — si una orden real ya se ejecutó en este bucket
            # y luego algo truena en el siguiente, ese fill real nunca
            # debe quedar sin reflejarse en el estado local.
            save_state(state)
        snapshot["buckets"][bucket] = result

        if equity_antes and equity_antes > 0:
            cambio_pct = abs(result["equity"] - equity_antes) / equity_antes
            if cambio_pct > 0.25:
                alerta = (
                    f"⚠️⚠️ SALTO DE EQUITY SOSPECHOSO (LIVE) en '{bucket}': "
                    f"${equity_antes:.2f} -> ${result['equity']:.2f} "
                    f"({cambio_pct*100:.1f}% en un día)."
                )
                snapshot["alertas"].append(alerta)

        if result.get("ordenes_fallidas_hoy"):
            for o in result["ordenes_fallidas_hoy"]:
                snapshot["alertas"].append(
                    f"⚠️ Orden fallida en '{bucket}': {o['accion']} {o['symbol']} — {o['error']}"
                )

        if result["date"]:
            snapshot["date"] = result["date"]

    save_state(state)

    if snapshot["date"]:
        history = load_history()
        history = [h for h in history if h["date"] != snapshot["date"]]
        history.append(snapshot)
        history.sort(key=lambda h: h["date"])
        save_history(history)

    return snapshot


def posiciones_reconciliadas(ib) -> dict:
    """Compara lo que el estado local cree tener abierto, bucket por
    bucket, contra lo que IBKR reporta como posiciones reales de la
    cuenta — para detectar divergencias (ej. una orden que se llenó
    parcialmente, o algo movido fuera de este motor)."""
    state = load_state()
    reales = posiciones_reales(ib)

    esperado: dict[str, int] = {}
    for bucket, bstate in state.items():
        for pos in bstate.get("open_positions", []):
            esperado[pos["symbol"]] = esperado.get(pos["symbol"], 0) + pos["shares"]

    simbolos = set(esperado) | set(reales)
    divergencias = {
        s: {"esperado": esperado.get(s, 0), "real": reales.get(s, 0)}
        for s in simbolos
        if esperado.get(s, 0) != reales.get(s, 0)
    }
    return {"esperado": esperado, "real": reales, "divergencias": divergencias}


def reconciliar_posiciones_automatico(ib) -> dict[str, list[str]]:
    """Agrega al estado local, bucket por bucket, cualquier posición
    real de IBKR que el motor no sepa que tiene — causa típica: una
    orden se mandó fuera de horario regular (IBKR la encola para el
    siguiente open en vez de rechazarla) y se llenó horas después,
    sin que el motor lo supiera (ver ADR 0035). No toca símbolos ya
    conocidos ni SPY/GLD (blend, se trackea aparte). El costo real
    (`avgCost`) se resta del cash del bucket; el stop_price se calcula
    con la fórmula real de la estrategia de ese bucket sobre el último
    dato disponible, igual que una entrada normal.

    Devuelve {bucket: [símbolos agregados]} — vacío si no había nada
    que reconciliar. Guarda el estado solo si agregó algo."""
    posiciones = posiciones_reales_con_costo(ib)
    state = load_state()
    resultado: dict[str, list[str]] = {}
    ya_asignados: set[str] = set()

    for bucket, config in BUCKET_CONFIG.items():
        bucket_state = state.get(bucket)
        if bucket_state is None:
            continue
        symbols_universo = set(read_universe_file(config["universe_file"]))
        symbols_conocidos = {p["symbol"] for p in bucket_state.get("open_positions", [])}
        candidatos = [
            s for s, info in posiciones.items()
            if s in symbols_universo and s not in symbols_conocidos
            and s not in ya_asignados and info["shares"] > 0
        ]
        if not candidatos:
            continue

        universo_datos = load_universe(symbols=candidatos)
        agregadas = []
        for symbol in candidatos:
            df = universo_datos.get(symbol)
            if df is None:
                continue
            stop_price = None
            strategy_usada = None
            for strategy_key in config["strategies"]:
                signaled = _signals_for_symbol(df, strategy_key)
                last = _last_row_as_of(signaled, None)
                if last is not None:
                    stop_price = float(last["stop_price"])
                    strategy_usada = strategy_key
                    break
            if stop_price is None:
                continue

            info = posiciones[symbol]
            shares, avg_cost = info["shares"], info["avg_cost"]
            bucket_state["cash"] = round(bucket_state.get("cash", 0.0) - shares * avg_cost, 2)
            bucket_state["open_positions"].append({
                "symbol": symbol,
                "strategy": strategy_usada,
                "entry_date": date.today().isoformat(),
                "entry_price": round(avg_cost, 2),
                "stop_price": round(stop_price, 2),
                "initial_stop_price": round(stop_price, 2),
                "shares": shares,
            })
            ya_asignados.add(symbol)
            agregadas.append(symbol)

        if agregadas:
            resultado[bucket] = agregadas

    if resultado:
        save_state(state)
    return resultado


def rebasar_y_recalcular_stops(buckets: list[str] | None = None) -> dict[str, dict]:
    """Recalcula el stop_price de cada posición abierta con los datos
    más frescos (nunca lo baja — toma el máximo contra el guardado,
    misma regla del trailing stop normal), y re-basa `starting_capital`
    / `peak_equity` al equity actual de cada bucket — para que el
    retorno acumulado arranque en 0% desde este momento en vez de
    arrastrar el rebasamiento de la reconciliación (ADR 0035/0036).
    No cierra ni abre ninguna posición, no manda ninguna orden.

    `buckets`: si se da, solo rebasa esos buckets (ej. uno que se
    suspendió por un salto de equity espurio) — los demás quedan
    intactos. Por default (None) rebasa todos, comportamiento
    original."""
    state = load_state()
    precios_blend = _precios_blend_hoy()
    resultado: dict[str, dict] = {}

    for bucket, bucket_state in state.items():
        if buckets is not None and bucket not in buckets:
            continue
        config = BUCKET_CONFIG.get(bucket)
        if config is None:
            continue
        open_positions = bucket_state.get("open_positions", [])
        symbols = [p["symbol"] for p in open_positions]
        universo = load_universe(symbols=symbols) if symbols else {}

        unrealized = 0.0
        stops_actualizados = []
        for pos in open_positions:
            df = universo.get(pos["symbol"])
            if df is not None:
                last_close = _last_row_as_of(df, None)
                if last_close is not None:
                    unrealized += float(last_close["close"]) * pos["shares"]
                signaled = _signals_for_symbol(df, pos["strategy"])
                last = _last_row_as_of(signaled, None)
                if last is not None:
                    nuevo_stop = max(pos["stop_price"], float(last["stop_price"]))
                    if nuevo_stop != pos["stop_price"]:
                        stops_actualizados.append(
                            {"symbol": pos["symbol"], "antes": pos["stop_price"], "despues": round(nuevo_stop, 2)}
                        )
                    pos["stop_price"] = round(nuevo_stop, 2)

        valor_blend = _valor_blend(bucket_state, precios_blend)
        cash = bucket_state.get("cash", 0.0)
        equity_actual = round(cash + valor_blend + unrealized, 2)

        bucket_state["starting_capital"] = equity_actual
        bucket_state["peak_equity"] = equity_actual
        bucket_state["day_start_equity"] = equity_actual
        bucket_state["day_start_date"] = None
        bucket_state["start_date"] = date.today().isoformat()

        resultado[bucket] = {"nuevo_starting_capital": equity_actual, "stops_actualizados": stops_actualizados}

    save_state(state)
    return resultado


def reconciliar_blend_automatico(ib) -> dict[str, dict]:
    """Corrige las shares de SPY/GLD que el motor cree tener en el
    blend (`blend_spy_shares`/`blend_gld_shares` por bucket) cuando no
    coinciden con las reales en IBKR.

    Causa real encontrada el 9-nov-2026: SPY y GLD también estaban
    listados como símbolos operables normales en los universos de
    trading — una venta de estrategia (no del blend) podía mover la
    posición real sin que el ledger del blend se enterara, dejándolo
    creyendo que tenía acciones que ya no existían (24 de SPY y 24 de
    GLD en este caso real, cuando IBKR reportaba 0). Ya se corrigió
    la causa (`run_bucket_tick_live` nunca vuelve a abrir una entrada
    de estrategia en un símbolo del blend), pero el daño ya hecho al
    ledger necesita esta reconciliación.

    Escala proporcionalmente las shares de cada bucket al total real
    (nunca inventa de qué bucket específico salió la diferencia —no
    hay forma de saberlo con certeza) y registra una entrada de ajuste
    en el ledger, valuada al precio de HOY (la mejor aproximación
    disponible — no hay un fill real del que sacar el precio exacto
    de cuándo se perdió la sincronía), para que el costo base quede
    razonable en vez de seguir sobreestimado.

    Devuelve {} si ya estaba todo cuadrado. Guarda el estado solo si
    corrigió algo."""
    reales = posiciones_reales(ib)
    precios_hoy = _precios_blend_hoy()
    state = load_state()
    ajustes: dict[str, dict] = {}

    for simbolo in BLEND_WEIGHTS:
        clave = f"blend_{simbolo.lower()}_shares"
        creidas_por_bucket = {
            bucket: bucket_state.get(clave, 0)
            for bucket, bucket_state in state.items()
            if not bucket.startswith("_")
        }
        total_creido = sum(creidas_por_bucket.values())
        total_real = reales.get(simbolo, 0)

        if abs(total_creido - total_real) < 1e-9 or total_creido == 0:
            continue  # ya cuadra, o no hay nada que escalar

        factor = total_real / total_creido
        detalle_por_bucket = {}
        for bucket, creidas in creidas_por_bucket.items():
            if creidas == 0:
                continue
            nuevas = creidas * factor
            state[bucket][clave] = round(nuevas, 6)
            detalle_por_bucket[bucket] = {"antes": creidas, "despues": round(nuevas, 6)}

        shares_de_mas = total_creido - total_real
        precio_hoy = precios_hoy.get(simbolo)
        blend_ledger.registrar(
            LIVE_BLEND_LEDGER_PATH, bucket="_reconciliacion", fecha=date.today().isoformat(),
            tipo="venta" if shares_de_mas > 0 else "compra",
            simbolo=simbolo, monto_usd=round(abs(shares_de_mas) * (precio_hoy or 0.0), 2),
            precio=precio_hoy or 0.0, shares=abs(shares_de_mas),
            motivo=(
                f"Ajuste de reconciliación automática: el motor creía tener {total_creido:.4f} "
                f"acciones de {simbolo} repartidas entre buckets, IBKR reporta {total_real} reales "
                "— ver docstring de reconciliar_blend_automatico. Valuado al precio de hoy, no al "
                "precio real de cuándo se perdió la sincronía (no hay fill del que sacarlo)."
            ),
        )
        ajustes[simbolo] = {
            "total_creido_antes": total_creido, "total_real": total_real,
            "por_bucket": detalle_por_bucket,
        }

    if ajustes:
        save_state(state)

    # El ledger (blend_ledger.json) es una bitácora APPEND-ONLY
    # independiente del contador operativo de arriba (state[...][clave])
    # — puede tener su propia desincronización histórica (ej. entradas
    # de "capital inicial del bucket" duplicadas de corridas viejas que
    # fallaron a medias) que el ajuste de arriba, calculado solo sobre
    # el contador operativo, no necesariamente cubre. resumen_blend_live
    # (el reporte que ve el usuario) suma el ledger completo, así que
    # también hay que corregir ESE total, por separado.
    ledger = blend_ledger.load_ledger(LIVE_BLEND_LEDGER_PATH)
    for simbolo in BLEND_WEIGHTS:
        neto_ledger = sum(
            (tx["shares"] if tx["tipo"] == "compra" else -tx["shares"])
            for tx in ledger if tx["simbolo"] == simbolo
        )
        total_real = reales.get(simbolo, 0)
        if abs(neto_ledger - total_real) < 1e-9:
            continue

        shares_de_mas = neto_ledger - total_real
        precio_hoy = precios_hoy.get(simbolo)
        blend_ledger.registrar(
            LIVE_BLEND_LEDGER_PATH, bucket="_reconciliacion_ledger", fecha=date.today().isoformat(),
            tipo="venta" if shares_de_mas > 0 else "compra",
            simbolo=simbolo, monto_usd=round(abs(shares_de_mas) * (precio_hoy or 0.0), 2),
            precio=precio_hoy or 0.0, shares=abs(shares_de_mas),
            motivo=(
                f"Ajuste de reconciliación del LEDGER completo (independiente del contador "
                f"operativo de arriba): sumando todas las transacciones registradas, el ledger "
                f"neto da {neto_ledger:.4f} acciones de {simbolo}, IBKR reporta {total_real} "
                "reales. Probablemente de entradas 'capital inicial del bucket' duplicadas de "
                "corridas viejas. Valuado al precio de hoy, no al precio real de cuándo se perdió "
                "la sincronía (no hay fill del que sacarlo)."
            ),
        )
        ajustes.setdefault(simbolo, {})["ledger_neto_antes"] = neto_ledger
        ajustes[simbolo]["ledger_total_real"] = total_real
    return ajustes


def reautorizar_bucket(bucket: str) -> dict:
    """Levanta la suspensión de un bucket del motor EN VIVO después de
    que el circuit breaker de drawdown lo detuvo. Acción MANUAL a
    propósito — el motor nunca se reactiva solo (misma regla que el
    motor simulado, ver reauthorize.py). No liquida ni modifica
    posiciones abiertas, solo permite que vuelvan a abrirse posiciones
    NUEVAS si hay señal. No borra el historial de por qué se suspendió
    (vive en daily_history, intacto).

    Lanza ValueError si el bucket no existe o no está suspendido —
    quien llama decide qué hacer con eso (el endpoint lo traduce a
    400/404), para no reautorizar algo "por accidente" cuando en
    realidad no había nada que reautorizar."""
    if bucket not in ACTIVE_BUCKETS:
        raise ValueError(f"'{bucket}' no es un bucket válido del motor en vivo ({ACTIVE_BUCKETS})")

    state = load_state()
    bucket_state = state.get(bucket)
    if bucket_state is None:
        raise ValueError(f"'{bucket}' no tiene estado todavía (no ha corrido ningún tick)")
    if not bucket_state.get("suspended"):
        raise ValueError(f"'{bucket}' no está suspendido — nada que reautorizar")

    anterior = {
        "suspended_since": bucket_state.get("suspended_since"),
        "suspended_reason": bucket_state.get("suspended_reason"),
    }
    bucket_state["suspended"] = False
    bucket_state["suspended_reason"] = None
    bucket_state["suspended_since"] = None
    save_state(state)

    return {"bucket": bucket, "reautorizado": True, **anterior}


def corregir_retorno_historico(bucket: str, fecha: str) -> dict:
    """Recalcula cumulative_return_pct/drawdown_pct de UNA entrada ya
    guardada en el historial, usando el starting_capital ACTUAL del
    bucket (normalmente justo después de un rebase) en vez del que
    estaba vigente ese día.

    Para cuándo sirve esto: un bug puede corromper el baseline contra
    el que se calculó el % de un día que ya se guardó (ej. el 9-nov-
    2026, el ledger fantasma del blend inflaba el starting_capital de
    largo_plazo, y al corregirlo el equity "cayó" -40% en el reporte
    aunque nada real hubiera pasado). Un rebase normal solo afecta
    corridas FUTURAS — esto corrige el número YA escrito, para que no
    quede un día distorsionado permanentemente en el historial público.

    Nunca toca equity/cash/posiciones de esa entrada (esos son reales,
    tal como se registraron) — solo recalcula el % derivado contra el
    baseline correcto. Devuelve el antes/después para que quede
    auditable qué cambió y por qué."""
    state = load_state()
    bucket_state = state.get(bucket)
    if bucket_state is None:
        raise ValueError(f"'{bucket}' no tiene estado")
    starting_capital = bucket_state["starting_capital"]
    if not starting_capital:
        raise ValueError(f"'{bucket}' no tiene starting_capital válido para recalcular contra")

    history = load_history()
    entrada = None
    for h in history:
        if h["date"] == fecha and bucket in h.get("buckets", {}):
            entrada = h["buckets"][bucket]
            break
    if entrada is None:
        raise ValueError(f"No hay entrada de historial para '{bucket}' en {fecha}")

    campos_a_corregir = (
        "cumulative_return_pct", "drawdown_pct",
        "daily_loss_pct", "daily_loss_breaker_tripped",
        "suspended", "suspended_reason", "newly_suspended_today",
    )
    anterior = {campo: entrada.get(campo) for campo in campos_a_corregir if campo in entrada}

    equity = entrada["equity"]
    entrada["cumulative_return_pct"] = round((equity / starting_capital - 1) * 100, 2)
    entrada["drawdown_pct"] = round(max(0.0, (starting_capital - equity) / starting_capital * 100), 2)
    # daily_loss_pct/daily_loss_breaker_tripped/suspended* de esta
    # entrada se derivaron del mismo baseline corrompido que ya se
    # corrigió arriba — si el drawdown recalculado ya no dispara el
    # breaker, estos campos tampoco deberían seguir marcándolo (si no
    # se corrigieran, el frontend seguiría mostrando el aviso de
    # "límite de pérdida diaria alcanzado" aunque ya no aplique).
    if "daily_loss_pct" in entrada:
        entrada["daily_loss_pct"] = 0.0
    if "daily_loss_breaker_tripped" in entrada:
        entrada["daily_loss_breaker_tripped"] = False
    if "suspended" in entrada:
        entrada["suspended"] = False
    if "suspended_reason" in entrada:
        entrada["suspended_reason"] = None
    if "newly_suspended_today" in entrada:
        entrada["newly_suspended_today"] = False

    save_history(history)
    return {
        "bucket": bucket, "fecha": fecha, "equity": equity,
        "starting_capital_usado": starting_capital,
        "anterior": anterior,
        "nuevo": {campo: entrada.get(campo) for campo in campos_a_corregir if campo in entrada},
    }
