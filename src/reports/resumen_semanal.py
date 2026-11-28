"""Resumen semanal de TODOS los motores (IBKR en vivo, paper simulado y
Reverse Winners), por día y por activo comprado, más candidatos de la
semana siguiente. Solo cifras: la narrativa del mercado (por qué subió o
bajó cada cosa) la agrega la rutina del viernes con fuentes, en los campos
`mercado` y `notas_activos` del JSON — este módulo nunca inventa causas.

    python -m src.reports.resumen_semanal --fin 2026-11-27 \
        --export /tmp/export_vivo.json \
        --rw /home/user/pulso-research-lab/experiments/EXP-005-reverse-winners/run_paper_portfolio/paper_portfolio.json \
        --salida /home/user/jesus-site/lib/resumen-semanal-trading.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
PAPER_STATE = ROOT / "data" / "paper_trading" / "state.json"
PAPER_HISTORY = ROOT / "data" / "paper_trading" / "history.json"
BUCKETS = ("largo_plazo", "mediano_plazo", "riesgo_alto")
UMBRAL_CERCA_DE_STOP_PCT = 3.0


def _cierres(symbol: str) -> pd.Series:
    df = pd.read_parquet(PROCESSED / f"{symbol}.parquet").sort_values("date")
    return df.set_index(pd.to_datetime(df["date"]))["close"].astype(float)


def dias_de_la_semana(calendario: pd.DatetimeIndex, fin: str) -> list[pd.Timestamp]:
    """Días de mercado de la semana (lunes a viernes) que termina en `fin`."""
    fin_ts = pd.Timestamp(fin)
    lunes = fin_ts - pd.Timedelta(days=fin_ts.weekday())
    return [d for d in calendario if lunes <= d <= fin_ts]


def filas_por_dia(posiciones: list[dict], cierres: dict[str, pd.Series], dias: list[pd.Timestamp],
                  calendario: pd.DatetimeIndex) -> dict[str, list[dict]]:
    """P&L de cada activo en cada día. Referencia: el precio de entrada si se
    compró ese día, si no el cierre del día de mercado anterior; fin: el
    precio de salida si se vendió ese día, si no el cierre."""
    salida: dict[str, list[dict]] = {}
    for d in dias:
        previo = calendario[calendario.get_loc(d) - 1]
        filas = []
        for p in posiciones:
            entrada = pd.Timestamp(p["entry_date"])
            sale = pd.Timestamp(p["exit_date"]) if p.get("exit_date") else None
            if entrada > d or (sale is not None and sale < d):
                continue
            serie = cierres.get(p["symbol"])
            if serie is None or d not in serie.index:
                continue
            ref = p["entry_price"] if entrada == d else float(serie.get(previo, p["entry_price"]))
            fin = p["exit_price"] if sale == d else float(serie[d])
            filas.append({
                "symbol": p["symbol"],
                "bucket": p["bucket"],
                "shares": p["shares"],
                "accion": "comprada" if entrada == d else ("vendida" if sale == d else "mantenida"),
                "precio_referencia": round(ref, 2),
                "precio_fin": round(fin, 2),
                "cambio_pct": round((fin / ref - 1) * 100, 2),
                "pnl_usd": round(p["shares"] * (fin - ref), 2),
            })
        salida[d.strftime("%Y-%m-%d")] = sorted(filas, key=lambda f: f["pnl_usd"])
    return salida


def activos_de_la_semana(posiciones: list[dict], cierres: dict[str, pd.Series], dias: list[pd.Timestamp],
                         por_dia: dict[str, list[dict]]) -> list[dict]:
    """Una fila por activo que se tuvo en cartera durante la semana, con el
    P&L total desde su entrada (no solo de la semana) y el de la semana."""
    primero, ultimo = dias[0], dias[-1]
    filas = []
    for p in posiciones:
        entrada = pd.Timestamp(p["entry_date"])
        sale = pd.Timestamp(p["exit_date"]) if p.get("exit_date") else None
        if entrada > ultimo or (sale is not None and sale < primero):
            continue
        actual = p["exit_price"] if sale is not None else float(cierres[p["symbol"]].iloc[-1])
        pnl_semana = sum(f["pnl_usd"] for fs in por_dia.values() for f in fs
                         if f["symbol"] == p["symbol"] and f["bucket"] == p["bucket"])
        filas.append({
            "symbol": p["symbol"],
            "bucket": p["bucket"],
            "shares": p["shares"],
            "fecha_entrada": p["entry_date"],
            "precio_entrada": round(p["entry_price"], 2),
            "estado": "cerrada" if sale is not None else "abierta",
            "fecha_salida": p.get("exit_date"),
            "precio_actual_o_salida": round(actual, 2),
            "pnl_total_usd": round(p["shares"] * (actual - p["entry_price"]), 2),
            "pnl_total_pct": round((actual / p["entry_price"] - 1) * 100, 2),
            "pnl_semana_usd": round(pnl_semana, 2),
        })
    return sorted(filas, key=lambda f: f["pnl_total_usd"])


def _posiciones(buckets: dict) -> list[dict]:
    out = []
    for bucket in BUCKETS:
        b = buckets.get(bucket) or {}
        for p in (b.get("open_positions") or []) + (b.get("closed_positions") or []):
            out.append({"bucket": bucket, "symbol": p["symbol"], "shares": p["shares"],
                        "entry_date": p["entry_date"], "entry_price": float(p["entry_price"]),
                        "exit_date": p.get("exit_date"), "exit_price": p.get("exit_price"),
                        "strategy": p.get("strategy"), "stop_price": p.get("stop_price")})
    return out


def _equity_por_dia(historias: dict[str, list[dict]], dias: list[pd.Timestamp]) -> list[dict]:
    """Equity total por día (suma de buckets) y su variación contra el día anterior disponible."""
    fechas = sorted({h["date"] for hs in historias.values() for h in hs})
    total = {f: sum(h["equity"] for hs in historias.values() for h in hs if h["date"] == f) for f in fechas}
    filas = []
    for d in dias:
        f = d.strftime("%Y-%m-%d")
        if f not in total:
            continue
        previas = [x for x in fechas if x < f]
        ant = total[previas[-1]] if previas else None
        filas.append({"fecha": f, "equity": round(total[f], 2),
                      "pnl_dia_usd": round(total[f] - ant, 2) if ant is not None else None,
                      "pnl_dia_pct": round((total[f] / ant - 1) * 100, 2) if ant else None})
    return filas


def motor(id_: str, nombre: str, buckets: dict, historias: dict, cierres, dias, calendario) -> dict:
    posiciones = _posiciones(buckets)
    for p in posiciones:
        if p["symbol"] not in cierres:
            cierres[p["symbol"]] = _cierres(p["symbol"])
    por_dia = filas_por_dia(posiciones, cierres, dias, calendario)
    equity = _equity_por_dia(historias, dias)
    for fila in equity:
        fila["activos"] = por_dia.get(fila["fecha"], [])
    return {"id": id_, "nombre": nombre, "dias": equity,
            "activos_semana": activos_de_la_semana(posiciones, cierres, dias, por_dia)}


def motor_reverse_winners(ruta: Path, dias: list[pd.Timestamp]) -> dict:
    d = json.loads(Path(ruta).read_text())
    fechas = {x["fecha"]: x for x in d["historial_diario"]}
    ordenadas = sorted(fechas)
    filas = []
    for dia in dias:
        f = dia.strftime("%Y-%m-%d")
        if f not in fechas:
            continue
        previas = [x for x in ordenadas if x < f]
        ant = fechas[previas[-1]]["equity"] if previas else None
        compradas = [p["ticker"] for p in d["posiciones_abiertas"] if p["entry_fecha"] == f]
        eq = fechas[f]["equity"]
        filas.append({"fecha": f, "equity": eq,
                      "pnl_dia_usd": round(eq - ant, 2) if ant is not None else None,
                      "pnl_dia_pct": round((eq / ant - 1) * 100, 2) if ant else None,
                      "compradas": len(compradas), "tickers_comprados": sorted(compradas)})
    return {"id": "reverse_winners", "nombre": "Reverse Winners (paper portfolio, EXP-005)", "dias": filas,
            "n_posiciones_abiertas": d["n_posiciones_abiertas"], "efectivo": d["efectivo"],
            "primeras_ventas_estimadas": "tras 30 sesiones de mercado desde cada compra (las del 27-nov, ≈ 12-ene-2027)"}


def candidatos(export: dict, paper_state: dict) -> dict:
    """Compras: señal de entrada activa en la última vela y aún sin posición.
    Ventas/vigilar: posiciones abiertas con señal de salida o a ≤3% de su stop."""
    from src.paper_trading.engine import _signals_for_symbol, _last_row_as_of
    from src.screening.daily_signals import BUCKET_CONFIG, today_signals

    compra, vigilar = [], []
    abiertas_vivo = {(b, p["symbol"]) for b in BUCKETS for p in (export["buckets"].get(b) or {}).get("open_positions", [])}
    for bucket in BUCKETS:
        capital = (export["buckets"][bucket]["daily_history"] or [{}])[-1].get("equity") or export["buckets"][bucket]["starting_capital"]
        descartes = {(c["symbol"], c["strategy"]): c["reason"]
                     for c in ((export["buckets"][bucket]["daily_history"] or [{}])[-1].get("discarded_candidates_today") or [])}
        for strategy in BUCKET_CONFIG[bucket]["strategies"]:
            df = today_signals(strategy, capital, bucket)
            for _, r in df.iterrows():
                if (bucket, r["symbol"]) in abiertas_vivo:
                    continue
                compra.append({"symbol": r["symbol"], "bucket": bucket, "estrategia": strategy,
                               "fecha_dato": r["date"], "precio_entrada": r["entry_price"], "stop": r["stop_price"],
                               "acciones_sugeridas": int(r["suggested_shares"]),
                               "motivo_no_entro": descartes.get((r["symbol"], strategy)) or
                               ("capital_insuficiente" if int(r["suggested_shares"]) < 1 else None)})
    from src.backtesting.run import load_universe
    for fuente, buckets in (("vivo", export["buckets"]), ("paper", paper_state)):
        for bucket in BUCKETS:
            for p in (buckets.get(bucket) or {}).get("open_positions", []):
                df = load_universe(symbols=[p["symbol"]]).get(p["symbol"])
                if df is None:
                    continue
                last = _last_row_as_of(_signals_for_symbol(df, p["strategy"]), None)
                if last is None:
                    continue
                cierre = float(last["close"])
                dist = (cierre / p["stop_price"] - 1) * 100
                salida = int(last["signal"]) == -1
                if salida or dist <= UMBRAL_CERCA_DE_STOP_PCT:
                    vigilar.append({"symbol": p["symbol"], "bucket": bucket, "motor": fuente, "cierre": round(cierre, 2),
                                    "stop": round(p["stop_price"], 2), "distancia_al_stop_pct": round(dist, 2),
                                    "senal_de_salida": salida})
    return {"compra": sorted(compra, key=lambda c: (c["bucket"], c["symbol"])), "vigilar_venta": vigilar}


def construir(fin: str, export: dict, paper_state: dict, paper_history: list[dict], rw_path: Path | None) -> dict:
    spy = _cierres("SPY")
    calendario = spy.index
    dias = dias_de_la_semana(calendario, fin)
    cierres: dict[str, pd.Series] = {"SPY": spy}
    historias_vivo = {b: export["buckets"][b]["daily_history"] for b in BUCKETS}
    historias_paper = {b: [{"date": h["date"], "equity": h["buckets"][b]["equity"]} for h in paper_history if b in h["buckets"]]
                       for b in BUCKETS}
    motores = [
        motor("ibkr_vivo", "Motor IBKR (paper de IBKR)", export["buckets"],
              historias_vivo, cierres, dias, calendario),
        motor("paper_simulado", "Paper trading simulado", paper_state, historias_paper, cierres, dias, calendario),
    ]
    if rw_path:
        motores.append(motor_reverse_winners(rw_path, dias))
    mercado = []
    for d in dias:
        f = d.strftime("%Y-%m-%d")
        previo = calendario[calendario.get_loc(d) - 1]
        fila = {"fecha": f}
        for s in ("SPY", "QQQ", "IJR", "GLD"):
            c = cierres.setdefault(s, _cierres(s))
            fila[s.lower() + "_pct"] = round((c[d] / c[previo] - 1) * 100, 2)
        mercado.append(fila)
    return {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "semana": {"inicio": dias[0].strftime("%Y-%m-%d"), "fin": dias[-1].strftime("%Y-%m-%d")},
            "mercado": {"dias": mercado, "narrativa": [], "fuentes": []},
            "notas_activos": {},
            "motores": motores,
            "candidatos": candidatos(export, paper_state)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fin", required=True, help="viernes (o último día de mercado) de la semana, YYYY-MM-DD")
    ap.add_argument("--export", required=True, help="JSON de /live/exportar")
    ap.add_argument("--rw", default=None, help="paper_portfolio.json de Reverse Winners")
    ap.add_argument("--salida", required=True)
    args = ap.parse_args(argv)
    resumen = construir(args.fin, json.loads(Path(args.export).read_text()),
                        json.loads(PAPER_STATE.read_text()), json.loads(PAPER_HISTORY.read_text()),
                        Path(args.rw) if args.rw else None)
    Path(args.salida).write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    print(f"Resumen semanal {resumen['semana']['inicio']} → {resumen['semana']['fin']} escrito en {args.salida}")


if __name__ == "__main__":
    main()
