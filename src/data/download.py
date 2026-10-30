"""Descarga histórico diario OHLCV para un universo de símbolos.

Fuente: yfinance (gratuita, suficiente para investigación/backtest;
no apta para datos en tiempo real de producción — eso se decide en
una fase posterior, ver docs/adr/0001-data-provider.md).

Guarda un Parquet por símbolo en data/raw/<symbol>.parquet con
columnas: date, open, high, low, close, adj_close, volume.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def read_universe(path: str) -> list[str]:
    symbols = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols


def download_symbol(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise ValueError(f"Sin datos para {symbol} entre {start} y {end}")

    # yfinance con un solo símbolo a veces devuelve columnas MultiIndex.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index.name = "date"
    df = df.reset_index()
    df["symbol"] = symbol
    return df[["date", "symbol", "open", "high", "low", "close", "adj_close", "volume"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="config/universe.txt")
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    symbols = read_universe(args.universe)
    end = datetime.today()
    start = end - timedelta(days=365 * args.years)

    ok, failed = [], []
    for symbol in symbols:
        try:
            df = download_symbol(symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            out_path = RAW_DIR / f"{symbol}.parquet"
            df.to_parquet(out_path, index=False)
            print(f"  {symbol}: {len(df)} filas -> {out_path}")
            ok.append(symbol)
        except Exception as e:
            print(f"  {symbol}: FALLÓ ({e})", file=sys.stderr)
            failed.append(symbol)

    print(f"\nDescargados: {len(ok)}/{len(symbols)}")
    if failed:
        print(f"Fallaron: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
