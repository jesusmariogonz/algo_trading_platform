# ADR 0006 — Elimina el bucket Muy Alta Volatilidad (cripto)

## Estado
Aceptado. Reemplaza la decisión original de ADR 0004 (mantener el
bucket pese al backtest negativo, "porque el usuario lo definió como
apuestas arriesgadas") — la evidencia acumulada de varias ventanas de
backtest hizo que el usuario decidiera eliminarlo, no solo documentarlo.

## Contexto
A partir de un ejercicio exploratorio (simular el modelo de buckets
con capital real: $1,000 inicial + $3,000 MXN/mes, con datos reales de
mercado), se compararon varias configuraciones sobre 3 ventanas de
tiempo distintas:

| Ventana | Con cripto (10%) | Sin cripto, repartido proporcional | Sin cripto, todo al mejor bucket |
|---|---|---|---|
| 6 meses (may-oct 2026) | +3.98% | — | — |
| 22 meses (ene 2025-oct 2026) | +17.12% / +17.75% (ajustado) | +20.64% | +19.70% |
| 34 meses (ene 2024-oct 2026) | +29.92% | **+34.10%** | +33.34% |

En las 3 ventanas probadas, sin excepción, eliminar el bucket de
cripto mejoró el resultado total — nunca lo empeoró. El bucket
`muy_alta_volatilidad` individualmente rindió negativo en las 3
ventanas (-2.78%, -4.37%, -3.03% en sus versiones comparables), de la
mano con lo ya documentado en ADR 0004 (BTC -46.9% en el backtest
original de Trend Following, SOL -54%/XRP -59% en Momentum/Breakout).

## Decisión
Se elimina el bucket `muy_alta_volatilidad` (cripto) de
`src/screening/daily_signals.py` (`BUCKET_CONFIG`) y de
`src/paper_trading/engine.py` (`ACTIVE_BUCKETS`, `BENCHMARK_SYMBOL`).

El 10% de capital que tenía se reparte **EQUITATIVAMENTE** entre los 3
buckets restantes (+10%/3 = +3.33 puntos cada uno), no proporcional a
su tamaño original — decisión explícita del usuario, distinta de la
alternativa "proporcional" (44.4/33.3/22.3) que también se probó y
rindió un poco menos bien en las 3 ventanas (+20.64%/+34.10% vs.
+19.70%/+33.34% para la variante "todo al mejor bucket", pero ninguna
de las dos es la elegida):

| Bucket | Antes | Ahora |
|---|---|---|
| Largo plazo | 40% | **43.33%** (40 + 10/3) |
| Mediano plazo | 30% | **33.33%** (30 + 10/3) |
| Riesgo alto | 20% | **23.33%** (20 + 10/3) |
| Muy alta volatilidad | 10% | — (eliminado) |

Ver `BUCKETS` en `src/portfolio/allocation.py`.

## Qué NO cambia
- Los Quant Portfolios (`src/quant_portfolios/`) siguen usando BTC
  como parte de Aggressive Momentum (10% de ese modelo) — es un
  producto completamente separado, con su propio Risk Engine, y esta
  decisión no lo afecta. Cripto no desaparece del proyecto, solo del
  modelo de 4 (ahora 3) buckets por horizonte.
- `src/data/download_crypto.py` y `config/universe_cripto.txt` se
  mantienen sin cambios (siguen usados para investigación y por los
  Quant Portfolios vía BTC).
- ADR 0004 se mantiene como está — documenta el backtest original,
  sigue siendo la evidencia histórica correcta aunque la decisión que
  motivó cambió.

## Pendiente
- Se reinició `data/portfolio/ledger.json` y
  `data/paper_trading/{state,history}.json` al aplicar este cambio
  (igual que se hizo con los cambios de capital anteriores) — el
  historial de paper trading con cripto queda en el historial de git,
  no se pierde, pero el tracking en vivo arranca de nuevo con el
  modelo de 3 buckets.
