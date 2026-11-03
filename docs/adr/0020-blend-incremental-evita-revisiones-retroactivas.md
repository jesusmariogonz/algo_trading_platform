# ADR 0020 — El blend SPY/GLD se avanza incrementalmente, no se recompone desde cero

## Contexto

El 3-nov-2026 se detectó que las Routines de producción (`trig_0143jvtBiKDiQVjXocmdVFfW`
y `trig_01NeXE4j9zyiRBHP1bwSGrfZ`) llevaban **3 días reportando
"SUCCEEDED" sin producir ningún tick nuevo** — `state.json` y
`history.json` seguían exactamente iguales a como quedaron tras la
migración manual del 1-nov-2026 (ADR 0019).

Diagnóstico, corriendo el pipeline manualmente paso a paso:

- La descarga de datos y los indicadores funcionaban bien.
- `run_daily_tick` sí procesaba el día correctamente, pero disparaba
  la alerta de ADR 0017 ("salto de equity sospechoso") para
  `riesgo_alto` y `mean_reversion`: ambos cayeron ~25.6% de un día a
  otro, sin tener ninguna posición abierta — su equity es 100% el
  blend SPY/GLD.
- SPY y GLD en sí mismos estaban perfectamente normales (sin saltos).
  El problema era el **nivel del índice sintético del blend**, que se
  desplazó ~25% entre el 1 y el 3 de noviembre pese a que los
  retornos diarios reales de SPY/GLD en ese período fueron mínimos.

## Causa raíz

`_blend_price_series()` recomponía el índice sintético desde el
**primer día de todo el historial disponible** en cada llamada
(`100.0 * (1 + blend_ret).cumprod()`). yfinance revisa precios
ajustados de días viejos de forma retroactiva (ya documentado en ADR
0012/0013 para comparaciones de backtest) — una sola revisión a un
dato de hace meses desplaza **todo** el nivel del índice compuesto,
aunque nada haya pasado en el mercado. Hasta ahora solo habíamos visto
este efecto contaminar comparaciones de backtests exploratorios; esta
es la primera vez que se confirma que también contamina el **marcado
a mercado en producción**, con dinero (simulado) real.

Las Routines, al toparse con la alerta de ADR 0017 (diseñada
justamente para detectar esto), optaron por precaución no commitear
— correctamente cauteloso, pero sin una instrucción explícita de qué
hacer, quedaron en un bucle silencioso de "alerta → no commitear →
el problema de fondo nunca se corrige → mismo problema al día
siguiente".

## Decisión

Se reemplaza el recálculo completo por un **avance incremental**: el
estado de cada bucket ahora persiste `blend_last_price`,
`blend_last_date` y `blend_last_components` (el cierre crudo de SPY y
GLD el día del último precio conocido). Cada tick:

1. Si no hay precio previo persistido (primera vez): cae una única
   vez al cálculo completo (`_blend_price_series`) para establecer la
   base, y guarda también los componentes crudos de ese día.
2. Si ya hay un precio previo: solo mira los días **posteriores** al
   último conocido, calcula el retorno de cada día nuevo contra el
   cierre crudo YA PERSISTIDO (nunca contra lo que el dato de ese día
   diga hoy — esa es la pieza clave, ver más abajo), compone esos
   retornos sobre `blend_last_price`, y actualiza los 3 campos.

Con esto, una revisión retroactiva a un dato de hace meses **ya no
puede** desplazar el valor de hoy — como máximo puede afectar el
precio del día más reciente antes de que el mercado cierre (riesgo
mucho menor, ya acotado, documentado desde ADR 0012).

### El error en el primer intento de implementación

La primera versión de este fix solo persistía el *nivel del índice*
(`blend_last_price`/`blend_last_date`) y, para calcular el retorno del
primer día nuevo, volvía a leer el cierre crudo del último día
conocido desde los datos actuales — exactamente el mismo problema un
paso más adelante: una revisión futura a ese mismo día seguiría
colándose. Un test de regresión escrito a propósito para esto
(`test_blend_incremental_price_ignores_revisions_to_old_history`) lo
detectó antes de llegar a producción: simula una "revisión" del día 1
después de haberlo consumido, y confirma que el resultado no debe
verse afectado en absoluto. La solución fue persistir también los
cierres crudos de los componentes (`blend_last_components`), no solo
el nivel compuesto — así el ancla para el siguiente retorno nunca se
vuelve a leer desde una fuente que puede cambiar.

## Migración del estado real (3-nov-2026)

Se estableció la base del blend incremental para los 4 buckets con el
precio real de hoy (recompone el historial completo UNA última vez,
como está diseñado para la primera llamada). El nuevo nivel resultó
~25.6% menor al que tenían `riesgo_alto` y `mean_reversion` antes (sin
posiciones abiertas, 100% expuestos al blend) — esto es una
**corrección de datos, no una pérdida de mercado real**: el
`peak_equity`/`day_start_equity`/`last_equity` de los 4 buckets se
re-basearon al valor real de hoy, exactamente la misma lógica que se
aplicó en ADR 0019 tras la migración de capital, para que el circuit
breaker no interprete esta corrección como un drawdown real y
suspenda los buckets en falso. Verificado: tras el fix, el tick corre
limpio, sin alertas ni suspensiones, y es idempotente (correrlo dos
veces el mismo día no cambia nada).

`starting_capital` de cada bucket NO se tocó — sigue siendo el
capital originalmente inyectado; `cumulative_return_pct` de
`riesgo_alto`/`mean_reversion` ahora refleja honestamente que su valor
real siempre fue menor de lo que el cálculo con el bug sugería, no
una pérdida nueva de hoy.

## Lección para el futuro

Cualquier serie de precios que se use para marcar a mercado dinero
(real o simulado) en producción debe avanzarse incrementalmente desde
un ancla persistida, nunca recomponerse desde el historial completo en
cada corrida — el costo de recomponer todo "porque es más simple" es
quedar silenciosamente expuesto a que cualquier revisión de datos
viejos contamine el valor de hoy. Ver también ADR 0014 (bug de
migración de unidades) y ADR 0019 (bug de re-base de capital): el
patrón recurrente en los tres es el mismo — un valor persistido que
deja de corresponder a la realidad sin que nada en el código lo
detecte, hasta que la red de seguridad de ADR 0017 lo marca.
