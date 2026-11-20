# EXP-003 — Síntesis final

Las 7 capas pre-registradas están corridas. Esta síntesis la escribe
el coordinador (Claude), con las 7 capas ya visibles — regla explícita
del pre-registro: "No es un promedio ni una votación de las 7 capas.
Se reporta cada capa por separado... y una síntesis en prosa."

## Tabla completa

| Capa | largo_plazo | mediano_plazo | riesgo_alto |
|---|---|---|---|
| 1 — Walk-forward rolling | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE |
| 2 — Sesgo de supervivencia | INCONCLUSIVE (no aplica) | VALIDATED | **REJECTED** |
| 3 — DSR + PBO (47 intentos históricos) | Ambiguo, sin resolver | **REJECTED** | **REJECTED** |
| 4 — Placebo (potencia verificada) | **REJECTED** | **REJECTED** | **REJECTED** |
| 5 — Leave-one-group-out | VALIDATED | VALIDATED | VALIDATED |
| 6 — Perturbación de parámetros | VALIDATED | VALIDATED | VALIDATED |
| 7 — Ejecución realista | VALIDATED | VALIDATED | VALIDATED |

(largo_plazo en Capas 1/4/6/7 usa la configuración CORREGIDA con el
filtro cross-sectional real de ADR 0034 — ver notas de corrección del
2026-11-19 en cada archivo. Capa 3 no se re-corrió tras la corrección,
su ambigüedad en largo_plazo queda abierta.)

## Lo que esto significa, bucket por bucket

**Dos capas (3 y 4) se diseñaron específicamente para responder "¿hay
una ventaja real, o es indistinguible del azar?" — las otras cinco
responden preguntas de robustez (¿es frágil?), no de habilidad.**

### riesgo_alto — el caso más claro, y el más preocupante

Tres hallazgos independientes apuntan en la misma dirección: DSR≈0
(no distinguible de ser el ganador de 47 configuraciones ya probadas
en la historia del proyecto), placebo en el percentil 55 (en la
mediana de lo que daría un orden al azar), y sesgo de supervivencia
confirmado material (26.21% anual con el universo curado a mano vs.
11.57% con una muestra neutral del S&P 500 — más del doble, y
probablemente un piso, no un techo, del sesgo real dado que el
universo neutral usado es estructuralmente más estable que el real).
Pasa las 3 pruebas de robustez (no depende de un sector, no es un pico
de parámetro aislado, aguanta ejecución realista) — pero "no es
frágil" y "tiene ventaja real" son cosas distintas, y aquí la evidencia
de habilidad real es la más débil de los 3 buckets.

### mediano_plazo — ventaja no demostrada, pero sin la bandera adicional de sesgo

DSR≈0 y placebo en la mediana (percentil 49) — mismo patrón que
riesgo_alto en las 2 pruebas de habilidad. A diferencia de
riesgo_alto, su universo SÍ pasó el chequeo de sesgo de supervivencia
(30.92% vs. 30.65%, prácticamente idéntico) — su universo de
large/mid-cap diversificado no depende de nombres elegidos con
hindsight. Pasa las 3 pruebas de robustez igual que los otros dos.

### largo_plazo — el cuadro más mixto, con una ambigüedad sin resolver

Placebo REJECTED (percentil 48, con la configuración corregida) pero
DSR quedó ambiguo sin resolver (REJECTED con Sharpe 0.78, VALIDATED
con Sharpe 2.25 — nunca se re-calculó con el Sharpe corregido de la
configuración real, 0.92 en el período completo). El sesgo de
supervivencia no aplica de la misma forma (universo de ETFs de clase
de activo, no acciones elegidas a mano). Pasa las 3 pruebas de
robustez. Es el único de los 3 donde la Capa 7 (ejecución) mostró que
el margen es más delgado (Sharpe cae ~80% bajo el escenario pesimista,
aunque se queda positivo).

## Síntesis de fondo

El patrón más fuerte y consistente de las 7 capas: **ninguno de los 3
buckets demuestra, con las pruebas diseñadas para medirlo
directamente, una ventaja distinguible del azar** — y en `riesgo_alto`
esto se agrava con sesgo de supervivencia confirmado. Al mismo tiempo,
ninguno de los 3 muestra señales de fragilidad extrema (sobreajuste a
un parámetro, dependencia de un sector, quiebre bajo ejecución
realista) — lo que sea que esté produciendo estos números no es un
artefacto de un solo supuesto frágil.

Esto no es lo mismo que "está probado que la estrategia no vale nada"
— la Capa 1 quedó INCONCLUSIVE en los 3 buckets por pocas operaciones,
así que la pregunta de consistencia temporal sigue abierta con los
datos disponibles. Lo honesto, con la evidencia reunida: **no hay
evidencia validada de que la configuración actual de producción tenga
una ventaja real sobre el azar**, con un hallazgo adicional y más
severo en `riesgo_alto` (sesgo de supervivencia material confirmado).

## Qué NO responde EXP-003 (por diseño, no por omisión)

No busca ni propone una configuración mejor — el pre-registro fue
explícito en que esto validaría o rechazaría la configuración EXACTA
de producción de hoy, nunca alternativas. "¿Es óptima la estrategia?"
no es una pregunta que este protocolo pueda responder, con cualquier
resultado que hubiera salido.
