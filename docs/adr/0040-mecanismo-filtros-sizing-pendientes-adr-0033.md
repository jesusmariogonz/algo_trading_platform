# ADR 0040 — Mecanismo detrás de los 2 filtros de sizing pendientes de ADR 0033

## Contexto

ADR 0033 dejó dos candidatos documentados pero nunca implementados ni
investigados a fondo: **#5 Trend efficiency ratio (Kaufman)** (ayuda
fuerte a `trend_following`/mediano_plazo, rompe `momentum_breakout`/
riesgo_alto) y **#2 Correlation-adjusted sizing** (ayuda a largo_plazo
y riesgo_alto, empeora mediano_plazo). El ADR documenta el resultado
numérico de cada hipótesis, nunca el mecanismo causal de por qué el
mismo tipo de filtro ("esta señal es de mayor calidad") ayuda en un
bucket y rompe otro — antes de tocar producción (motor paper o motor
en vivo IBKR), el usuario pidió entender ese mecanismo. **Esta
investigación es pura exploración, igual que ADR 0033 — nada se
implementa en producción aquí.**

### Limitación central: el código original no existe

`exploracion_2026_11/` es gitignored por diseño (ADR 0033 ya advertía
"el código en sí puede perderse si el contenedor de una sesión
termina") y, en efecto, ya no existe en este clon. Todo lo de abajo es
una **reconstrucción de buena fe del mecanismo descrito en prosa** en
ADR 0033, no una reproducción byte-a-byte — los parámetros exactos
(ventana del efficiency ratio, piso del multiplicador de correlación,
si había un tope de posiciones concurrentes, qué ventanas de
calendario exactas se usaron) no están documentados y no se pueden
recuperar.

**Auto-verificación (regla no negociable antes de confiar en algo
nuevo): el resultado NO pasó.** Con el harness reconstruido (walk-
forward rolling, 5 ventanas, 12m train/6m test, paso 4 meses, sizing
por riesgo sobre equity actual — mismo patrón que `engine.py`/ADR
0012, fricción 0.001 por lado — mismo valor que `FRICCION_POR_LADO`):

| Bucket | Sharpe baseline publicado (ADR 0033) | Sharpe baseline reconstruido |
|---|---|---|
| largo_plazo | 1.33 | 0.44 |
| mediano_plazo/trend_following | 0.96 | 0.21 |
| riesgo_alto/momentum_breakout | 1.49 | 0.39 |

Los 3 buckets salen entre 2.5x y 4.5x más bajos que lo publicado, de
forma consistente — no es ruido de un solo bucket. Se probaron dos
hipótesis alternativas antes de aceptar la discrepancia como no
resuelta: (1) que el Sharpe original se calculó sobre retornos
semanales/mensuales en vez de diarios (descartada: remuestrear la
curva de equity reconstruida a semana/mes no cambia el Sharpe de forma
material — las tres frecuencias dan resultados similares); (2) que el
código de las 3 estrategias cambió desde el 6-nov (no se puede
confirmar ni descartar: el clon es shallow, `git log` solo expone 3
commits, no hay historial para comparar — pero ADR 0033 dice
explícitamente "Ninguna cambia la señal de entrada/salida existente" y
nada en los ADR posteriores (0034 en adelante) toca
`src/strategies/*.py`, así que es poco probable). La causa más
plausible no descartable: el harness original probablemente usaba un
esquema de capital/concurrencia distinto (quizás backtest
independiente por símbolo con agregación distinta, o un tope de
posiciones concurrentes) que no se puede inferir solo de la prosa del
ADR.

**Consecuencia de este hallazgo:** los números absolutos de Sharpe de
este documento NO son comparables nivel-a-nivel con ADR 0033. Lo que
SÍ se puede evaluar con el mismo harness, aplicado de forma consistente
al baseline y a cada filtro, es el **patrón direccional** (¿el filtro
sube o baja el Sharpe en cada bucket?) — que es, de todos modos, la
pregunta real detrás de las 4 preguntas del usuario.

## Decisión — hallazgos (documentación de investigación, no implementación)

### Reproducción direccional: parcial, no limpia

| Filtro | Bucket | ADR 0033 dice | Reconstrucción dice |
|---|---|---|---|
| #5 Trend efficiency | largo_plazo | Ayuda (modesto) | Ayuda (0.44→1.37) ✓ |
| #5 Trend efficiency | mediano_plazo | Ayuda fuerte (0.96→1.75) | Ayuda fuerte (0.21→0.74) ✓ |
| #5 Trend efficiency | riesgo_alto | **Rompe** (1.49→0.42, 3/5 ventanas negativas) | **Ayuda** (0.39→1.02, 1/5 ventana negativa) ✗ |
| #2 Correlation-adj. | largo_plazo | Ayuda (1.33→2.00) | Ayuda (0.44→1.63) ✓ |
| #2 Correlation-adj. | mediano_plazo | **Empeora** | Ayuda modesto (0.21→0.43) ✗ |
| #2 Correlation-adj. | riesgo_alto | Ayuda | Ayuda modesto (0.39→0.53) ✓ |

4 de 6 relaciones de signo coinciden; las 2 que no coinciden son
justo las dos "rupturas" que motivaron la pregunta del usuario — la
reconstrucción **no logra romper riesgo_alto con trend efficiency
ratio, ni empeorar mediano_plazo con correlation-adjusted sizing**.
Esto se reporta así, sin forzarlo: no se puede confirmar el mecanismo
exacto de esas dos rupturas con este harness. Puede ser (a) una
diferencia real de implementación no recuperable, o (b) que esas dos
rupturas específicas en ADR 0033 eran en sí mismas sensibles a
detalles de implementación — lo cual sería evidencia a favor de la
preocupación del usuario en la pregunta 4 (sobre overfitting).

### Pregunta 1 — Trend efficiency ratio: ¿estrategia, universo, o ambos?

Prueba de aislamiento (intercambiando estrategia y universo en un
diseño 2×2, siempre con el mismo harness):

| Combinación | Sharpe baseline | Sharpe +trend efficiency | Ventanas negativas |
|---|---|---|---|
| `trend_following` × universo mediano (nativo) | 0.21 | 0.74 | 2/5 |
| `momentum_breakout` × universo riesgo_alto (nativo) | 0.39 | 1.02 | 1/5 |
| `trend_following` × universo **riesgo_alto** (swap) | 0.32 | **0.11** | 2/5 |
| `momentum_breakout` × universo **mediano** (swap) | 1.15 | 1.62 | 1/5 |

En esta reconstrucción, el filtro solo empeora el Sharpe en **una** de
las 4 combinaciones: `trend_following` corriendo sobre el universo de
riesgo_alto — ni la estrategia `momentum_breakout` por sí sola (le va
bien en ambos universos) ni el universo riesgo_alto por sí solo (le va
bien con `momentum_breakout`) explican una ruptura; es una
**interacción específica** entre una estrategia de tendencia pura y un
universo de alta volatilidad, no un efecto principal de ninguno de los
dos factores aislado. Dicho esto, esta es la ruptura *correcta en el
sentido de que SÍ aparece una combinación que rompe*, pero es la
combinación cruzada (`trend_following`×riesgo_alto), no la nativa
(`momentum_breakout`×riesgo_alto) que reporta ADR 0033 — así que esta
evidencia debe tratarse como generadora de hipótesis, no confirmatoria.

### Pregunta 2 — Correlation-adjusted sizing: ¿concurrencia o correlación interna?

Evidencia directa, independiente de cualquier simulación (solo
estadística de precios y de los trades del baseline):

| Bucket | Correlación promedio intra-universo (36m, diaria) | Posiciones concurrentes (prom. / máx.) |
|---|---|---|
| largo_plazo | **0.406** (la más alta) | 2.14 / 5 |
| riesgo_alto | 0.278 | **0.59 / 2** (la más baja, con mucho) |
| mediano_plazo | 0.213 (la más baja) | **2.78 / 5** (la más alta) |

Esto da una explicación mecánica coherente, aunque no 100% confirmada
por la simulación (ver tensión abajo): el filtro necesita **ambas**
condiciones para funcionar como se espera — correlación real que
penalizar, y suficientes posiciones concurrentes para que la
penalización se aplique con frecuencia:

- **largo_plazo**: correlación alta + concurrencia moderada → el
  filtro encuentra redundancia real y la penaliza seguido. Caso más
  limpio de los tres, y el único donde la reconstrucción coincide en
  signo con ADR 0033.
- **mediano_plazo**: concurrencia alta pero correlación baja → el
  filtro se dispara seguido pero penaliza posiciones que en realidad
  SÍ diversifican — debería restar más que sumar. La reconstrucción
  muestra una mejora modesta en vez del empeoramiento esperado por este
  mecanismo: **tensión no resuelta** entre la teoría (basada en datos
  de precio reales, no en la simulación) y el resultado de la
  simulación — posiblemente el piso de 0.1 elegido para el
  multiplicador, o el detalle exacto de cuándo se evalúa la
  correlación, amortigua el efecto esperado más de lo que debería.
- **riesgo_alto**: concurrencia casi nula (menos de 1 posición abierta
  en promedio, máximo 2) → el filtro **casi nunca tiene una posición
  abierta contra la cual comparar** (su condición de "sin posiciones
  abiertas → sin penalización" se cumple casi siempre). Cualquier
  mejora de Sharpe atribuida a este filtro en riesgo_alto es, por
  construcción, producto de un puñado de instancias aisladas, no de un
  mecanismo sistemático — esto es evidencia **directa** a favor de la
  preocupación de la pregunta 4 para este bucket específico.

### Pregunta 3 — Evidencia de momentum crash en riesgo_alto

Evidencia fuerte y directa (estadística de retornos futuros a 20 días
condicional al percentil cross-sectional de momentum de 126 días,
sobre los 3 universos reales, sin depender de ninguna simulación de
filtro):

| Universo | Desv. std. retorno fwd 20d (top 20% momentum) | P(retorno fwd 20d ≤ -15% \| top momentum) | Retorno medio fwd 20d: top vs. bottom momentum |
|---|---|---|---|
| largo_plazo | 6.50% | 1.13% | 0.66% vs. 1.06% |
| mediano_plazo | 9.75% | 2.81% | 1.57% vs. 1.69% |
| **riesgo_alto** | **22.97%** (3.5x largo_plazo) | **18.36%** (16x largo_plazo, 6.5x mediano_plazo) | 2.52% vs. 3.26% (**negativo**: los de MÁS momentum rinden peor en promedio) |

Esto es la firma clásica de momentum crash (Daniel & Moskowitz):
riesgo_alto no solo tiene colas mucho más gordas tras rachas fuertes de
momentum, sino que ahí perseguir momentum ni siquiera paga en
promedio — el retorno esperado hacia adelante es más bajo para el
grupo de mayor momentum que para el de menor. Esto es consistente con
(y ayuda a explicar) por qué **cualquier** filtro que amplifique la
exposición a nombres de momentum fuerte en ese universo específico
corre un riesgo estructural que los otros dos universos no tienen —
independientemente de si esta reconstrucción logró o no replicar la
ruptura exacta de #5.

### Pregunta 4 — ¿Riesgo de correlación espuria tipo hipótesis #9?

- **Trend efficiency ratio**: la prueba de aislamiento (pregunta 1)
  muestra que el efecto es una interacción específica
  estrategia×universo, no un efecto principal robusto de ninguno de
  los dos — eso ya es una señal de fragilidad. Además, la
  descomposición por símbolo (ver abajo) muestra que el filtro
  **diversifica** la operación (más símbolos operados, menor
  concentración) en los 3 buckets, de forma consistente — no hay un
  puñado de símbolos atípicos manejando el resultado agregado, lo cual
  es evidencia moderadamente tranquilizadora sobre ESE aspecto
  específico, pero no resuelve la fragilidad de la interacción.
- **Correlation-adjusted sizing en riesgo_alto específicamente**: la
  pregunta 2 ya da evidencia directa de que el mecanismo casi no tiene
  oportunidad de operar ahí (concurrencia casi nula) — cualquier
  mejora medida en ADR 0033 para ese bucket es más consistente con un
  artefacto de pocas observaciones que con una mejora generalizable.
  **Este es el hallazgo de mayor riesgo de correlación espuria de los
  dos candidatos.**
- **Correlation-adjusted sizing en mediano_plazo**: la tensión entre
  la teoría basada en datos de precio reales (debería empeorar, baja
  correlación + alta concurrencia) y el resultado observado en la
  reconstrucción (mejora modesta) es, en sí misma, una señal de que el
  resultado no es robusto a los detalles exactos de implementación —
  ni el de ADR 0033 ni el de esta reconstrucción deberían tratarse
  como la última palabra.

### Descomposición por símbolo (¿lo maneja un puñado de atípicos?)

| Bucket / variante | Símbolos con trades | % del \|PnL\| total en el top 3 |
|---|---|---|
| largo_plazo baseline | 10 | 59.0% |
| largo_plazo +trend efficiency | 26 | 34.8% |
| largo_plazo +correlation-adj. | 23 | 34.9% |
| mediano_plazo baseline | 41 | 36.9% |
| mediano_plazo +trend efficiency | 70 | 24.5% |
| riesgo_alto baseline | 19 | 46.9% |
| riesgo_alto +trend efficiency | 34 | 37.0% |

En la reconstrucción, ambos filtros **reducen** la concentración en
pocos símbolos (sube el número de símbolos operados, baja el % del
top 3) en los 3 buckets — el baseline en sí ya está notablemente
concentrado (hasta 59% del PnL en solo 3 de 26 símbolos en
largo_plazo). Esto es consistente con el mecanismo declarado (un
multiplicador continuo, no un filtro binario, reparte capital hacia
más candidatos marginales en vez de concentrarlo en los más fuertes) y
no apunta a que el resultado agregado de ningún filtro dependa de 1-2
símbolos atípicos — aunque, dado que esta reconstrucción no pasó la
auto-verificación, esta conclusión aplica a ESTA reconstrucción, no
necesariamente al código original de ADR 0033.

## Recomendación final

**No implementar ninguno de los dos candidatos en producción (motor
paper ni motor en vivo IBKR) con el nivel de evidencia actual.**

Razón: esta investigación no logró confirmar, con un harness
reconstruido de buena fe, ni la magnitud absoluta de los baselines de
ADR 0033 ni el signo de 2 de las 6 relaciones bucket×filtro
documentadas ahí — incluyendo las DOS rupturas que originalmente
motivaron la pregunta del usuario. Hay evidencia independiente sólida
(estructura de correlación, concurrencia de posiciones, estadística de
momentum crash) que SÍ sostiene una historia mecánica coherente para
por qué estos filtros deberían comportarse de forma distinta entre
buckets — pero esa misma evidencia predice correctamente la dirección
en unos casos (correlation-adjusted en largo_plazo, riesgo_alto) y no
en otro (correlation-adjusted en mediano_plazo, donde la teoría dice
"debería empeorar" y la simulación dice "mejora modesto"). Mezclar
evidencia robusta con resultados de simulación que no auto-verifican
sería forzar una conclusión, lo que el usuario explícitamente pidió
evitar.

**Recomendación de proceso (más importante que la decisión de
implementar o no):** el verdadero hallazgo de esta investigación es
que el código de ADR 0033 era **irreproducible por diseño** — se
decidió explícitamente que podía perderse, y se perdió. El costo real
de esa decisión es que hoy no se puede distinguir con confianza entre
"el mecanismo es real pero esta reconstrucción tiene un detalle
distinto" y "el hallazgo original era frágil/un artefacto". Antes de
confiar en cualquier candidato de ADR 0033 — o en cualquier
investigación exploratoria futura de este tipo — se recomienda que el
código de este tipo de investigación, aunque nunca se use en
producción, se mantenga en una ubicación versionada (ej. una carpeta
`research/` NO gitignored, o un repo/rama separado) en vez de
gitignored — el ahorro de no commitear código exploratorio no vale el
costo de no poder volver a verificar una decisión de miles de dólares
reales. Esto queda como recomendación, no como cambio — decisión del
usuario.

**Si en el futuro se quiere seguir explorando estos 2 candidatos**, la
vía más segura (consistente con cómo se dio de baja mean_reversion_rsi2
en ADR 0027) es un **período de prueba en paralelo, sin tocar el motor
real**: una 5ª canasta puramente informativa (igual patrón que
`benchmark_diversificado` de ADR 0039) que corra el filtro candidato
sobre papel, comparado día a día contra el bucket real equivalente,
antes de considerar sizing a la mitad o cualquier cambio en
`engine.py`/`live_engine.py`.

## Consecuencias

- Cero cambios de producción: no se tocó `engine.py`, `live_engine.py`
  ni `daily_signals.py`.
- El harness y los filtros reconstruidos viven en `exploracion_2026_11/`
  (gitignored, no se commitea — mismo patrón que ADR 0033). Este
  documento es el registro persistente.
- Se descargó más historia de precios (`--years 5`) para los universos
  de `universe.txt`, `universe_riesgo_alto.txt` y
  `universe_largo_plazo.txt`, y se corrieron `src.indicators.compute` y
  `src.indicators.relative_strength` sobre todo el universo — datos en
  `data/raw/`/`data/processed/` (gitignored), sin efecto en producción.
- Suite completa: 233/233 tests pasan (sin cambios, no se tocó código
  de producción).
- Pregunta pendiente para el usuario: si quiere adoptar la
  recomendación de proceso (dejar de gitignorar el código de
  investigación exploratoria tipo ADR 0033/0040) para que esta
  situación de irreproducibilidad no se repita.
