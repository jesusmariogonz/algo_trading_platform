"""Screener diario — qué símbolos cumplen HOY las condiciones de
entrada de cada estrategia, y cuánto comprar según la regla de riesgo
del master prompt (1% máximo del capital del bucket por operación).

Esto NO ejecuta nada. Es información para que tú decidas y operes
manualmente en tu broker. No hay modo LIVE en este proyecto todavía —
ver docs/vision.md § 4.6.

Requiere datos actualizados: corre primero (en la MISMA sesión, el
mismo día que quieras operar):
    python -m src.data.download --universe config/universe.txt --years 5
    python -m src.indicators.compute
    python -m src.indicators.relative_strength --benchmark SPY

Uso:
    python -m src.screening.daily_signals --capital 300
    # o, si ya registraste inyecciones de capital:
    python -m src.screening.daily_signals --bucket mediano_plazo
"""

import argparse
from pathlib import Path

import pandas as pd

from src.backtesting.run import STRATEGIES, load_universe
from src.portfolio.allocation import get_balances

ROOT = Path(__file__).resolve().parents[2]

# Configuración por bucket: universo, riesgo por operación, y QUÉ
# estrategias corren ahí (Largo Plazo solo usa Time-Series Momentum,
# un horizonte de meses — correrle Trend Following/Momentum Breakout
# encima no tendría sentido, son estrategias de swing diario). Ver
# docs/adr/0003-buckets-y-escalamiento.md.
#
# El bucket "muy_alta_volatilidad" (cripto) se ELIMINÓ — ver
# docs/adr/0006-elimina-bucket-cripto.md. Cada bucket que queda usa
# BENCHMARK_SYMBOL (SPY) para invertir el cash ocioso en vez de dejarlo
# parado — ver paper_trading/engine.py.
# Riesgo por operación subido el 1-nov-2026 (ver ADR 0012): 1%->2% en
# Largo/Mediano Plazo, 2%->3% en Riesgo Alto — decisión explícita del
# usuario tras ver el trade-off real medido (retorno +37.21%->+48.25%,
# drawdown máximo 10.83%->18.77% en 36 meses de backtest).
BUCKET_CONFIG = {
    "largo_plazo": {
        "universe_file": ROOT / "config" / "universe_largo_plazo.txt",
        "risk_pct": 0.02,
        "strategies": ["time_series_momentum"],
    },
    "mediano_plazo": {
        "universe_file": ROOT / "config" / "universe.txt",
        "risk_pct": 0.02,
        "strategies": ["trend_following", "momentum_breakout"],
    },
    "riesgo_alto": {
        "universe_file": ROOT / "config" / "universe_riesgo_alto.txt",
        "risk_pct": 0.03,
        "strategies": ["trend_following", "momentum_breakout"],
    },
    # Bucket agregado el 1-nov-2026 (ver ADR 0019): Mean Reversion
    # RSI(2), lógica de entrada opuesta a los otros 3 (compra debilidad
    # temporal dentro de tendencia alcista, no fortaleza) — correlación
    # medida de 0.142 con el resto del sistema sobre datos reales
    # congelados, por eso corre con capital propio en vez de competir
    # por símbolo dentro de un bucket existente (lección de ADR 0018).
    "mean_reversion": {
        "universe_file": ROOT / "config" / "universe_mean_reversion.txt",
        "risk_pct": 0.02,
        "strategies": ["mean_reversion_rsi2"],
    },
}


def read_universe_file(path: Path) -> list[str]:
    symbols = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line)
    return symbols


def resolve_capital(args) -> float:
    if args.capital is not None:
        return args.capital
    balances = get_balances()
    capital = balances.get(args.bucket, 0.0)
    if capital <= 0:
        raise SystemExit(
            f"El bucket '{args.bucket}' no tiene capital registrado. "
            "Usa --capital <monto> para una corrida de prueba, o registra una "
            "inyección primero: python -m src.portfolio.allocation inject <monto>"
        )
    return capital


def today_signals(strategy_key: str, capital: float, bucket: str) -> pd.DataFrame:
    params_cls, signal_fn = STRATEGIES[strategy_key]
    params = params_cls()
    config = BUCKET_CONFIG[bucket]
    symbols = read_universe_file(config["universe_file"])
    risk_pct = config["risk_pct"]
    universe = load_universe(symbols=symbols)

    rows = []
    for symbol, df in universe.items():
        df = signal_fn(df, params)
        df = df.dropna(subset=["sma_200", "atr_14"]).reset_index(drop=True)
        if df.empty:
            continue

        last = df.iloc[-1]
        if last["signal"] != 1:
            continue

        entry_price = float(last["close"])
        stop_price = float(last["stop_price"])
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            continue  # dato inconsistente, no sugerir una operación con riesgo cero o negativo

        risk_amount = capital * risk_pct
        suggested_shares = int(risk_amount // risk_per_share)
        position_value = suggested_shares * entry_price

        rows.append(
            {
                "symbol": symbol,
                "date": str(last["date"].date()) if hasattr(last["date"], "date") else str(last["date"]),
                "entry_price": round(entry_price, 2),
                "stop_price": round(stop_price, 2),
                "risk_per_share": round(risk_per_share, 2),
                "suggested_shares": suggested_shares,
                "position_value": round(position_value, 2),
                "pct_of_capital": round(100 * position_value / capital, 2) if capital else 0,
            }
        )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capital", type=float, default=None, help="capital a usar (ignora el libro de allocation.py si se da)")
    parser.add_argument("--bucket", default="mediano_plazo", choices=list(BUCKET_CONFIG.keys()))
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()) + ["all"],
        default="all",
        help="limita a una estrategia específica (debe ser una de las que corren en ese bucket)",
    )
    args = parser.parse_args()

    capital = resolve_capital(args)
    config = BUCKET_CONFIG[args.bucket]
    risk_pct = config["risk_pct"]
    bucket_strategies = config["strategies"]
    if args.strategy == "all":
        strategies_to_run = bucket_strategies
    elif args.strategy not in bucket_strategies:
        raise SystemExit(
            f"La estrategia '{args.strategy}' no corre en el bucket '{args.bucket}' "
            f"(ahí corren: {', '.join(bucket_strategies)})"
        )
    else:
        strategies_to_run = [args.strategy]

    print(f"\n=== Screener diario [{args.bucket}] — capital: ${capital:.2f} · riesgo máx. por operación: {risk_pct*100:.0f}% ===")
    print("Esto es información para decidir, no una orden. Nada se ejecuta automáticamente.\n")

    any_signal = False
    for key in strategies_to_run:
        df = today_signals(key, capital, args.bucket)
        print(f"--- {key} ---")
        if df.empty:
            print("  Sin señales hoy.\n")
            continue
        any_signal = True
        print(df.to_string(index=False))
        sin_tamano = df[df["suggested_shares"] < 1]
        if not sin_tamano.empty:
            print(
                f"\n  ⚠ {len(sin_tamano)} símbolo(s) con señal pero capital insuficiente "
                f"para respetar el {risk_pct*100:.0f}% de riesgo máximo con al menos 1 acción."
            )
        print()

    if not any_signal:
        print("Ninguna estrategia tiene señales hoy. No hay nada que operar.")


if __name__ == "__main__":
    main()
