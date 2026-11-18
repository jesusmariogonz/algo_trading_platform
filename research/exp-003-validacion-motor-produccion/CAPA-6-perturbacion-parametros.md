# EXP-003 — Capa 6: Superficie de perturbación de parámetros

Código: `capa6_perturbacion.py`. Mismo motor de simulación que las
Capas 1 y 7 (`simulate_bucket` del harness de ADR 0040 — capital
compartido, sizing por riesgo sobre equity actual, trailing stop,
fricción real), corrido sobre todo el período disponible
(2021-11-22 a 2026-11-17, sin ventanas — eso ya lo hizo la Capa 1).
Cada parámetro continuo real de cada estrategia de producción se
perturba ±10%/±20%, uno a la vez, los demás fijos en su valor de
producción.

`breakout_window` de `momentum_breakout` (20 o 55) se excluyó a
propósito: es un switch discreto entre dos columnas precomputadas
(`high_20`/`high_55`), no un valor continuo perturbable en un grid.

El criterio pre-registrado usa la banda "±15%" — como el grid corrido
es ±10%/±20%, solo los puntos ±10% (estrictamente dentro de ±15%)
deciden el label; ±20% se reporta como contexto adicional, nunca
decide por sí solo.

## Resultado por bucket

### largo_plazo (`time_series_momentum`) — `atr_stop_multiple`

| Perturbación | Valor | Sharpe | Retorno | Trades |
|---|---|---|---|---|
| -20% | 2.4 | 1.37 | +102.85% | 92 |
| -10% | 2.7 | 1.10 | +84.26% | 94 |
| **0%** | **3.0** | **0.78** | **+45.96%** | **96** |
| +10% | 3.3 | 0.52 | +27.87% | 90 |
| +20% | 3.6 | 0.64 | +37.45% | 89 |

**Label: VALIDATED** (caída máxima dentro de ±10%: 33.3%, en +10%).

### mediano_plazo (`trend_following`) — `atr_stop_multiple`

| Perturbación | Valor | Sharpe | Retorno | Trades |
|---|---|---|---|---|
| -20% | 2.0 | 1.28 | +176.60% | 137 |
| -10% | 2.25 | 1.44 | +268.91% | 130 |
| **0%** | **2.5** | **1.39** | **+209.36%** | **130** |
| +10% | 2.75 | 1.00 | +114.71% | 112 |
| +20% | 3.0 | 0.98 | +112.03% | 119 |

**Label: VALIDATED** (caída máxima dentro de ±10%: 28.1%, en +10%).

### riesgo_alto (`momentum_breakout`) — 4 parámetros

| Parámetro | -20% | -10% | **0% (producción)** | +10% | +20% | Label |
|---|---|---|---|---|---|---|
| `atr_stop_multiple` (1.75) | 0.78 | 0.64 | **0.91** | 0.92 | 0.84 | VALIDATED |
| `min_breakout_volume` (1.5) | 0.69 | 0.81 | **0.91** | 1.08 | 1.12 | VALIDATED |
| `min_relative_strength` (1.0) | 0.60 | 0.67 | **0.91** | 1.21 | 1.27 | VALIDATED |
| `max_atr_contraction` (1.0) | 0.75 | 0.96 | **0.91** | 1.09 | 1.21 | VALIDATED |

(Sharpe mostrado en cada celda; detalle completo con retorno/DD/trades
en `resultados_capa6.json`.) Caída máxima dentro de ±10% en cualquiera
de los 4: 29.7% (`atr_stop_multiple`, -10%) — ningún punto cruza el
50%.

Ningún bucket/parámetro salió INCONCLUSIVE — el punto con menos
operaciones dentro de la banda ±10% fue `max_atr_contraction` -10%
con 32 trades, por encima del piso de 10.

## Veredicto de esta capa (no de EXP-003 completo)

**Los 3 buckets: VALIDATED en todos los parámetros perturbados** —
ninguna perturbación dentro de ±10% (la banda que decide el label)
produce una caída de Sharpe mayor al 50%. No hay evidencia de "pico
aislado" (la firma clásica de sobreajuste: degradación fuerte en
AMBAS direcciones alrededor del valor actual).

## Hallazgo adicional (no cambia el label, pero es relevante)

En varios parámetros la superficie **no es una meseta simétrica**: el
valor de producción no está en un máximo local, sino en una pendiente
— mejora en una dirección y empeora en la otra:

- **largo_plazo**: `atr_stop_multiple` más ajustado (2.4, -20%) da
  Sharpe 1.37 vs. 0.78 de producción — casi el doble. La dirección
  "stop más ajustado" mejora consistentemente en este período.
- **riesgo_alto**: los 3 filtros de calidad (`min_breakout_volume`,
  `min_relative_strength`, `max_atr_contraction`) mejoran de forma
  consistente al volverse MÁS estrictos (+10%/+20%) — `min_relative_strength`
  +20% casi duplica el Sharpe de producción (1.27 vs. 0.91), con menos
  operaciones (31 vs. 44).
- **mediano_plazo** es el único de los 3 donde el valor de producción
  (2.5) está cerca de un máximo real: -10% (2.25) da el Sharpe más
  alto de la malla (1.44), pero -20% ya cae un poco (1.28) — la
  pendiente es más plana ahí que en los otros dos.

Esto no es evidencia de sobreajuste (no hay caída en ambas
direcciones), pero sí sugiere que, al menos en esta muestra, los
parámetros actuales de `largo_plazo` y `riesgo_alto` no están donde el
backtest histórico rendiría mejor — son válidos (pasan el criterio),
no necesariamente óptimos. Explorar esto a fondo (¿es una mejora real
o la misma clase de riesgo de sobreajuste que ADR 0040 ya encontró al
perseguir el mejor punto de una malla?) queda fuera del alcance de
esta capa — el pre-registro de EXP-003 no autoriza usar este hallazgo
para proponer un cambio de parámetro; solo lo documenta.
