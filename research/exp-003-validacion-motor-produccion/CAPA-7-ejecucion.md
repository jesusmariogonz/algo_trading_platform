# EXP-003 — Capa 7: Robustez a supuestos de ejecución

Código: `capa7_ejecucion.py`. Mismo motor de simulación que la Capa 1
(capital compartido, sizing por riesgo sobre equity actual, trailing
stop), corrido sobre todo el período disponible (2021-11-22 a
2026-11-17, no ventanas). Compara baseline (fill al close del día de
la señal, fricción normal 0.1% por lado) contra un escenario
pesimista combinado: fill al OPEN del día siguiente + 2x fricción
(0.2% por lado). Si el día siguiente no existe dentro de la ventana
(señal en el último día de datos), esa operación se descarta — no se
inventa un precio.

## Resultado por bucket

| Bucket | Baseline (Sharpe / retorno) | Pesimista (Sharpe / retorno) | Label |
|---|---|---|---|
| largo_plazo | 0.78 / +45.96% | **-0.09 / -9.28%** | **REJECTED** |
| mediano_plazo | 1.39 / +209.36% | 0.53 / +49.19% | **VALIDATED** |
| riesgo_alto | 0.91 / +165.28% | 0.33 / +25.65% | **VALIDATED** |

Detalle completo en `resultados_capa7.json`.

## largo_plazo: por qué se revierte

Se inspeccionaron a mano los trades individuales (no solo el
agregado) para descartar un bug antes de reportar esto — los 5 peores
trades bajo el escenario pesimista son movimientos de mercado reales,
no datos corruptos: FXI -14.68% (2025-04-02 a 2025-04-07), IWM -9.43%
(2024-07-19 a 2024-08-05), SPY -3.6%/-4.6%/-3.0% en tres ventanas de
2024-2025. La ventana FXI/IWM cae en un período real de alta
volatilidad de mercado (principios de abril 2025).

El mecanismo: el baseline asume que un stop se llena exactamente AL
PRECIO del stop (optimista — un supuesto de ejecución tipo límite que
no siempre es real). El escenario pesimista reemplaza eso por "se
detecta el stop al close, se ejecuta al open del día siguiente" — si
el mercado sigue cayendo overnight (como en una racha de ventas
real), el precio de salida real es peor que el stop nominal. Esto es
exactamente el riesgo de ejecución que un stop-loss real enfrenta en
un movimiento rápido, no un artefacto de la simulación.

Con solo 96-100 operaciones en 5 años, un puñado de salidas mal
ejecutadas en una ventana de alta volatilidad basta para revertir el
signo del resultado completo — la misma fragilidad de "pocas
operaciones" que ya apareció en riesgo_alto en la Capa 1, aquí en
largo_plazo por una razón distinta (no es volumen de operaciones, es
sensibilidad a la calidad de ejecución del stop).

## Veredicto de esta capa (no de EXP-003 completo)

**largo_plazo: REJECTED. mediano_plazo y riesgo_alto: VALIDATED**
(ambos se degradan bajo el escenario pesimista — Sharpe cae a menos
de la mitad en los dos — pero se mantienen netos positivos). Esta es
la primera capa de EXP-003 donde un bucket cruza la línea a REJECTED,
y es justo el bucket (largo_plazo) que en la Capa 1 ya mostraba la
ventana reciente más débil de los 3.

## CORRECCIÓN (2026-11-19): largo_plazo con el filtro cross-sectional real de ADR 0034

**El REJECTED de `largo_plazo` arriba corresponde a una configuración
INCORRECTA** — el harness nunca implementó el filtro cross-sectional
de ADR 0034 (activo en producción hoy, solo para `largo_plazo`; ver
detalle completo en la corrección de CAPA-1-walk-forward.md).
`mediano_plazo`/`riesgo_alto` no usan ese filtro, sus resultados
arriba siguen vigentes.

| | Baseline (fill close, fricción normal) | Pesimista (fill open+1, 2x fricción) |
|---|---|---|
| Sharpe | 0.92 | **0.18** |
| Retorno | +59.52% | **+6.37%** |
| Drawdown | 12.82% | 22.55% |
| Trades | 89 | 91 |

**Label corregido: VALIDATED** — con el filtro real de producción
activo, `largo_plazo` SÍ sobrevive al escenario pesimista combinado
(Sharpe y retorno se quedan positivos, aunque se degradan fuerte:
Sharpe cae ~80%, igual de severo que el drawdown que sube a 22.55%).
**Esto revierte el hallazgo original.** Hipótesis plausible sin
verificar a fondo en esta capa (fuera de su alcance): el filtro
cross-sectional, al exigir momentum relativo fuerte, selecciona un
subconjunto de entradas de mejor calidad promedio — con suficiente
margen para absorber el supuesto de ejecución más duro sin cruzar a
pérdida neta, aunque por un margen bastante más delgado que el de los
otros 2 buckets (Sharpe cae ~80%, la mayor degradación relativa de los
3).
