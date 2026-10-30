"""Cross-Sectional Momentum — selección y ranking, no una señal de
entrada/salida por símbolo como las demás estrategias.

Investigación base: Jegadeesh & Titman (1993), "Returns to Buying
Winners and Selling Losers", Journal of Finance. Compraron ganadores
y vendieron perdedores con periodos de formación/tenencia de 3-12
meses.

Reglas (adaptadas de la propuesta del usuario, solo LONG — mismo
motivo que en time_series_momentum.py, sin infraestructura de
shorting):
  1. Calcular el retorno de 6 meses de cada símbolo del universo.
  2. Excluir los que están por debajo de su SMA 200 (filtro de
     tendencia — no comprar "ganadores" que ya perdieron su tendencia).
  3. Ordenar de mayor a menor retorno.
  4. Seleccionar el 20% superior.
  5. Repetir mensualmente (rebalanceo).

Esto es un MÉTODO DE SELECCIÓN, no una estrategia de trading
completa con su propio motor de entradas/salidas diarias — por eso
no se registra en STRATEGIES (src/backtesting/run.py) junto a las
demás. Se usa para decidir QUÉ símbolos priorizar dentro de un
universo más grande del que hay capital para operar — ver
rank_universe() y el backtest de portafolio mensual en
src/backtesting/cross_sectional_backtest.py.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class CrossSectionalMomentumParams:
    id: str = "cross_sectional_momentum_v1"
    name: str = "Cross-Sectional Momentum (ranking 6m, top 20%)"
    version: str = "0.1.0"
    lookback_days: int = 126  # ~6 meses
    top_pct: float = 0.20


def rank_universe(
    universe: dict[str, pd.DataFrame],
    as_of_date: pd.Timestamp,
    params: CrossSectionalMomentumParams = CrossSectionalMomentumParams(),
) -> pd.DataFrame:
    """Rankea el universo a una fecha dada. Devuelve un DataFrame con
    symbol, return_6m, above_sma200, selected — ordenado de mejor a
    peor retorno. `selected=True` para el top_pct que además pasa el
    filtro de SMA 200 (los demás quedan fuera aunque su retorno sea
    alto, si ya perdieron la tendencia)."""
    rows = []
    for symbol, df in universe.items():
        snapshot = df[df["date"] <= as_of_date]
        if snapshot.empty:
            continue
        last = snapshot.iloc[-1]
        if pd.isna(last.get("sma_200")) or pd.isna(last.get("return_126d")):
            continue
        rows.append(
            {
                "symbol": symbol,
                "date": last["date"],
                "return_6m": float(last["return_126d"]),
                "close": float(last["close"]),
                "sma_200": float(last["sma_200"]),
                "above_sma200": bool(last["close"] > last["sma_200"]),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["symbol", "date", "return_6m", "close", "sma_200", "above_sma200", "rank", "selected"]
        )

    ranking = pd.DataFrame(rows).sort_values("return_6m", ascending=False).reset_index(drop=True)

    cutoff = max(1, int(len(ranking) * params.top_pct))
    ranking["rank"] = ranking.index + 1
    ranking["selected"] = (ranking["rank"] <= cutoff) & ranking["above_sma200"]
    return ranking
