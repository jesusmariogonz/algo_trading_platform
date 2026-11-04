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
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from src.broker.ibkr_adapter import conectar, desconectar, equity_de_cuenta, equity_de_cuenta_usd
from src.portfolio.allocation import BUCKETS, get_usd_mxn_rate
from src.paper_trading import live_engine

API_TOKEN = os.environ["TRADING_API_TOKEN"]
ROOT = Path(__file__).resolve().parents[2]
UNIVERSO_LIVE = ROOT / "config" / "universe_live_4_buckets.txt"

app = FastAPI()


def _correr(*args: str) -> None:
    """Corre un script del repo como subproceso (mismo intérprete que
    uvicorn, mismo venv) y propaga cualquier falla con su stdout/stderr
    — para que el error se vea completo en el 500, no solo el código
    de salida."""
    resultado = subprocess.run(
        [sys.executable, "-m", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"Falló '{' '.join(args)}' (exit {resultado.returncode}):\n{resultado.stdout}\n{resultado.stderr}"
        )


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
