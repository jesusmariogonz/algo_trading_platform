# ADR 0019 — Se agrega Mean Reversion RSI(2) como 4to bucket (35%)

## Contexto

Tras cerrar la configuración oficial en ADR 0016 y descartar Donchian
Breakout y Risk Parity por empeorar el sistema (ADR 0018), se probó
**Mean Reversion RSI(2)** (Connors/Radge) como tercer candidato de la
misma lista externa de modelos — con una diferencia deliberada de
diseño respecto a los dos anteriores: en vez de competir por símbolo
dentro de un bucket existente (el error que diluyó Donchian), se midió
primero AISLADO, con capital y universo propios, para evaluar su
correlación con el sistema antes de decidir cómo mezclarlo.

## Reglas de la estrategia

- Filtro de régimen: solo opera LONG si `close > sma_200` — igual que
  las otras 3 estrategias en producción, exige tendencia alcista de
  fondo confirmada. La diferencia real es qué hace DENTRO de esa
  tendencia: compra debilidad temporal (RSI(2) < 10), no fortaleza.
- Salida: RSI(2) > 70 (recuperó) O cierre bajo su propio sma_5 (salida
  de seguridad) O stop ATR (2.0x, más ajustado que las otras 3 —
  horizonte de 2-15 días, no de meses).
- Universo: unión de los universos de Mediano Plazo y Riesgo Alto
  (119 símbolos), sin agregar ningún activo nuevo al sistema.

## Resultados medidos (datos reales congelados, 36 meses)

### Fase 1 — aislado (capital propio, sin mezclar con el portafolio)

| Métrica | Valor |
|---|---|
| Retorno 36mo | +47.90% |
| Drawdown máximo | 13.48% |
| Operaciones cerradas | 156 |
| **Correlación de retornos diarios con el control (ADR 0016/0018)** | **0.142** |

La correlación baja (vs. lo que hubiera sido agregar una 4ta señal de
momentum, que habría estado mucho más cerca de 1.0) es la evidencia
concreta de que esta estrategia gana dinero en condiciones mayormente
distintas al resto del sistema — diversificación real, no la misma
apuesta con otro nombre.

### Fase 2 — combinado (4 buckets reales, capital repartido)

Sensibilidad al peso de capital asignado a Mean Reversion (los otros 3
buckets escalados proporcionalmente, manteniendo su ratio interno
13/10/7):

| Peso a Mean Reversion | Retorno 36mo | Drawdown máximo |
|---|---|---|
| 0% (control) | +34.00% | 12.91% |
| 15% | +41.57% | 12.17% |
| 25% | +41.81% | 13.32% (ya peor que el control) |
| **35%** | **+43.61% (máximo medido)** | **11.75% (mejor que el control)** |
| 50% | +30.27% (peor que el control) | 9.19% |

La relación NO es monotónica: hay un punto óptimo cerca de 35%, no en
los extremos. Por debajo, se desaprovecha la diversificación; por
encima, se le quita demasiado capital a las 3 estrategias de momentum
(que individualmente rinden más que Mean Reversion) y el costo de
oportunidad supera el beneficio de diversificación. No se exploraron
puntos intermedios finos (30%, 40%) ni se corrió walk-forward — el
35% es el mejor de 4 puntos espaciados probados, no un óptimo
matemático verificado exhaustivamente. Se acepta como decisión
razonable dado el patrón claro de mejora en ambas métricas simultáneas
frente al control.

## Decisión

Se agrega "mean_reversion" como 4to bucket de producción con 35% del
capital total. Los 3 buckets existentes se escalan a 65% del total,
**manteniendo su proporción interna de siempre** (13/10/7, no un
reparto equitativo):

- Largo Plazo: 43.33% -> **28.17%**
- Mediano Plazo: 33.33% -> **21.67%**
- Riesgo Alto: 23.33% -> **15.17%**
- Mean Reversion: 0% -> **35.00%**

`risk_pct` = 2% por operación (igual que largo/mediano plazo). Circuit
breakers: `daily_loss_limit_pct` 1.5%, `drawdown_review_pct` 15% (más
holgado que largo/mediano porque el propio backtest aislado ya mostró
un drawdown normal de 13.48% — un límite más ajustado lo suspendería
por su comportamiento esperado, no por una anomalía real).

## Migración de capital real (paper trading)

El capital ya invertido en los 3 buckets existentes tiene posiciones
abiertas (ver ADR 0008/0014: nunca se liquida una posición para
rebalancear). La migración solo mueve el `bench_shares` (cash ocioso
en el blend SPY/GLD) disponible de cada bucket hacia el nuevo bucket
`mean_reversion` — nunca vende una posición abierta.

Resultado real el 1-nov-2026: Largo Plazo y Mediano Plazo tenían la
mayoría de su capital ya invertido en posiciones abiertas, así que solo
pudieron cederle a Mean Reversion lo que tenían líquido ($116.20 y
$51.52 respectivamente); Riesgo Alto no tenía posiciones abiertas, así
que cedió el monto completo necesario ($81.67) para llegar exactamente
a su nuevo objetivo. Mean Reversion arrancó con $249.38 (24.9% del
capital total, no el 35% teórico) — **convergerá al 35% real de forma
orgánica** a medida que las posiciones de Largo/Mediano Plazo cierren
por stop o señal y liberen más cash ocioso, sin ninguna acción manual
adicional.

### Bug encontrado y corregido durante la migración

El primer intento de migración solo actualizó `bench_shares`/`cash` de
los 3 buckets existentes, sin re-basear `starting_capital`,
`peak_equity` ni `day_start_equity` al nuevo principal (más pequeño)
post-migración. Al correr el siguiente tick, el motor interpretó la
reducción de capital como un drawdown real contra el principal viejo
(ej. Largo Plazo: equity bajó de $433.33 a $316.99 = 26.8% de
"drawdown" contra un límite de revisión de 6%) y **suspendió los 3
buckets por un falso positivo** — exactamente el tipo de problema que
la red de seguridad de ADR 0017 está diseñada para exponer (y lo hizo:
disparó la alerta de salto de equity >25% correctamente). Se corrigió
restaurando `state.json` desde git (sin cambios aún commiteados) y
repitiendo la migración, esta vez re-baseando `starting_capital`,
`peak_equity` y `day_start_equity` al equity real post-migración de
cada bucket. Verificado: tras el fix, el tick corre sin alertas ni
suspensiones, con retorno acumulado re-baseado a ~0% en los 3 buckets
migrados, como se espera justo después de una reasignación de capital.

## Lección para el futuro

Cualquier migración que cambie el principal de un bucket (no solo las
que cambian la semántica de un campo, como ADR 0014) debe re-basear
`starting_capital`/`peak_equity`/`day_start_equity` explícitamente —
de lo contrario los circuit breakers no distinguen entre "perdiste
dinero" y "te reasignaron capital a otro bucket".
