"""Exporta el estado de paper trading a un JSON que jesus-site
consume (misma idea que el snapshot manual de backtest — ver
docs/adr/0002-dashboard-hosting.md). Corre esto después de
run_daily_tick para que el dashboard de /trading se vea al día.

Uso:
    python -m src.paper_trading.export /ruta/a/jesus-site/lib/paper-trading-snapshot.json [/ruta/a/jesus-site/lib/trading-historico.json] [/ruta/a/jesus-site/lib/trading-bitacora.json]

El segundo argumento (opcional) es un histórico acumulativo: una
operación por renglón (bucket+symbol+entry_date como llave única),
que se actualiza cada vez que corre el export en vez de sobreescribirse
— mientras la posición sigue abierta se refresca con el precio/stop
actual, y al cerrarse queda fija con sus valores finales. A diferencia
de paper-trading-snapshot.json (que SÍ se sobreescribe completo en
cada tick), este archivo nunca pierde una fila ya escrita.

El tercer argumento (opcional, requiere el segundo) es una bitácora
diaria: un renglón por bucket por día (fecha+bucket como llave única)
con equity/retorno/drawdown/abiertas/cerradas/win rate de ese bucket a
esa fecha — para ver la evolución del portafolio en el tiempo, no solo
el estado actual. Si la rutina corre dos veces el mismo día, la
segunda corrida actualiza el renglón de hoy en vez de duplicarlo."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.backtesting.run import load_universe
from src.paper_trading.engine import load_history, load_state
from src.portfolio.allocation import get_usd_mxn_rate
from src.portfolio.asset_types import asset_type_de


def _tipo_de_cambio_hoy() -> dict:
    """Tipo de cambio USD->MXN del día, para que jesus-site pueda
    mostrar todo el dashboard en pesos sin inventar un número — si la
    API falla (ver allocation.get_usd_mxn_rate), se omite el campo y
    el frontend debe mostrar USD con una nota, nunca un tipo de cambio
    viejo o estimado."""
    try:
        rate = get_usd_mxn_rate()
    except Exception:
        return {"usd_mxn_rate": None, "usd_mxn_rate_fecha": None}
    return {
        "usd_mxn_rate": round(rate, 4),
        "usd_mxn_rate_fecha": datetime.now(timezone.utc).date().isoformat(),
    }


def _con_precio_en_vivo(open_positions: list[dict]) -> list[dict]:
    """Agrega precio actual y P&L no realizado a cada posición abierta,
    usando el mismo dato procesado (data/processed/<symbol>.parquet)
    que ya usa el motor para el tick del día — no descarga nada nuevo,
    no inventa un precio: si falta el dato procesado de algún símbolo,
    esa posición se exporta sin precio en vivo en vez de fallar el
    export completo."""
    if not open_positions:
        return open_positions

    symbols = sorted({p["symbol"] for p in open_positions})
    try:
        universe = load_universe(symbols=symbols)
    except SystemExit:
        return open_positions  # faltan datos procesados para algún símbolo: no bloquea el export

    enriquecidas = []
    for pos in open_positions:
        df = universe.get(pos["symbol"])
        precio_actual = float(df.sort_values("date")["close"].iloc[-1]) if df is not None and not df.empty else None
        nueva = dict(pos)
        nueva["asset_type"] = asset_type_de(pos["symbol"])
        if precio_actual is not None:
            valor_actual = precio_actual * pos["shares"]
            costo_entrada = pos["entry_price"] * pos["shares"]
            nueva["current_price"] = round(precio_actual, 4)
            nueva["unrealized_pnl"] = round(valor_actual - costo_entrada, 2)
            nueva["unrealized_pnl_pct"] = round((valor_actual / costo_entrada - 1) * 100, 2)
        enriquecidas.append(nueva)
    return enriquecidas


def build_export() -> dict:
    state = load_state()
    history = load_history()

    buckets = {}
    for bucket, bucket_state in state.items():
        history_for_bucket = [
            {"date": h["date"], **h["buckets"][bucket]}
            for h in history
            if bucket in h["buckets"]
        ]
        buckets[bucket] = {
            "starting_capital": bucket_state["starting_capital"],
            "start_date": bucket_state["start_date"],
            "open_positions": _con_precio_en_vivo(bucket_state["open_positions"]),
            "closed_positions": [
                {**p, "asset_type": asset_type_de(p["symbol"])} for p in bucket_state["closed_positions"]
            ],
            "daily_history": history_for_bucket,
            "suspended": bucket_state.get("suspended", False),
            "suspended_reason": bucket_state.get("suspended_reason"),
            "suspended_since": bucket_state.get("suspended_since"),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "algo_trading_platform paper trading engine (simulado, sin dinero real)",
        "buckets": buckets,
        **_tipo_de_cambio_hoy(),
    }


BUCKET_LABELS = {
    "largo_plazo": "Largo Plazo",
    "mediano_plazo": "Mediano Plazo",
    "riesgo_alto": "Riesgo Alto",
}


def _fila_historico(bucket: str, p: dict, estado: str) -> dict:
    return {
        "bucket": bucket,
        "bucket_label": BUCKET_LABELS.get(bucket, bucket),
        "symbol": p["symbol"],
        "asset_type": p.get("asset_type") or asset_type_de(p["symbol"]),
        "estado": estado,
        "entry_date": p.get("entry_date"),
        "entry_price": p.get("entry_price"),
        "initial_stop_price": p.get("initial_stop_price"),
        "exit_date": p.get("exit_date"),
        "exit_price": p.get("exit_price"),
        "current_price": p.get("current_price"),
        "stop_price": p.get("stop_price"),
        "pnl": p.get("pnl") if estado == "Cerrada" else p.get("unrealized_pnl"),
        "pnl_pct": p.get("pnl_pct") if estado == "Cerrada" else p.get("unrealized_pnl_pct"),
        "reason": p.get("reason"),
        "actualizado": datetime.now(timezone.utc).isoformat(),
    }


def _fila_bitacora(bucket: str, data: dict, fecha: str) -> dict:
    historial = data["daily_history"]
    ultimo = historial[-1] if historial else None
    equity = ultimo["equity"] if ultimo else data["starting_capital"]
    retorno_pct = ultimo["cumulative_return_pct"] if ultimo else 0.0
    drawdown_pct = ultimo["drawdown_pct"] if ultimo else 0.0
    cerradas = data["closed_positions"]
    ganadoras = sum(1 for p in cerradas if p.get("pnl", 0) > 0)

    return {
        "fecha": fecha,
        "bucket": bucket,
        "bucket_label": BUCKET_LABELS.get(bucket, bucket),
        "capital_inicial": data["starting_capital"],
        "equity": round(equity, 2),
        "ganancia_perdida": round(equity - data["starting_capital"], 2),
        "retorno_pct": retorno_pct,
        "drawdown_pct": drawdown_pct,
        "abiertas": len(data["open_positions"]),
        "cerradas": len(cerradas),
        "ganadoras": ganadoras,
        "win_rate_pct": round(ganadoras / len(cerradas) * 100, 1) if cerradas else None,
        "suspended": data.get("suspended", False),
        "actualizado": datetime.now(timezone.utc).isoformat(),
    }


def append_bitacora(buckets: dict, bitacora_path: Path, fecha: str | None = None) -> list[dict]:
    """Bitácora diaria: un renglón por bucket por día (fecha+bucket como
    llave única), con equity/retorno/drawdown/abiertas/cerradas/win rate
    de ese bucket a esa fecha. Si la rutina corre dos veces el mismo día
    (apertura y cierre), la segunda corrida actualiza el renglón de hoy
    en vez de duplicarlo — el histórico de días anteriores nunca se toca."""
    fecha = fecha or datetime.now(timezone.utc).date().isoformat()

    existentes: dict[str, dict] = {}
    if bitacora_path.exists():
        try:
            for fila in json.loads(bitacora_path.read_text()):
                llave = f"{fila['fecha']}:{fila['bucket']}"
                existentes[llave] = fila
        except (json.JSONDecodeError, KeyError):
            existentes = {}  # bitácora corrupta o con formato viejo: empieza limpio en vez de fallar el export

    for bucket, data in buckets.items():
        llave = f"{fecha}:{bucket}"
        existentes[llave] = _fila_bitacora(bucket, data, fecha)

    filas = sorted(existentes.values(), key=lambda f: (f["fecha"], f["bucket"]))
    bitacora_path.parent.mkdir(parents=True, exist_ok=True)
    bitacora_path.write_text(json.dumps(filas, indent=2, ensure_ascii=False))
    return filas


def append_historico(buckets: dict, historico_path: Path) -> list[dict]:
    """Funde las posiciones del export actual sobre el histórico ya
    guardado en historico_path (si existe), usando bucket+symbol+entry_date
    como llave única por operación. Una posición cerrada deja de
    actualizarse en corridas futuras una vez que ya quedó marcada
    'Cerrada' con sus valores finales."""
    existentes: dict[str, dict] = {}
    if historico_path.exists():
        try:
            for fila in json.loads(historico_path.read_text()):
                llave = f"{fila['bucket']}:{fila['symbol']}:{fila.get('entry_date')}"
                existentes[llave] = fila
        except (json.JSONDecodeError, KeyError):
            existentes = {}  # histórico corrupto o con formato viejo: empieza limpio en vez de fallar el export

    for bucket, data in buckets.items():
        for p in data["open_positions"]:
            llave = f"{bucket}:{p['symbol']}:{p.get('entry_date')}"
            existentes[llave] = _fila_historico(bucket, p, "Abierta")
        for p in data["closed_positions"]:
            llave = f"{bucket}:{p['symbol']}:{p.get('entry_date')}"
            existentes[llave] = _fila_historico(bucket, p, "Cerrada")

    filas = sorted(existentes.values(), key=lambda f: (f["entry_date"] or "", f["bucket"], f["symbol"]))
    historico_path.parent.mkdir(parents=True, exist_ok=True)
    historico_path.write_text(json.dumps(filas, indent=2, ensure_ascii=False))
    return filas


def main():
    export = build_export()
    payload = json.dumps(export, indent=2, ensure_ascii=False)

    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload)
        print(f"Exportado a {out_path}")

        if len(sys.argv) > 2:
            historico_path = Path(sys.argv[2])
            filas = append_historico(export["buckets"], historico_path)
            print(f"Histórico actualizado en {historico_path} ({len(filas)} operaciones)")

        if len(sys.argv) > 3:
            bitacora_path = Path(sys.argv[3])
            filas_bitacora = append_bitacora(export["buckets"], bitacora_path)
            print(f"Bitácora actualizada en {bitacora_path} ({len(filas_bitacora)} renglones)")
    else:
        print(payload)


if __name__ == "__main__":
    main()
