# EXP-003 — Capa 1: Walk-forward rolling baseline

Código: `capa1_walkforward.py`. Reutiliza el harness de ADR 0040 sin
ningún filtro — las 3 estrategias de producción exactas (universos,
sizing por riesgo sobre equity actual, fricción real), 5 ventanas
rolling (12m train / 6m test, paso 4 meses), ancladas hacia atrás
desde el último dato disponible (2026-11-17). Esto cubre el tramo de
test de ~2025-01-17 a 2026-11-17 (~22 meses), no 36 — ver nota de
comparabilidad abajo.

## Resultado por bucket

| Bucket | Sharpe OOS prom. | Ventanas positivas | Ventana con menos trades | Label |
|---|---|---|---|---|
| largo_plazo | 0.44 | 3/5 | Ventana 2: 9 trades | **INCONCLUSIVE** (ventana con <10 operaciones) |
| mediano_plazo | 0.21 | 3/5 | — (mín. 18 trades) | **INCONCLUSIVE** (exactamente 3/5 positivas) |
| riesgo_alto | 0.39 | 4/5 | Ventana 4: 3 trades | **INCONCLUSIVE** (ventanas con <10 operaciones) |

Detalle completo por ventana en `resultados_capa1.json`.

### largo_plazo
Sharpe por ventana: 0.57, 1.48, 0.64, 0.07, -0.54. La ventana más
reciente (mayo-nov 2026) es la peor (-4.67% de retorno) — sin ser
suficiente para REJECTED (3/5 siguen positivas), es la estrategia más
débil de las 3 en el tramo reciente.

### mediano_plazo
Sharpe por ventana: -0.68, 1.18, 0.59, 1.14, -1.2. Alterna
fuerte/débil sin patrón claro — la ventana 5 (-10.08%) es la peor de
las 3 estrategias en ese mismo tramo final.

### riesgo_alto
Sharpe por ventana: 2.7, 1.13, -2.91, 0.92, 0.1. El más volátil con
diferencia: ventana 1 rindió +56.27% y la ventana 3 inmediatamente
después -24.65% — y con solo 3-10 operaciones por ventana, cualquier
Sharpe aquí es estadísticamente ruidoso por diseño (pocas muestras).
Esto confirma, desde un ángulo distinto, el hallazgo de ADR 0040 sobre
la concurrencia casi nula de riesgo_alto.

## Nota de comparabilidad con ADR 0015/0016

ADR 0015 (+31.07%/36m) y ADR 0016 (+34.00%/36m, cifra oficial vigente)
son el retorno acumulado de los 3 buckets YA COMBINADOS con sus pesos
de asignación, sobre backtests continuos de 36 meses — no son
comparables número a número con los Sharpe OOS por bucket de esta
capa (ventanas rolling de 6 meses, ~22 meses de cobertura total, cada
bucket aislado). No se puede ni se intenta forzar una reconciliación
exacta entre ambas cifras.

Lo que SÍ es una observación honesta y relevante: el headline de
+34% en 36 meses describe sobre todo el desempeño HISTÓRICO agregado;
el comportamiento OOS más reciente, bucket por bucket, es
consistentemente más débil y errático de lo que ese único número
sugiere — ninguno de los 3 buckets alcanza el umbral de VALIDATED en
esta capa, y los 3 muestran al menos una ventana reciente débil o
negativa. Esto no es evidencia de que la configuración esté rota
(REJECTED tampoco se alcanzó en ningún bucket), pero sí de que el
margen de confianza es más estrecho de lo que el número agregado de
36 meses comunica por sí solo.

## Veredicto de esta capa (no de EXP-003 completo)

**Los 3 buckets: INCONCLUSIVE.** Ninguno alcanza VALIDATED (por pocas
operaciones en al menos una ventana, o por quedar justo en 3/5
positivas) ni REJECTED (ninguno cae a ≤2/5 ventanas positivas). El
resultado más preocupante — no por el label en sí, sino por lo que
revela — es riesgo_alto: con tan pocas operaciones por ventana, el
bucket entero está, en la práctica, subdimensionado para que un
walk-forward de este tipo pueda confirmar o refutar nada con
confianza.

## CORRECCIÓN (2026-11-19): largo_plazo con el filtro cross-sectional real de ADR 0034

**El número de `largo_plazo` arriba (Sharpe OOS 0.76, INCONCLUSIVE)
corresponde a una configuración INCORRECTA.** El harness de ADR 0040
nunca implementó `CROSS_SECTIONAL_FILTER_BUCKETS`/
`CROSS_SECTIONAL_PERCENTIL_MIN` (ADR 0034) — el filtro cross-sectional
que SÍ está activo en producción hoy, solo para `largo_plazo`. Se
corrigió el harness (`harness.apply_cross_sectional_filter`, replica
fiel de `_percentiles_cross_sectional_hoy` + la condición de
`engine.py`) y se re-corrió esta capa. `mediano_plazo`/`riesgo_alto`
no usan este filtro — sus resultados arriba siguen vigentes tal cual.

**Autoverificación contra ADR 0034** (Sharpe OOS 2.25, +19.14%, DD
6.99%, 0/5 ventanas negativas, su propio walk-forward rolling): **no
reprodujo esa magnitud** — el reconstruido da Sharpe OOS 0.76, misma
categoría de discrepancia ya documentada arriba para el baseline sin
filtro (ventanas/esquema de capital distinto al de la exploración
original de ADR 0033/0034, causa exacta no identificada). Se reporta
honesto en vez de forzarse.

| Ventana | Período | Sharpe | Retorno | DD | Trades |
|---|---|---|---|---|---|
| 1 | 2025-01-17 → 2025-07-17 | 0.32 | +1.75% | 11.7% | 12 |
| 2 | 2025-05-17 → 2025-11-17 | 2.85 | +21.01% | 5.8% | 9 |
| 3 | 2025-09-17 → 2026-03-17 | 0.97 | +7.03% | 6.43% | 10 |
| 4 | 2026-01-17 → 2026-07-17 | 0.20 | +0.94% | 8.65% | 18 |
| 5 | 2026-05-17 → 2026-11-17 | -0.54 | -4.42% | 7.46% | 17 |

**Label corregido: INCONCLUSIVE** (igual categoría que antes — ventana
2 tiene solo 9 operaciones, por debajo del piso de 10 — pero ahora por
la configuración correcta). El panorama de fondo no cambia: con o sin
el filtro, 5 ventanas de 6 meses sobre ~26 ETFs siguen dando muestras
demasiado chicas (9-18 operaciones) para que este diseño de
walk-forward pueda confirmar o refutar nada con confianza en
`largo_plazo`.
