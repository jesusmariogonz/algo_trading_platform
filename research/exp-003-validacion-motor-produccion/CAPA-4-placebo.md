# EXP-003 — Capa 4: Placebo con potencia verificada

Código: `capa4_placebo.py` (pipeline de reconstrucción + réplica) y
`capa4_run_chunk.py` (ejecución en bloques, acumula resultados en
`placebo_<bucket>.json`). `capa4_real_sharpe.py` calcula el Sharpe
real bajo el MISMO pipeline de reconstrucción, para comparar manzanas
con manzanas.

## Método

Lección de EXP-002 (pulso-research-lab): un placebo de rotación
circular sobre una estadística invariante al orden (CAGR vía producto)
tuvo potencia estadística CERO. Las 3 estrategias de producción SÍ
dependen del orden temporal (trailing stop, entradas/salidas
secuenciales) — pero había que confirmarlo, no asumirlo.

**Moving block bootstrap conjunto**, tamaño de bloque 21 sesiones
(~1 mes de trading — preserva autocorrelación de corto plazo, destruye
deliberadamente la persistencia de tendencia de varios meses que
`time_series_momentum`/`trend_following` están diseñadas a explotar).
La MISMA secuencia de bloques reordenados se aplica a TODOS los
símbolos del universo de un bucket y al benchmark SPY en una réplica
dada (no independiente por símbolo) — preserva la estructura
cross-seccional dentro de cada bloque, necesaria para que
`relative_strength_63` de `momentum_breakout` siga siendo coherente.

Desde los retornos crudos (`data/raw/<symbol>.parquet`, antes de
cualquier indicador) se reconstruye un panel OHLCV sintético completo
por símbolo (close/high/low vía su razón histórica contra el close del
día anterior; volumen pasa junto con el bloque, sin inventarse), se
recalculan TODOS los indicadores desde cero con las funciones REALES
de producción (`compute_indicators`, `compute_relative_strength` —
nunca reimplementadas) y se corre la estrategia de producción
(`generate_signals`) + el motor de simulación (`simulate_bucket`,
reusado de `research/2026-11-filtros-sizing-adr0033/harness.py`) sobre
ese universo sintético — recreando una réplica placebo completa de
punta a punta, no solo reordenando el resultado final.

**Validación de la reconstrucción**: corriendo este MISMO pipeline con
la secuencia identidad (orden histórico real, cero bootstrap) se
obtiene Sharpe 0.78/1.39/0.91 para largo_plazo/mediano_plazo/
riesgo_alto — IDÉNTICO a los números ya reportados en Capa 1/6/7. El
pipeline de reconstrucción es fiel, no una aproximación con sesgo
propio.

**Exclusión de datos documentada**: `ROKU` (solo 2 filas de datos
crudos, descarga corrupta/incompleta) y `WOLF` (287 filas, agregado
reciente al universo) se excluyeron del universo de `riesgo_alto`
antes de calcular el calendario común — dejarlos adentro acotaba la
intersección de fechas de TODO el bucket a casi nada. 43/44 símbolos
de ese universo quedan usables; 26/26 en largo_plazo, 74/79 en
mediano_plazo (5 sin archivo crudo descargado).

## Réplicas corridas: 300 por bucket, no 1,000 — justificación

Calibración empírica (5 réplicas reales por bucket antes de comprometer
tiempo): 2.75-2.95s/réplica (largo_plazo, 26 símbolos), 7.4-8.0s/réplica
(mediano_plazo, 74 símbolos), 4.0-4.2s/réplica (riesgo_alto, 43
símbolos) — el costo escala con el tamaño del universo, no es
constante. 1,000 réplicas de mediano_plazo solo habrían tomado >2
horas. Se corrieron los 3 buckets EN PARALELO (4 núcleos disponibles)
en 6 rondas de 50 réplicas, ~6.5 minutos por ronda (acotado por
mediano_plazo) — 300 réplicas por bucket en ~40 minutos totales, un
trade-off deliberado de tiempo/precisión documentado aquí en vez de
forzar 1,000 a costa de la sesión completa. 300 réplicas siguen dando
resolución de percentil de ~0.33%, suficiente para distinguir con
margen cualquiera de las bandas del criterio (80/95).

## Chequeo de potencia (ANTES de mirar el percentil)

| Bucket | Sharpe placebo: media (std) | Rango (min-max) |
|---|---|---|
| largo_plazo | 1.006 (0.469) | -0.33 a 2.25 |
| mediano_plazo | 1.392 (0.455) | -0.06 a 2.60 |
| riesgo_alto | 0.795 (0.497) | -0.69 a 2.12 |

**Potencia CONFIRMADA en los 3 buckets** — a diferencia del caso
degenerado de EXP-002 (varianza ~1e-16, solo ruido de punto flotante),
aquí la desviación estándar entre réplicas es ~0.45-0.50, del mismo
orden de magnitud que el propio Sharpe real. El bootstrap de bloques
sí produce una distribución con variación genuina, consistente con que
estas 3 estrategias dependen de verdad del orden temporal de las
señales (a diferencia de la estadística invariante al orden de
EXP-002). Se procede a interpretar el percentil.

## Resultado — percentil del Sharpe real dentro de la distribución placebo

| Bucket | Sharpe real (mismo pipeline) | Percentil dentro del placebo | Label |
|---|---|---|---|
| largo_plazo | 0.78 | **27.67** | **REJECTED** |
| mediano_plazo | 1.39 | **49.33** | **REJECTED** |
| riesgo_alto | 0.91 | **55.33** | **REJECTED** |

Percentil = % de las 300 réplicas placebo con Sharpe MENOR al real.
Criterio pre-registrado: REJECTED si percentil <80 con potencia
confirmada — los 3 buckets caen muy por debajo de ese umbral. El
Sharpe real de `largo_plazo` queda incluso por debajo de la MEDIANA
del placebo (percentil 50); `mediano_plazo` y `riesgo_alto` quedan
prácticamente EN la mediana (49.33 y 55.33).

## Qué significa esto (y qué NO significa)

Esta prueba responde una pregunta específica: *si el mismo tipo de
movimientos diarios reales (mismos bloques de ~1 mes, mismas
magnitudes y mismo signo) hubiera ocurrido en un ORDEN distinto al que
realmente ocurrió, ¿la estrategia de producción habría rendido peor?*
Para los 3 buckets, la respuesta es que el orden histórico real NO
produjo un resultado distinguible de un reordenamiento al azar de esos
mismos bloques — el Sharpe real cae donde cualquier reordenamiento
típico también caería, no en la cola alta.

Esto es consistente con (no prueba por sí solo, pero apunta en la
misma dirección que) los hallazgos de las Capas 1 y 6: Capa 1 ya marcó
los 3 buckets como INCONCLUSIVE por pocas operaciones por ventana;
Capa 6 encontró que el valor de parámetro actual de `largo_plazo` y
`riesgo_alto` no está en un máximo local de la malla (está en una
pendiente). La Capa 4 agrega ahora una pieza más fuerte: ni siquiera
el ORDEN TEMPORAL REAL de los retornos parece aportar algo que un
reordenamiento al azar de los mismos bloques no replique.

**Lo que esto NO dice**: no dice que los retornos reales de estos
símbolos fueran aleatorios (el bootstrap usa retornos reales, no
simulados) — dice que, DADO el conjunto real de movimientos de
~1 mes de estos símbolos, el orden específico en que realmente
ocurrieron no fue mejor que un orden alternativo para las reglas
exactas de estas 3 estrategias. Tampoco es la última palabra: es UN
diseño específico de placebo (bloques de 21 días, bootstrap conjunto)
— un tamaño de bloque distinto, o una forma distinta de romper el
orden, podría dar un resultado diferente; esto se documenta como
limitación, no se presenta como una prueba definitiva cerrada.

## Veredicto de esta capa (no de EXP-003 completo)

**Los 3 buckets: REJECTED.** Potencia confirmada en los 3, percentil
del Sharpe real muy por debajo del umbral de 80 en los 3 — en
`mediano_plazo` y `riesgo_alto` prácticamente en la mediana del
placebo, en `largo_plazo` por debajo de ella. Esta es la capa más
severa de EXP-003 hasta ahora — a diferencia de Capa 7 (donde solo
`largo_plazo` se revertía), aquí los 3 buckets caen del mismo lado de
la línea.

## CORRECCIÓN (2026-11-19): largo_plazo con el filtro cross-sectional real de ADR 0034

**El resultado de `largo_plazo` arriba (Sharpe real 0.78, percentil
27.67) corresponde a una configuración INCORRECTA** — mismo bug que en
las demás capas (ver corrección en CAPA-1-walk-forward.md).
`mediano_plazo`/`riesgo_alto` no usan el filtro cross-sectional, sus
resultados arriba siguen vigentes.

Se re-corrieron 300 réplicas nuevas (mismo diseño: bloques de 21 días,
bootstrap conjunto, con el filtro cross-sectional aplicado a CADA
réplica antes de simular). **Bug encontrado y corregido durante esta
misma corrección** (documentado con transparencia, mismo estándar que
el resto del proyecto): el primer cálculo del percentil usó
`np.mean([1 for s in sharpes if s < real])`, que siempre da 1.0 (es
la media de una lista que solo contiene unos, nunca divide por el
total de réplicas) — dio un percentil falso de 100.0 (VALIDATED). Se
corrigió a `count(s < real) / total * 100` y se re-corrió la capa
completa para no dejar un número sabidamente mal en el registro.

| Bucket | Sharpe real (con filtro) | Media placebo (std) | Percentil corregido | Label |
|---|---|---|---|---|
| largo_plazo | 0.92 | 0.921 (0.476) | **48.33** | **REJECTED** |

**Label corregido: REJECTED — sin cambio respecto al resultado
original.** Potencia confirmada (std 0.476, mismo orden que antes).
El Sharpe real con el filtro (0.92) queda prácticamente EN la media
de la distribución placebo (0.921) — percentil 48.33, consistente con
`mediano_plazo` (49.33) y `riesgo_alto` (55.33). El filtro
cross-sectional mejora el Sharpe absoluto de `largo_plazo` (0.78→0.92)
pero no cambia la conclusión de esta capa: el orden temporal real de
los retornos tampoco aporta, con el filtro activo, algo que un
reordenamiento al azar de los mismos bloques mensuales no replique.
**Los 3 buckets siguen REJECTED en esta capa, ahora con la
configuración correcta de los 3.**
