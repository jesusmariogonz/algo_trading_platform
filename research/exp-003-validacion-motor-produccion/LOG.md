# LOG — EXP-003

Registro cronológico. Se agrega una entrada por sesión de trabajo,
incluyendo lo que no funcionó — mismo estándar que el LOG.md de
pulso-research-lab.

## 2026-11-18 — Pre-registro

Se escribió `PREREGISTRATION.md`: alcance (configuración de producción
exacta de los 3 buckets, ADR 0027), 7 capas con criterio
VALIDATED/REJECTED/INCONCLUSIVE fijado antes de correr nada, orden de
ejecución (Capa 1 y 7 primero por reutilizar infraestructura ya
existente; Capa 2 al final por incertidumbre de datos point-in-time).

Sin ejecutar todavía ninguna capa. Siguiente paso: Capa 1
(walk-forward rolling baseline, sin filtros) sobre las 3
estrategias/buckets de producción.

## 2026-11-18 — Capa 1 y Capa 7

**Bug encontrado y corregido antes de poder correr nada**: al mover
`exploracion_2026_11/` a `research/2026-11-filtros-sizing-adr0033/`
(ADR 0041), el `ROOT` de `harness.py` quedó apuntando un nivel arriba
de lo correcto (`parents[1]` en vez de `parents[2]`, porque el archivo
ahora vive un nivel más anidado) — corregido en el mismo commit de
esta entrada.

**Capa 1** (`capa1_walkforward.py`): walk-forward rolling SIN filtro
sobre las 3 estrategias de producción. Resultado: **los 3 buckets
INCONCLUSIVE** — largo_plazo y riesgo_alto por ventanas con <10
operaciones, mediano_plazo por quedar exactamente en 3/5 ventanas
positivas. Ver `CAPA-1-walk-forward.md` para el detalle y la nota de
comparabilidad con ADR 0015/0016 (métricas y ventanas de tiempo
distintas, no se fuerza una reconciliación numérica).

**Capa 7** (`capa7_ejecucion.py`): fill al open del día siguiente +
2x fricción, sobre todo el período disponible (2021-2026). Resultado:
**largo_plazo REJECTED** (Sharpe 0.78→-0.09, retorno +45.96%→-9.28%,
inspeccionado a mano, no es bug — sensibilidad real del stop-loss a
slippage de ejecución en una ventana de alta volatilidad real de abril
2025); **mediano_plazo y riesgo_alto VALIDATED** (ambos se degradan a
más de la mitad del Sharpe pero se mantienen netos positivos). Ver
`CAPA-7-ejecucion.md`.

Suite completa: 249/249 (sin cambios de producción). Pendiente:
Capa 6 (perturbación de parámetros), después Capa 4 (placebo).

## 2026-11-18 — Capa 6

**Capa 6** (`capa6_perturbacion.py`): perturbación ±10%/±20% de cada
parámetro continuo real de las 3 estrategias (`atr_stop_multiple` en
las 3; además `min_breakout_volume`/`min_relative_strength`/
`max_atr_contraction` en `momentum_breakout`/riesgo_alto —
`breakout_window` se excluyó por ser un switch discreto 20/55, no
continuo), backtest de período completo (sin ventanas, eso es Capa 1)
con el mismo motor de simulación del harness de ADR 0040.

Resultado: **los 3 buckets VALIDATED en todos los parámetros
perturbados** — ninguna caída de Sharpe dentro de ±10% (la banda que
decide el label, ±20% es solo contexto) supera el 50%. Sin evidencia
de pico aislado.

Hallazgo adicional documentado (no cambia el label): en varios
parámetros la superficie no es simétrica — `atr_stop_multiple` más
ajustado en largo_plazo casi duplica el Sharpe (1.37 vs. 0.78 de
producción en -20%), y los 3 filtros de calidad de riesgo_alto
mejoran de forma consistente al volverse más estrictos. El valor de
producción no está en un máximo local en 2 de los 3 buckets — válido,
no necesariamente óptimo. No se propone ningún cambio de parámetro:
fuera del alcance de esta capa. Ver `CAPA-6-perturbacion-parametros.md`.

Suite completa: 249/249 (sin cambios de producción). Pendiente: Capa 4
(placebo con potencia verificada).

## 2026-11-19 — Capa 4

**Capa 4** (`capa4_placebo.py` + `capa4_run_chunk.py` + `capa4_real_sharpe.py`):
moving block bootstrap conjunto (bloque de 21 sesiones, misma
secuencia de bloques para todo el universo + benchmark SPY en cada
réplica), reconstruyendo el panel OHLCV crudo desde cero y recalculando
indicadores/señales con las funciones REALES de producción
(`compute_indicators`, `compute_relative_strength`) en cada réplica —
no un reordenamiento superficial del resultado final.

**Bug encontrado y corregido antes de poder correr nada**: `ROKU`
tiene datos crudos corruptos (2 filas) y `WOLF` solo 287 filas —
intersectar el calendario común contra TODO el universo de riesgo_alto
sin excluirlos primero acotaba el calendario de los 43 símbolos buenos
a casi nada. Se agregó un filtro de historia mínima (500 filas) antes
de calcular la intersección.

**Validación de la reconstrucción**: corriendo el mismo pipeline con
la secuencia identidad (sin bootstrap) reproduce EXACTO el Sharpe de
Capa 1/6/7 (0.78/1.39/0.91) — el pipeline de reconstrucción es fiel.

**300 réplicas por bucket, no 1,000**: calibración empírica mostró
costo proporcional al tamaño del universo (2.75-8.0s/réplica según
bucket) — 1,000 réplicas de mediano_plazo (74 símbolos) habría tomado
>2h. Se corrieron los 3 buckets en paralelo (4 núcleos) en 6 rondas de
50, ~40 minutos totales — trade-off de tiempo documentado, no se forzó
el número objetivo a costa de la sesión.

**Potencia CONFIRMADA en los 3 buckets** (std del Sharpe placebo:
0.45-0.50, nada parecido al caso degenerado de EXP-002).

**Resultado — los 3 buckets REJECTED**: percentil del Sharpe real
dentro de la distribución placebo: largo_plazo 27.67 (por DEBAJO de la
mediana), mediano_plazo 49.33, riesgo_alto 55.33 (ambos prácticamente
EN la mediana). Ninguno cerca del umbral de 80. El orden histórico
real de los retornos no produjo, para ninguna de las 3 estrategias, un
resultado distinguible de un reordenamiento al azar de los mismos
bloques de ~1 mes. Ver `CAPA-4-placebo.md` para el detalle completo,
incluyendo qué significa esto y qué NO significa (es un diseño
específico de placebo, no una prueba definitiva cerrada).

Esta es la capa más severa de EXP-003 hasta ahora: a diferencia de
Capa 7 (solo largo_plazo se revertía), aquí los 3 buckets caen del
mismo lado.

Suite completa: 254/254 (sin cambios de producción). Pendiente: Capa 5
(leave-one-group-out), Capa 3 (DSR+PBO), Capa 2 (sesgo de
supervivencia).

## 2026-11-19 — Capa 5

**Capa 5** (`capa5_leave_one_group_out.py`): universo completo
construido una vez por bucket (`harness.signaled_universe`), agrupado
por clase de activo (largo_plazo) o sector GICS aproximado a mano
(mediano_plazo/riesgo_alto, documentado íntegro en el código —
`asset_types.py` es demasiado grueso para este propósito, casi todo
cae en "Stock"). Para cada grupo se re-corre `simulate_bucket` sobre
el universo menos ese grupo (sin recalcular señales — son por símbolo,
no dependen del resto del universo del bucket).

**Validación de la reconstrucción**: universo completo reproduce
Sharpe/retorno idéntico a Capas 1/6/7 (0.78/+45.96%, 1.39/+209.36%,
0.91/+165.28%).

**Resultado — los 3 buckets VALIDATED**: la caída máxima de Sharpe al
quitar cualquier grupo individual fue 1.3% (largo_plazo, Commodities),
30.2% (mediano_plazo, Utilities), 17.6% (riesgo_alto, Hardware_Semis)
— ninguna cruza el umbral de 40%, y varios grupos directamente MEJORAN
el Sharpe al quitarse (dilución, no dependencia concentrada). Ver
`CAPA-5-leave-one-group-out.md`.

Nota explícita en el reporte: esto no contradice el REJECTED de la
Capa 4 — responde una pregunta distinta ("¿depende de un sector
específico?" vs. "¿el orden temporal aporta algo sobre el azar?").
Un resultado puede estar bien distribuido entre sectores y seguir sin
ser distinguible de ruido en su conjunto.

Suite completa: sin cambios de producción (Capa 5 no modifica
`src/`). Pendiente: Capa 3 (DSR+PBO sobre el historial de los ADR),
Capa 2 (sesgo de supervivencia).

## 2026-11-19 — Capa 3

**⚠ Hallazgo crítico, previo al resultado de esta capa**: leyendo
`docs/adr/0001` a `0043` para catalogar el espacio de búsqueda, se
confirmó (código fuente actual de `src/paper_trading/engine.py`) que
`CROSS_SECTIONAL_FILTER_BUCKETS = {"largo_plazo"}` (ADR 0034) está
ACTIVO en producción hoy, y que el harness compartido de EXP-003
(`research/2026-11-filtros-sizing-adr0033/harness.py`) **nunca lo
incluyó** — genera la señal de `largo_plazo` con
`time_series_momentum` puro. Esto significa que el Sharpe 0.78 usado
como "baseline de producción" de `largo_plazo` en las Capas 1, 4, 5,
6 y 7 NO es la configuración real vigente — ADR 0034 reporta el
Sharpe real con el filtro: 2.25. No afecta a `mediano_plazo` ni
`riesgo_alto` (el filtro es exclusivo de `largo_plazo`). Documentado
íntegro en `CAPA-3-dsr-pbo.md`, sección inicial — no se corrigieron
las capas anteriores en este commit, queda como hallazgo abierto.

**Catálogo de variantes** (Paso 1, `capa3_dsr_pbo.py`): se leyeron los
43 ADR del repo, se catalogaron **47 configuraciones materialmente
distintas** con Sharpe/retorno medido contra un control (desde el
bucket de cripto descartado en ADR 0004/0006 hasta el swap
estrategia×universo de ADR 0040) — lista completa con ADR de origen
en el código y en `CAPA-3-dsr-pbo.md`.

**DSR** (Paso 2): `sigma_SR` = 0.7101, estimado de los 18 valores de
Sharpe realmente reportados en el catálogo (de los 47, solo 18 tienen
Sharpe explícito). Con N=47, el máximo esperado por puro azar es
SR₀≈1.60. Resultado: **mediano_plazo DSR=0.0001 (REJECTED),
riesgo_alto DSR=0.0000 (REJECTED)**; `largo_plazo` da **DSR=0.0000
(REJECTED) con el Sharpe del harness (0.78)** pero **DSR=1.0000
(VALIDATED) con el Sharpe real de producción (2.25, ADR 0034)** — la
ambigüedad del hallazgo de arriba se propaga directo al resultado.

**PBO** (Paso 3, `capa3_pbo.py`): CSCV sobre las 3 variantes
re-simulables de ADR 0040 (baseline/trend_efficiency/
correlation_adjusted, 5 ventanas, 20 particiones por bucket) — los 3
buckets dan PBO bajo (0.00/0.00/0.15), muy por debajo del umbral de
0.5. Nota explícita: esto solo cubre 3 de las 47 variantes del
catálogo, no contradice el DSR bajo sobre las 47 — son preguntas
distintas.

**Labels**: mediano_plazo REJECTED, riesgo_alto REJECTED,
largo_plazo AMBIGUO (REJECTED o VALIDATED según qué Sharpe se use —
sin resolver en esta capa). Consistente con Capa 4 (placebo, también
REJECTED en los 3 con el mismo Sharpe del harness).

Suite completa: 254/254 (sin cambios de producción — `capa3_dsr_pbo.py`
y `capa3_pbo.py` solo leen datos ya existentes y el harness, no tocan
`src/`). Pendiente: Capa 2 (sesgo de supervivencia) — última capa — y,
fuera del alcance de EXP-003 en sí, decidir si se extiende el harness
para incluir el filtro de ADR 0034 y se re-corren las Capas 1/4/6/7
para `largo_plazo` con la configuración real completa.
