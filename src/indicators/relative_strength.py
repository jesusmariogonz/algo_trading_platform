"""Fuerza relativa frente a un benchmark (por defecto SPY).

Se calcula aparte de compute.py porque requiere cruzar cada símbolo
contra el benchmark por fecha — compute.py opera símbolo por símbolo
sin contexto del resto del universo.

relative_strength_63 = retorno 63 sesiones (~3 meses) del símbolo
                        dividido entre el retorno 63 sesiones del
                        benchmark en el mismo período.
  > 1  -> el símbolo superó al benchmark en esa ventana
  < 1  -> el símbolo quedó por debajo

Debe correr DESPUÉS de src/indicators/compute.py (requiere que
data/processed/<BENCHMARK>.parquet ya exista).
"""

import argparse
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def compute_relative_strength(df: pd.DataFrame, benchmark: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    bench = benchmark[["date", "adj_close"]].rename(columns={"adj_close": "bench_close"})
    merged = df.merge(bench, on="date", how="left")

    symbol_return = merged["adj_close"] / merged["adj_close"].shift(window)
    bench_return = merged["bench_close"] / merged["bench_close"].shift(window)
    merged[f"relative_strength_{window}"] = symbol_return / bench_return

    return merged.drop(columns=["bench_close"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--window", type=int, default=63)
    args = parser.parse_args()

    bench_path = PROCESSED_DIR / f"{args.benchmark}.parquet"
    if not bench_path.exists():
        raise SystemExit(
            f"No se encontró {bench_path}. Corre primero src.data.download y "
            f"src.indicators.compute, asegurándote de incluir {args.benchmark} "
            "en config/universe.txt."
        )
    benchmark = pd.read_parquet(bench_path)

    files = sorted(PROCESSED_DIR.glob("*.parquet"))
    for path in files:
        df = pd.read_parquet(path)
        df = compute_relative_strength(df, benchmark, window=args.window)
        df.to_parquet(path, index=False)
        print(f"  {path.stem}: relative_strength_{args.window} agregado")

    print(f"\nFuerza relativa calculada para {len(files)} símbolos (benchmark: {args.benchmark})")


if __name__ == "__main__":
    main()
