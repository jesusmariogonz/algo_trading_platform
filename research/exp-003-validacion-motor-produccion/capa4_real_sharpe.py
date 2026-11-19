"""Sharpe REAL (secuencia identidad, sin bootstrap) bajo el MISMO
pipeline de reconstrucción que usa el placebo (reconstruye OHLCV desde
razones + recalcula indicadores desde cero) — para comparar manzanas
con manzanas contra la distribución placebo, no contra el número
cacheado de Capa 1/7 (que usa `data/processed/` ya calculado, no esta
reconstrucción). Cualquier diferencia con Capa 1/7 se documenta, no se
oculta."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from capa4_run_chunk import prep  # noqa: E402
from capa4_placebo import BUCKETS, run_replica  # noqa: E402


def main():
    out = {}
    for bucket in BUCKETS:
        aligned, usable_symbols, ratios, excluidos, n_dias = prep(bucket)
        n_returns = n_dias - 1
        identity_seq = np.arange(n_returns)

        # Parchea bootstrap_block_sequence para devolver la secuencia
        # identidad (orden histórico real, sin reordenar nada) —
        # mismo código de reconstrucción/indicadores, cero bootstrap.
        import capa4_placebo as cp
        original = cp.bootstrap_block_sequence
        cp.bootstrap_block_sequence = lambda n, b, rng: identity_seq
        try:
            sharpe_real = run_replica(bucket, aligned, usable_symbols, ratios, np.random.default_rng(0))
        finally:
            cp.bootstrap_block_sequence = original

        out[bucket] = {"sharpe_real_reconstruido": sharpe_real, "n_dias": n_dias}
        print(bucket, out[bucket])

    Path(__file__).parent.joinpath("sharpe_real_reconstruido.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
