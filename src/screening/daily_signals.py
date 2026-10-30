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
from src.strategies.momentum_breakout import MomentumBreakoutParams
from src.strategies.trend_following import TrendFollowingParams

RISK_PCT_PER_TRADE = 0.01  # 1% del capital del bucket, por operación — ver docs/vision.md § 4.4


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


def today_signals(strategy_key: str, capital: float) -> pd.DataFrame:
    params_cls, signal_fn = STRATEGIES[strategy_key]
    params = params_cls()
    universe = load_universe()

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

        risk_amount = capital * RISK_PCT_PER_TRADE
        suggested_shares = int(risk_amount // risk_per_share)
        position_value = suggested_shares * entry_price

        if suggested_shares < 1:
            # El capital del bucket es tan chico que ni una acción cumple
            # el límite de riesgo del 1% — se reporta igual, en 0, para
            # que quede explícito por qué no hay operación sugerida.
            pass

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
    parser.add_argument("--capital", type=float, default=None, help="capital a usar (ignora --bucket si se da)")
    parser.add_argument("--bucket", default="mediano_plazo", choices=["largo_plazo", "mediano_plazo", "riesgo_alto", "muy_alta_volatilidad"])
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()) + ["all"],
        default="all",
    )
    args = parser.parse_args()

    capital = resolve_capital(args)
    strategies_to_run = list(STRATEGIES.keys()) if args.strategy == "all" else [args.strategy]

    print(f"\n=== Screener diario — capital: ${capital:.2f} · riesgo máx. por operación: {RISK_PCT_PER_TRADE*100:.0f}% ===")
    print("Esto es información para decidir, no una orden. Nada se ejecuta automáticamente.\n")

    any_signal = False
    for key in strategies_to_run:
        df = today_signals(key, capital)
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
                f"para respetar el {RISK_PCT_PER_TRADE*100:.0f}% de riesgo máximo con al menos 1 acción."
            )
        print()

    if not any_signal:
        print("Ninguna estrategia tiene señales hoy. No hay nada que operar.")


if __name__ == "__main__":
    main()
