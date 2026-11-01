# ADR 0014 — Cash ocioso: blend 50% SPY / 50% oro (GLD)

## Estado
Aceptado.

## Contexto
ADR 0013 dejó pendiente, explícitamente, la decisión sobre dónde invertir
el cash ocioso de cada bucket entre SPY (configuración original) y GLD
(oro). Con el problema de reproducibilidad de datos ya corregido (ver
ADR 0012), el trade-off medido fue:

| Destino del cash ocioso | Retorno neto (36 meses) | Drawdown máximo |
|---|---|---|
| 100% SPY | +22.07% | 13.63% |
| 100% GLD (oro) | +17.53% | 12.22% |

## Decisión
El usuario eligió un punto intermedio no probado antes: **50% SPY / 50%
GLD**, no uno de los dos extremos.

## Implementación
`BENCHMARK_SYMBOL` en `src/paper_trading/engine.py` pasa de `"SPY"` a
`"BLEND_SPY_GLD"` para los 3 buckets. Se agregó `_blend_price_series()`:
construye un índice sintético, rebalanceado diariamente, que compone el
retorno ponderado de SPY y GLD cada día, empezando en una base de 100 —
**no son acciones reales de ningún símbolo**, es una unidad de cuenta
interna para marcar a mercado el cash ocioso (consistente con cómo ya
funcionaba `bench_shares` antes, solo que ahora referencia un índice
compuesto en vez de un solo símbolo).

## Bug real encontrado y corregido durante el despliegue
Al cambiar `BENCHMARK_SYMBOL` de `"SPY"` a `"BLEND_SPY_GLD"` y correr el
tick sobre el estado ya persistido (`data/paper_trading/state.json`), el
equity de Riesgo Alto se desplomó a **-75.11%** en un solo tick — un
resultado absurdo, no un movimiento real de mercado. Causa: `bench_shares`
ya guardaba una cantidad calculada como `dólares / precio_de_SPY`
(~$755 ese día); al reinterpretar esa misma cantidad como "unidades del
nuevo índice sintético" (que arranca en base ~100, no ~755), el valor en
dólares se multiplicó por un precio equivocado, destruyendo ~85% del
valor de la noche a la mañana sin que pasara nada en el mercado.

**Corrección aplicada**: antes de correr el primer tick con el blend
activo, se migró `bench_shares` de cada bucket preservando el valor en
dólares exacto:
```
valor_dólares = bench_shares_antiguo × precio_SPY_hoy
bench_shares_nuevo = valor_dólares / precio_blend_hoy
```
Verificado: los 3 buckets mantuvieron su equity casi idéntico al día
anterior tras la migración (largo_plazo $433.19, mediano_plazo $333.17,
riesgo_alto $233.33 — sin cambios absurdos), antes de aplicarse
cualquier movimiento real de mercado del día.

## Lección para el futuro
**Cualquier cambio futuro en `BENCHMARK_SYMBOL` (o en la unidad de
cuenta de cualquier campo persistido en `state.json`) necesita una
migración explícita de datos, no solo un cambio de código.** El motor no
tiene ninguna protección automática contra este tipo de error — un
cambio de código que reinterpreta silenciosamente un campo persistido
existente es un riesgo real, ya materializado una vez aquí. Se
documenta para que la próxima persona (o sesión) que toque
`BENCHMARK_SYMBOL`, `risk_pct`, o cualquier otro parámetro que participe
en el cálculo de unidades guardadas, revise primero si el estado
persistido necesita convertirse antes de correr el siguiente tick.

## Qué NO se tocó
- Ningún criterio de entrada de las estrategias.
- Los circuit breakers y la fricción real siguen igual.
- Semiconductores/Defensa siguen fuera del universo (ADR 0013) — el
  usuario confirmó que la intención original era probarlos como
  activos operables, no como destino de cash, y esa prueba ya se hizo
  correctamente y se descartó.

## Pendiente
- Validar el blend 50/50 con más historial de paper trading real, no
  solo backtest.
