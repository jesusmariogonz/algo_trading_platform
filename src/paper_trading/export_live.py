"""Exporta el estado del motor de paper trading EN VIVO (IBKR real,
ver live_engine.py) a los mismos tres artefactos que export.py genera
para el motor simulado — snapshot, histórico acumulativo de
operaciones y bitácora diaria de equity por bucket — pero en archivos
separados, para no mezclar resultados reales con la simulación.

Reusa toda la lógica de fusión (append_historico/append_bitacora) de
export.py: esas funciones solo dependen de la forma del diccionario
`buckets`, no de si vino del motor simulado o del motor en vivo.

Uso:
    python -m src.paper_trading.export_live /ruta/a/jesus-site/lib/trading-snapshot-vivo.json [/ruta/a/jesus-site/lib/trading-historico-vivo.json] [/ruta/a/jesus-site/lib/trading-bitacora-vivo.json]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.backtesting.run import load_universe
from src.paper_trading import blend_bucket, live_engine
from src.paper_trading.engine import BLEND_WEIGHTS
from src.paper_trading.export import _con_precio_en_vivo, append_bitacora, append_historico
from src.portfolio.asset_types import asset_type_de


def build_export_live() -> dict:
    state = live_engine.load_state()
    history = live_engine.load_history()

    buckets = {}
    for bucket, bucket_state in state.items():
        history_for_bucket = [
            {"date": h["date"], **h["buckets"][bucket]}
            for h in history
            if bucket in h["buckets"]
        ]
        buckets[bucket] = {
            "starting_capital": bucket_state["starting_capital"],
            "open_positions": _con_precio_en_vivo(bucket_state["open_positions"]),
            "closed_positions": [
                {**p, "asset_type": asset_type_de(p["symbol"])} for p in bucket_state["closed_positions"]
            ],
            "daily_history": history_for_bucket,
            "suspended": bucket_state.get("suspended", False),
        }

    precios_blend = {}
    try:
        universo_blend = load_universe(symbols=list(BLEND_WEIGHTS))
        for simbolo, df in universo_blend.items():
            if not df.empty:
                precios_blend[simbolo] = float(df.sort_values("date")["close"].iloc[-1])
    except SystemExit:
        pass  # faltan datos procesados para SPY/GLD: el bucket de blend simplemente no se agrega

    resumen_blend = blend_bucket.resumen_blend_live(live_engine.LIVE_BLEND_LEDGER_PATH, precios_blend)
    if resumen_blend is not None:
        buckets[blend_bucket.BLEND_BUCKET_KEY] = resumen_blend

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "algo_trading_platform motor EN VIVO (cuenta paper real de IBKR, ver ADR 0022/0023)",
        "buckets": buckets,
    }


def main():
    export = build_export_live()
    payload = json.dumps(export, indent=2, ensure_ascii=False)

    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload)
        print(f"Exportado a {out_path}")

        if len(sys.argv) > 2:
            historico_path = Path(sys.argv[2])
            filas = append_historico(export["buckets"], historico_path)
            print(f"Histórico (vivo) actualizado en {historico_path} ({len(filas)} operaciones)")

        if len(sys.argv) > 3:
            bitacora_path = Path(sys.argv[3])
            filas_bitacora = append_bitacora(export["buckets"], bitacora_path)
            print(f"Bitácora (vivo) actualizada en {bitacora_path} ({len(filas_bitacora)} renglones)")
    else:
        print(payload)


if __name__ == "__main__":
    main()
