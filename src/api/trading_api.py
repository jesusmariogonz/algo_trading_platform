"""API HTTP que corre en la VM de Google Cloud, junto a IB Gateway/IBC
(ver ADR 0022), para que las Routines disparen el motor de paper
trading EN VIVO (ADR 0023) sin necesitar SSH — solo HTTPS con token,
vía el reverse proxy de Caddy en https://ibkr.jgonzalez.app.

Esta app reemplaza la versión mínima que se creó a mano directo en la
VM durante la validación inicial (solo tenía /health) — desde aquí en
adelante el código de la API vive versionado en el repo, no solo en
el filesystem de la VM.

Correr con:
  TRADING_API_TOKEN=... uvicorn src.api.trading_api:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from src.broker.ibkr_adapter import (
    OrdenNoLlenada,
    conectar,
    desconectar,
    ejecutar_orden_mercado,
    equity_de_cuenta,
    equity_de_cuenta_usd,
    posiciones_reales_con_costo,
)
from src.portfolio.allocation import BUCKETS, get_usd_mxn_rate
from src.paper_trading import live_engine

API_TOKEN = os.environ["TRADING_API_TOKEN"]
ROOT = Path(__file__).resolve().parents[2]
UNIVERSO_LIVE = ROOT / "config" / "universe_live_4_buckets.txt"

app = FastAPI()


def _correr(*args: str, env: dict | None = None) -> None:
    """Corre un script del repo como subproceso (mismo intérprete que
    uvicorn, mismo venv) y propaga cualquier falla con su stdout/stderr
    — para que el error se vea completo en el 500, no solo el código
    de salida."""
    resultado = subprocess.run(
        [sys.executable, "-m", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"Falló '{' '.join(args)}' (exit {resultado.returncode}):\n{resultado.stdout}\n{resultado.stderr}"
        )


def _git_pull() -> str:
    resultado = subprocess.run(
        ["git", "pull", "origin", "main"], cwd=ROOT, capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"git pull falló:\n{resultado.stdout}\n{resultado.stderr}")
    return resultado.stdout


def _reiniciar_proceso_despues_de_responder() -> None:
    """No usa `systemctl restart` (requeriría sudo desde dentro del
    proceso) — simplemente termina este proceso después de un segundo,
    para que la respuesta HTTP ya se haya mandado. El servicio tiene
    `Restart=always` (ver ADR 0022), así que systemd lo vuelve a
    levantar solo, con el código ya actualizado por el git pull."""
    time.sleep(1)
    os._exit(0)


def _equity_usd_con_fallback(ib) -> float:
    """La cuenta paper real de este proyecto no tiene segmento en USD
    todavía (nunca se ha comprado nada en dólares) — solo reporta en
    MXN. Si `equity_de_cuenta_usd` no encuentra el desglose en USD,
    convierte el equity en MXN al tipo de cambio del día (misma fuente
    que ya usa el dashboard, `allocation.get_usd_mxn_rate`)."""
    try:
        return equity_de_cuenta_usd(ib)
    except RuntimeError:
        equity_mxn = equity_de_cuenta(ib)
        return equity_mxn / get_usd_mxn_rate()


def _verificar_token(authorization: str | None) -> None:
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Token inválido")


@app.get("/health")
def health(authorization: str | None = Header(None)):
    _verificar_token(authorization)
    return {"status": "ok", "gateway_port_esperado": 4002}


@app.post("/admin/desplegar")
def desplegar(authorization: str | None = Header(None)):
    """git pull + pytest + reinicio del servicio, en una sola llamada
    HTTPS — para no tener que pedirle al usuario que corra esto a mano
    en la VM cada vez que hay código nuevo. Si los tests fallan, NO
    reinicia (el código en disco ya quedó actualizado por el pull,
    pero el proceso sigue corriendo con el código viejo hasta que se
    corrija y se vuelva a desplegar)."""
    _verificar_token(authorization)

    git_output = _git_pull()
    # Los tests fijan su propio TRADING_API_TOKEN de prueba vía
    # os.environ.setdefault, pero eso no pisa el token REAL que ya
    # está en el entorno de este servicio (vía systemd) — sin este
    # override, pytest corrido como subproceso aquí hereda el token
    # real, los tests comparan contra "token-de-prueba" y los 13
    # tests que golpean endpoints protegidos fallan con 401 aunque el
    # código esté bien (causa real del primer 500 de este endpoint).
    entorno_tests = os.environ.copy()
    entorno_tests.pop("TRADING_API_TOKEN", None)
    _correr("pytest", "-q", env=entorno_tests)

    threading.Thread(target=_reiniciar_proceso_despues_de_responder, daemon=True).start()
    return {"status": "ok", "git_pull": git_output, "mensaje": "tests pasaron, reiniciando en ~1s"}


@app.post("/live/ejecutar")
def ejecutar_live(authorization: str | None = Header(None)):
    """Corre un día del motor en vivo para los 4 buckets (ADR 0023) y
    devuelve el snapshot. Idempotente: igual que el motor simulado, si
    ya se corrió hoy, re-correrlo reemplaza el snapshot de hoy en vez
    de duplicarlo (lo garantiza `live_engine.save_history`)."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        state = live_engine.load_state()
        capital_por_bucket = {}
        if not state:
            # Primera corrida: reparte el equity REAL de la cuenta
            # (en USD, no en la moneda base MXN de la cuenta) con las
            # mismas proporciones que el portafolio simulado.
            equity_usd = _equity_usd_con_fallback(ib)
            capital_por_bucket = {bucket: equity_usd * pct for bucket, pct in BUCKETS.items()}

        snapshot = live_engine.run_daily_tick_live(ib, capital_por_bucket)
    finally:
        desconectar(ib)

    return snapshot


@app.post("/live/refrescar-datos-y-ejecutar")
def refrescar_datos_y_ejecutar_live(authorization: str | None = Header(None)):
    """Pensado para dispararse desde un cron/Routine automática, sin
    pasos intermedios: descarga el universo combinado de los 4 buckets
    (config/universe_live_4_buckets.txt), recalcula indicadores y
    fuerza relativa, y corre el motor en vivo — todo en una sola
    llamada HTTPS, para que una rutina externa no tenga que orquestar
    varios pasos por separado (y no necesite más acceso que HTTPS)."""
    _verificar_token(authorization)

    _correr("src.data.download", "--universe", str(UNIVERSO_LIVE))
    _correr("src.indicators.compute")
    _correr("src.indicators.relative_strength", "--universe", str(UNIVERSO_LIVE))

    return ejecutar_live(authorization)


@app.get("/live/estado")
def estado_live(authorization: str | None = Header(None)):
    """Último snapshot guardado, sin ejecutar nada ni conectar a
    Gateway — para consultar estado sin arriesgar mandar órdenes."""
    _verificar_token(authorization)
    history = live_engine.load_history()
    return history[-1] if history else {"date": None, "buckets": {}, "alertas": []}


@app.post("/admin/live/reiniciar-capital")
def reiniciar_capital_live(total_usd: float, authorization: str | None = Header(None)):
    """Reinicializa el capital de los 3 buckets del motor en vivo a un
    monto total fijo (repartido con las mismas proporciones que
    `BUCKETS`), en vez de usar el equity real de la cuenta — para
    poder operar con un subconjunto del capital disponible (ej.
    limitar a $2,000 USD aunque la cuenta tenga más), sin tener que
    editar `data/paper_trading_live/state.json` a mano en la VM.

    Por seguridad, se niega a tocar cualquier bucket que tenga
    posiciones abiertas (`open_positions`) — en ese caso hay que
    cerrarlas primero, no se cierran solas aquí."""
    _verificar_token(authorization)

    if total_usd <= 0:
        raise HTTPException(status_code=400, detail="total_usd debe ser positivo")

    ib = conectar()
    try:
        state = live_engine.load_state()
        for bucket, bucket_state in state.items():
            if bucket_state.get("open_positions"):
                raise HTTPException(
                    status_code=409,
                    detail=f"El bucket '{bucket}' tiene posiciones abiertas — ciérralas antes de reiniciar capital.",
                )

        nuevo_estado = {
            bucket: live_engine.init_bucket_state(bucket, total_usd * pct, ib)
            for bucket, pct in BUCKETS.items()
        }
        live_engine.save_state(nuevo_estado)
    finally:
        desconectar(ib)

    return nuevo_estado


@app.get("/live/equity")
def equity_live(authorization: str | None = Header(None)):
    """Equity real de la cuenta IBKR en este momento, sin ejecutar
    nada ni tocar el estado del motor — solo lectura, para validar
    cosas como el reset de balance de la cuenta paper sin tener que
    entrar a la VM a correr un script a mano."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        equity_usd = _equity_usd_con_fallback(ib)
    finally:
        desconectar(ib)

    return {"equity_usd": equity_usd}


@app.post("/admin/live/fijar-estado-bucket")
def fijar_estado_bucket_live(
    bucket: str,
    cash: float,
    blend_spy_shares: int = 0,
    blend_gld_shares: int = 0,
    authorization: str | None = Header(None),
):
    """Corrige a mano cash/acciones de blend de UN bucket ya existente
    — para reparar una divergencia puntual entre el estado local y las
    posiciones reales de IBKR (ej. tras un bug de contabilidad),
    sin tener que editar `state.json` en la VM. No crea buckets
    nuevos ni toca `starting_capital`/posiciones abiertas; se niega
    si el bucket no existe o tiene `open_positions`."""
    _verificar_token(authorization)

    state = live_engine.load_state()
    if bucket not in state:
        raise HTTPException(status_code=404, detail=f"Bucket '{bucket}' no existe en el estado actual")
    if state[bucket].get("open_positions"):
        raise HTTPException(
            status_code=409,
            detail=f"El bucket '{bucket}' tiene posiciones abiertas — no se puede corregir así.",
        )

    state[bucket]["cash"] = round(cash, 2)
    state[bucket]["blend_spy_shares"] = blend_spy_shares
    state[bucket]["blend_gld_shares"] = blend_gld_shares
    live_engine.save_state(state)
    return state[bucket]


@app.post("/admin/live/limpiar-blend-ledger")
def limpiar_blend_ledger_live(authorization: str | None = Header(None)):
    """Vacía el ledger de transacciones del blend del motor en vivo —
    para usarse SOLO si el archivo quedó contaminado con datos de
    prueba (ej. precios irreales que nunca pasaron en el mercado real),
    nunca como operación de rutina. No toca `state.json` ni las
    posiciones reales en IBKR, solo el historial de transacciones."""
    _verificar_token(authorization)
    live_engine.blend_ledger.save_ledger(live_engine.LIVE_BLEND_LEDGER_PATH, [])
    return {"status": "ok", "mensaje": "blend_ledger.json vaciado"}


@app.get("/live/blend-ledger")
def blend_ledger_live(authorization: str | None = Header(None)):
    """Ledger de transacciones del blend del motor en vivo (ADR 0028),
    sin ejecutar nada — para diagnosticar divergencias entre lo que
    el estado local cree y lo que IBKR reporta, sin tener que pedir
    el archivo manualmente en la VM."""
    _verificar_token(authorization)
    return live_engine.blend_ledger.load_ledger(live_engine.LIVE_BLEND_LEDGER_PATH)


@app.post("/admin/live/liquidar-todo")
def liquidar_todo_live(authorization: str | None = Header(None)):
    """Vende TODAS las posiciones reales de la cuenta (a mercado,
    hasta dejarlas en 0) — para limpiar divergencias serias entre el
    estado local y la cuenta real, antes de reinicializar el capital
    con `/admin/live/reiniciar-capital`. No toca `state.json`; eso se
    hace aparte. Reporta por símbolo si se vendió bien o falló."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        posiciones = posiciones_reales_con_costo(ib)
        resultados = {}
        for symbol, info in posiciones.items():
            shares = info["shares"]
            if shares == 0:
                continue
            accion = "SELL" if shares > 0 else "BUY"  # BUY para cerrar una posición corta
            try:
                fill = ejecutar_orden_mercado(ib, symbol, accion, abs(shares))
                resultados[symbol] = {
                    "status": "vendido", "shares": fill.shares, "precio": fill.precio_promedio,
                }
            except OrdenNoLlenada as e:
                resultados[symbol] = {"status": "fallo", "error": str(e)}
    finally:
        desconectar(ib)

    return resultados


@app.post("/admin/live/vender-simbolo")
def vender_simbolo_live(symbol: str, shares: int, authorization: str | None = Header(None)):
    """Vende (a mercado) un símbolo puntual que el estado local NO
    trackea — ej. un residuo huérfano que no pertenece a ningún
    universo actual (como FOXA, encontrado el 2026-11-08). No toca
    `state.json`: si el símbolo SÍ está en una posición trackeada,
    usa el flujo normal del motor (cierre por señal/stop), no este
    endpoint."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        try:
            fill = ejecutar_orden_mercado(ib, symbol, "SELL", shares)
        except OrdenNoLlenada as e:
            return {"status": "encolada_o_fallida", "detalle": str(e)}
    finally:
        desconectar(ib)

    return {"status": "vendido", "shares": fill.shares, "precio": fill.precio_promedio}


@app.post("/admin/live/rebasar-y-recalcular-stops")
def rebasar_y_recalcular_stops_live(authorization: str | None = Header(None)):
    """Recalcula el stop_price de cada posición abierta con el dato
    más fresco (solo lo sube, nunca lo baja) y re-basa
    starting_capital/peak_equity al equity actual de cada bucket —
    para que el retorno acumulado arranque en 0% desde este momento,
    sin cerrar ni abrir ninguna posición ni mandar ninguna orden."""
    _verificar_token(authorization)
    return live_engine.rebasar_y_recalcular_stops()


@app.get("/live/posiciones-reales")
def posiciones_reales_live(authorization: str | None = Header(None)):
    """Posiciones reales en IBKR con su costo promedio real
    (`avgCost`) — para reconciliar el estado local contra la cuenta
    cuando hay divergencias, sin tener que pedir esto a mano en la
    VM. Solo lectura, no ejecuta nada."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        posiciones = posiciones_reales_con_costo(ib)
    finally:
        desconectar(ib)

    return posiciones


@app.get("/live/reconciliar")
def reconciliar_live(authorization: str | None = Header(None)):
    """Compara posiciones que el estado local cree tener abiertas
    contra las posiciones reales reportadas por IBKR."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        resultado = live_engine.posiciones_reconciliadas(ib)
    finally:
        desconectar(ib)

    return resultado


@app.post("/admin/live/reconciliar-automatico")
def reconciliar_automatico_live(authorization: str | None = Header(None)):
    """Agrega al estado local cualquier posición real de IBKR que el
    motor no sepa que tiene (ADR 0035) — causa típica: una orden
    quedó encolada fuera de horario y se llenó horas después sin que
    el motor se enterara. No toca símbolos ya conocidos. Seguro de
    llamar aunque no haya nada que reconciliar (devuelve {})."""
    _verificar_token(authorization)

    ib = conectar()
    try:
        resultado = live_engine.reconciliar_posiciones_automatico(ib)
    finally:
        desconectar(ib)

    return resultado


@app.get("/live/exportar")
def exportar_live(authorization: str | None = Header(None)):
    """Snapshot del motor EN VIVO (posiciones abiertas/cerradas,
    equity y drawdown por bucket) en el mismo formato que usa
    export.py para el motor simulado — para que una rutina externa
    (sin acceso SSH a esta VM) pueda fundirlo sobre el histórico y la
    bitácora que ya tiene en jesus-site, igual que ya hace con el
    motor simulado. Solo lee estado local (state.json + history.json
    + datos procesados en disco), nunca se conecta a IBKR — rápido y
    sin riesgo de interferir con una corrida en curso."""
    _verificar_token(authorization)

    from src.paper_trading.export_live import build_export_live

    return build_export_live()
