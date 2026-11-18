# EXP-003 — Validación estadística y robustez del motor de trading

**Estado:** PRE-REGISTRADO, sin ejecutar. Este documento se escribe y
se commitea ANTES de correr cualquier capa — igual que la disciplina
de `PREREGISTRATION.md` en pulso-research-lab. Una vez commiteado, un
cambio a los criterios de abajo (umbrales, método, qué cuenta como
VALIDATED/REJECTED/INCONCLUSIVE) requiere un commit nuevo que lo diga
explícitamente, nunca una edición silenciosa después de ver resultados.

## Por qué existe

El usuario teme que la configuración con la que opera el motor en vivo
de IBKR (3 buckets: `largo_plazo`/`time_series_momentum`,
`mediano_plazo`/`trend_following`, `riesgo_alto`/`momentum_breakout` —
ADR 0027) sea mala, y pidió el protocolo completo, sin apuro de
calendario, para averiguarlo con honestidad en vez de buscar
confirmación. Motor paper y motor en vivo comparten la misma lógica de
señales (`engine.py`/`live_engine.py`), así que todo lo de abajo se
corre contra el motor simulado/backtest — la conclusión aplica a
ambos.

**Esto es investigación: cero cambios a producción en ningún momento
de EXP-003.** Si algún resultado sugiere un cambio (ej. un parámetro
distinto, descartar un bucket), eso es una decisión posterior del
usuario, nunca una consecuencia automática de este experimento.

## Convención de código

Todo el código de EXP-003 vive en este mismo directorio
(`research/exp-003-validacion-motor-produccion/`), versionado desde el
día 1 — nunca gitignored (ver ADR 0041: la razón de ese cambio de
convención fue precisamente para que esto no se pierda). `LOG.md` en
este mismo directorio registra avances capa por capa, en orden
cronológico, incluyendo lo que no funcionó.

## Lecciones ya incorporadas de experimentos anteriores

- **EXP-002**: un placebo mal especificado puede tener potencia
  estadística cero sin que sea obvio de entrada (rotar una estadística
  invariante al orden). La Capa 4 de abajo se diseña explícitamente
  para tener potencia real — ver esa sección.
- **ADR 0040**: código de investigación sin versionar es
  irreproducible. Ya resuelto por convención (ADR 0041), pero se
  reafirma aquí explícitamente para EXP-003 dado su tamaño y duración.
- **Roadmap Fase 0 / README**: sesgo de supervivencia ya detectado y
  nunca resuelto en los universos actuales (elegidos a mano, incluyen
  ganadores conocidos del rally de IA 2023-2025). La Capa 2 de abajo
  es el intento formal de cuantificarlo, no solo de advertirlo otra
  vez.

## Alcance — qué se valida

La configuración de producción EXACTA de hoy (no una variante, no una
mejora propuesta): las 3 estrategias, sus universos actuales
(`config/universe_largo_plazo.txt`, `config/universe.txt`,
`config/universe_riesgo_alto.txt`), sizing por riesgo sobre equity
actual (ADR 0012), fricción real (0.05%+0.05% por lado), blend
SPY/GLD para cash ocioso (ADR 0014/0028). Se excluye explícitamente:
`benchmark_diversificado` (ADR 0039, es el punto de comparación, no lo
que se valida) y los 2 candidatos pendientes de ADR 0033/0040
(cualquier decisión sobre ellos espera el resultado de EXP-003, no al
revés).

## Las 7 capas

Cada capa tiene: pregunta, método, y el criterio de
VALIDATED/REJECTED/INCONCLUSIVE **fijado ahora, antes de correrla**.
Una capa puede salir INCONCLUSIVE por datos insuficientes — eso es un
resultado válido, no un fallo del experimento.

### Capa 1 — Walk-forward rolling (robustez temporal)

**Pregunta:** ¿el rendimiento de cada estrategia es consistente a
través de distintos períodos, o depende de que un puñado de
operaciones caigan en la ventana correcta?

**Método:** reutiliza y extiende el harness ya construido para ADR
0040 (`research/2026-11-filtros-sizing-adr0033/harness.py` — rolling,
train 12m/test 6m, paso 4 meses), aplicado SIN ningún filtro (baseline
de producción tal cual) a las 3 estrategias/buckets, con la máxima
historia de precios disponible (no solo 36 meses si hay más).

**Criterio:**
- VALIDATED: ≥4/5 ventanas con Sharpe OOS > 0 Y ninguna ventana
  individual aporta >60% del retorno compuesto total (para descartar
  que todo dependa de una sola racha).
- INCONCLUSIVE: exactamente 3/5 ventanas positivas, o alguna ventana
  con <10 operaciones (ruido estadístico, no señal).
- REJECTED: ≤2/5 ventanas con Sharpe OOS > 0.

### Capa 2 — Cuantificación de sesgo de supervivencia

**Pregunta:** ¿cuánto del rendimiento reportado depende de que el
universo esté elegido a mano, hoy, con el diario de lo que ya ganó?

**Método:** comparar el universo actual contra un universo de
referencia más neutral y amplio reconstruible con datos point-in-time
razonables (ej. constituyentes históricos de S&P 500/S&P 600 hace 3
años vía un proveedor punto-en-el-tiempo, si se consigue a costo/tiempo
razonable — si no es viable con los datos disponibles, se documenta
explícitamente como limitación, no se fabrica un proxy). Se corre la
MISMA estrategia sobre ambos universos y se compara.

**Criterio:**
- VALIDATED (sesgo bajo): diferencia de retorno anualizado entre
  universo curado y universo neutral ≤30% relativo.
- INCONCLUSIVE: no se consigue un universo neutral reconstruible con
  esfuerzo razonable — se documenta como limitación abierta, no se
  fuerza una comparación con datos de dudosa calidad.
- REJECTED (sesgo material): diferencia >30% relativo — el número de
  producción debe tratarse como cota superior, no estimador puntual,
  en cualquier comunicación futura.

### Capa 3 — DSR + PBO sobre todo el espacio de búsqueda histórico

**Pregunta:** dado que este proyecto ya probó informalmente decenas de
variantes a través de ~40 ADRs (universos, parámetros de riesgo,
blends, 10 hipótesis de ADR 0033, etc.), ¿qué tan probable es que el
resultado actual sea el mejor de muchos intentos por azar, no
habilidad real?

**Método:** Deflated Sharpe Ratio (Bailey & López de Prado, misma
derivación ya hecha a mano en el appendix de EXP-002) usando como N el
número de configuraciones materialmente distintas documentadas en
`docs/adr/` que modificaron una estrategia/universo/parámetro de
sizing (se cuenta explícitamente al correr esta capa, con la lista
completa en el resultado — no se estima a ojo). Combinatorially
Symmetric Cross-Validation (PBO) sobre el conjunto de variantes que sí
se pueden re-simular con datos disponibles.

**Criterio:**
- VALIDATED: DSR > 0.95 Y PBO < 0.5 (más probable que sea habilidad
  real que artefacto de buscar entre alternativas).
- INCONCLUSIVE: DSR entre 0.5 y 0.95, o PBO no calculable por falta de
  variantes re-simulables suficientes.
- REJECTED: DSR ≤ 0.5.

### Capa 4 — Placebo bien especificado (con potencia real)

**Pregunta:** a diferencia de EXP-002 (CAGR vía producto, invariante
al orden — potencia cero), estas 3 estrategias SÍ dependen del orden
temporal de las señales (momentum/tendencia con entrada/salida
secuencial) — así que un placebo de reordenamiento aquí sí puede tener
potencia real. Hay que confirmarlo, no asumirlo.

**Método:** block-bootstrap de los RETORNOS DIARIOS de cada símbolo
(no de la señal ya generada) preservando autocorrelación de corto
plazo, re-generando las señales de la estrategia sobre cada réplica
bootstrapeada — 1,000+ réplicas. Antes de interpretar el percentil,
verificar potencia: confirmar que el placebo SÍ produce una
distribución con varianza no-trivial (a diferencia del caso
degenerado de EXP-002) — si la varianza entre réplicas placebo es
despreciable, declarar la prueba sin potencia ANTES de mirar el
percentil, no después.

**Criterio:**
- VALIDATED: el Sharpe real cae en el percentil ≥95 de la
  distribución placebo, Y la prueba tiene potencia confirmada
  (varianza no-trivial entre réplicas).
- INCONCLUSIVE: prueba sin potencia confirmada (como EXP-002), o
  percentil entre 80-95.
- REJECTED: percentil <80 con potencia confirmada.

### Capa 5 — Cross-sectional leave-one-group-out

**Pregunta:** ¿el resultado de cada bucket sobrevive si se le quita
cualquier grupo de símbolos correlacionados (ej. un sector), o
depende de que ese grupo específico esté adentro?

**Método:** agrupar cada universo por sector/clase de activo (datos ya
disponibles vía `src/portfolio/asset_types.py`), re-correr el backtest
completo quitando cada grupo uno a la vez (leave-one-group-out), medir
el Sharpe resultante sin ese grupo.

**Criterio:**
- VALIDATED: el Sharpe sin NINGÚN grupo individual cae más del 40%
  respecto al Sharpe con el universo completo.
- INCONCLUSIVE: algún universo queda con <3 grupos distinguibles
  (leave-one-group-out no es informativo con tan pocos grupos).
- REJECTED: quitar algún grupo individual hace caer el Sharpe >40% o
  lo vuelve negativo — el resultado depende de ese grupo específico,
  no es generalizable al universo como clase.

### Capa 6 — Superficie de perturbación de parámetros

**Pregunta:** ¿el rendimiento es una meseta estable alrededor de los
parámetros actuales (SMA 200, ventana ATR, lookback de momentum), o un
pico aislado — la firma clásica de sobreajuste a un valor exacto?

**Método:** perturbar cada parámetro clave de cada estrategia ±10% y
±20% (grid simple, no optimización), medir el Sharpe resultante en
cada punto, graficar la superficie.

**Criterio:**
- VALIDATED: el Sharpe en cualquier punto dentro de ±15% de cualquier
  parámetro no cae más del 50% respecto al valor actual.
- INCONCLUSIVE: la superficie es demasiado ruidosa (pocas operaciones
  en algún punto de la malla) para distinguir meseta de pico.
- REJECTED: alguna perturbación ≤15% produce una caída >50% — el
  resultado depende de un valor de parámetro específico, no de un
  rango razonable.

### Capa 7 — Robustez a supuestos de ejecución

**Pregunta:** ¿el resultado sobrevive a supuestos de llenado de
órdenes más realistas/pesimistas que los del backtest actual?

**Método:** extiende `src/backtesting/stress_test.py` (ya existe,
sube costos + usa la peor ventana histórica) agregando: llenado al
open del día siguiente en vez de al close del día de la señal
(latencia real de decisión), y 2x la fricción actual.

**Criterio:**
- VALIDATED: Sharpe > 0 y retorno neto positivo bajo AMBOS supuestos
  pesimistas combinados (llenado día siguiente + 2x fricción).
- INCONCLUSIVE: no aplica (esta capa siempre es computable con los
  datos ya disponibles).
- REJECTED: Sharpe ≤ 0 o retorno neto negativo bajo esos supuestos.

## Orden de ejecución

1. Capa 1 (reutiliza infraestructura ya construida, más rápida).
2. Capa 7 (también reutiliza infraestructura existente, stress_test.py).
3. Capa 6 (perturbación de parámetros, moderada).
4. Capa 4 (placebo — requiere diseño cuidadoso de potencia).
5. Capa 5 (leave-one-group-out, requiere clasificación por grupo).
6. Capa 3 (DSR+PBO — requiere primero el conteo completo de variantes
   históricas en los ADRs, trabajo manual de catalogación).
7. Capa 2 (sesgo de supervivencia — la más incierta en viabilidad de
   datos, se deja al final a propósito para no bloquear el resto si
   no se consigue un universo neutral reconstruible).

## Veredicto final de EXP-003

No es un promedio ni una votación de las 7 capas. Se reporta cada capa
por separado, con su label individual, y una síntesis en prosa de qué
significa el patrón completo — igual que el appendix de EXP-002
reportó hallazgos genuinamente mixtos sin forzar un veredicto único.
Si el usuario pide explícitamente un semáforo agregado, eso se decide
al final, con las 7 capas ya corridas y visibles, nunca antes.
