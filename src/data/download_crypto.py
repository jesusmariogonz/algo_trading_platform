"""Descarga histórico diario OHLCV de criptomonedas desde la API
pública de Kraken (sin API key — datos de mercado son públicos).

Por qué Kraken y no CCXT+Binance (lo que sugería el stack original
del master prompt): Binance está bloqueado desde este entorno (HTTP
451). Se probó también la API gratuita de CoinGecko, pero su
granularidad de velas se degrada a 4 días para historiales largos en
el tier gratuito — inútil para indicadores diarios (SMA 200, ATR 14).
Kraken da hasta 720 velas diarias REALES (open/high/low/close/volumen)
por símbolo sin autenticación. Ver docs/adr/0004-bucket-cripto.md.

Limitación real, no oculta: Kraken solo da ~2 años de historia diaria
por esta vía (no 5 como las acciones) — el walk-forward/backtest de
cripto va a tener menos ventanas que el de acciones.

Cripto opera 24/7; cada vela diaria de Kraken está anclada a
medianoche UTC — se trata como "un día de mercado" igual que una
sesión bursátil, sin cambios al resto del pipeline (indicadores,
estrategias, paper trading).

Mismo esquema de salida que src/data/download.py: un Parquet por
símbolo en data/raw/<symbol>.parquet con columnas date, symbol, open,
high, low, close, adj_close, volume (adj_close = close: no hay
splits/dividendos en cripto).
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"

# Símbolo amigable -> par de Kraken (altname). Ver AssetPairs de Kraken
# para encontrar más; algunos activos usan prefijo X/Z por legado.
KRAKEN_PAIR_MAP = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "SOL": "SOLUSD",
    "XRP": "XRPUSD",
    "ADA": "ADAUSD",
    "AVAX": "AVAXUSD",
    "DOT": "DOTUSD",
    "LINK": "LINKUSD",
    "LTC": "LTCUSD",
}


def read_universe(path: str) -> list[str]:
    symbols = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols


def download_symbol(symbol: str) -> pd.DataFrame:
    pair = KRAKEN_PAIR_MAP.get(symbol)
    if not pair:
        raise ValueError(f"'{symbol}' no está en KRAKEN_PAIR_MAP — agrégalo primero.")

    resp = requests.get(KRAKEN_OHLC_URL, params={"pair": pair, "interval": 1440}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise ValueError(f"Kraken devolvió error para {symbol} ({pair}): {payload['error']}")

    result_key = next(k for k in payload["result"] if k != "last")
    rows = payload["result"][result_key]
    if not rows:
        raise ValueError(f"Sin datos para {symbol} ({pair})")

    df = pd.DataFrame(
        rows, columns=["timestamp", "open", "high", "low", "close", "vwap", "volume", "count"]
    )
    df["date"] = pd.to_datetime(df["timestamp"], unit="s")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["adj_close"] = df["close"]
    df["symbol"] = symbol

    return df[["date", "symbol", "open", "high", "low", "close", "adj_close", "volume"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="config/universe_cripto.txt")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    symbols = read_universe(args.universe)

    ok, failed = [], []
    for symbol in symbols:
        try:
            df = download_symbol(symbol)
            out_path = RAW_DIR / f"{symbol}.parquet"
            df.to_parquet(out_path, index=False)
            print(f"  {symbol}: {len(df)} filas ({df['date'].min().date()} -> {df['date'].max().date()}) -> {out_path}")
            ok.append(symbol)
            time.sleep(0.5)  # cortesía con la API pública de Kraken
        except Exception as e:
            print(f"  {symbol}: FALLÓ ({e})", file=sys.stderr)
            failed.append(symbol)

    print(f"\nDescargados: {len(ok)}/{len(symbols)}")
    if failed:
        print(f"Fallaron: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
