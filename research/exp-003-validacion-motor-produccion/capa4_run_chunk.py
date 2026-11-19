"""Corre un bloque de réplicas placebo de UN bucket y las agrega a un
archivo JSON acumulado (`placebo_<bucket>.json`) — permite correr la
Capa 4 en varias llamadas cortas (cada una bajo el límite de 10 min de
una herramienta en primer plano) en vez de una sola corrida larga.

Uso: python3 capa4_run_chunk.py <bucket> <n_replicas> <seed_offset>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from capa4_placebo import (  # noqa: E402
    BENCHMARK, RAW_DIR, bootstrap_block_sequence, build_ratio_arrays,
    load_raw, run_replica,
)
from harness import BUCKETS, read_universe_file  # noqa: E402

MIN_RAW_ROWS = 500


def prep(bucket_key: str):
    cfg = BUCKETS[bucket_key]
    symbols = read_universe_file(Path(cfg["universe_file"]))
    all_symbols = list(dict.fromkeys(symbols + [BENCHMARK]))
    raw, excluidos = {}, []
    for s in all_symbols:
        p = RAW_DIR / f"{s}.parquet"
        if not p.exists():
            continue
        df = load_raw(s)
        if len(df) < MIN_RAW_ROWS:
            excluidos.append({"symbol": s, "filas": len(df)})
            continue
        raw[s] = df
    usable_symbols = [s for s in symbols if s in raw]
    common_dates = None
    for s in usable_symbols + [BENCHMARK]:
        if s not in raw:
            continue
        d = set(raw[s]["date"])
        common_dates = d if common_dates is None else (common_dates & d)
    aligned = {
        s: raw[s][raw[s]["date"].isin(common_dates)].sort_values("date").reset_index(drop=True)
        for s in usable_symbols + [BENCHMARK] if s in raw
    }
    ratios = {s: build_ratio_arrays(df) for s, df in aligned.items()}
    usable_symbols = [s for s in usable_symbols if s in aligned]
    return aligned, usable_symbols, ratios, excluidos, len(common_dates)


def main():
    bucket = sys.argv[1]
    n = int(sys.argv[2])
    seed_offset = int(sys.argv[3])
    out_path = Path(__file__).parent / f"placebo_{bucket}.json"

    existing = json.loads(out_path.read_text()) if out_path.exists() else {
        "bucket": bucket, "sharpes": [], "seeds_corridos": [], "per_replica_seconds": None,
    }

    aligned, usable_symbols, ratios, excluidos, n_dias = prep(bucket)
    existing["n_symbols_usables"] = len(usable_symbols)
    existing["excluidos_por_historia_corta"] = excluidos
    existing["n_dias_comunes"] = n_dias

    t0 = time.time()
    nuevos = 0
    for i in range(n):
        seed = 5000 + seed_offset + i
        if seed in existing["seeds_corridos"]:
            continue
        rng = np.random.default_rng(seed)
        sh = run_replica(bucket, aligned, usable_symbols, ratios, rng)
        if sh is not None:
            existing["sharpes"].append(sh)
            existing["seeds_corridos"].append(seed)
            nuevos += 1
    elapsed = time.time() - t0
    if nuevos:
        existing["per_replica_seconds"] = round(elapsed / nuevos, 3)

    out_path.write_text(json.dumps(existing, indent=2))
    print(f"{bucket}: +{nuevos} réplicas en {elapsed:.1f}s ({elapsed/max(nuevos,1):.2f}s/réplica) "
          f"-> total acumulado {len(existing['sharpes'])}")


if __name__ == "__main__":
    main()
