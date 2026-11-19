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
