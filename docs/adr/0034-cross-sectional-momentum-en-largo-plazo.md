# ADR 0034 — Cross-sectional momentum en producción para `largo_plazo`

## Contexto

ADR 0033 documentó la investigación de 10 hipótesis de filtros de
sizing/entrada probadas con walk-forward rolling. De los 2 candidatos
finales para `largo_plazo` (`time_series_momentum`), el usuario eligió
**cross-sectional momentum** (Hipótesis #3) por tener el mejor
retorno/Sharpe ajustado a riesgo de los dos, con cero ventanas
negativas en las 5 pruebas OOS:

| | Baseline | Cross-sectional momentum |
|---|---|---|
| Sharpe OOS prom (std) | 1.33 (1.56) | 2.25 (1.43) |
| Retorno | +8.91% | +19.14% |
| Drawdown | 8.76% | 6.99% |
| Ventanas negativas | 1/5 | 0/5 |

Costo: descarta ~67.5% de las señales de entrada (opera ~3x menos
seguido), un trade-off aceptado explícitamente.

## Decisión

Nuevo filtro de entrada en `src/paper_trading/engine.py` y
`src/paper_trading/live_engine.py` (ambos motores, simulado y en
vivo, para que se comporten igual — mismo criterio que el resto del
proyecto): además de la señal propia de la estrategia (momentum
absoluto vs. su propio pasado), exige que el símbolo esté en el
percentil ≥70 de retorno relativo (`return_126d`) DENTRO de su
universo, el mismo día:

```python
CROSS_SECTIONAL_FILTER_BUCKETS = {"largo_plazo"}
CROSS_SECTIONAL_PERCENTIL_MIN = 0.70
```

Nueva función `_percentiles_cross_sectional_hoy(universe, symbols,
as_of)` en `engine.py` (reutilizada por `live_engine.py`): calcula el
percentil (`rank(pct=True)`) del `return_126d` de cada símbolo del
universo del bucket contra el resto, el día más reciente disponible.
Si el candidato no pasa `return_126d > 0 AND percentil >= 0.70`, la
entrada se descarta ese día — igual que cualquier otro motivo de
"no cumple la señal", no afecta posiciones ya abiertas ni el trailing
stop.

El filtro se activa **solo para `largo_plazo`** —
`CROSS_SECTIONAL_FILTER_BUCKETS` es un set explícito, no un flag
global, para que quede claro en el código que es deliberado y no un
descuido. `mediano_plazo` y `riesgo_alto` siguen sin este filtro
(ADR 0033: en esos dos buckets el resultado fue ambiguo o negativo).

## Por qué no se combinó con otros filtros ganadores

ADR 0033 ya documentó que combinar los 5 filtros que mejoraron
`largo_plazo` por separado (correlación, cross-sectional momentum,
breadth, trend efficiency, residual momentum) empeora progresivamente
el resultado — se solapan 78% entre sí y la combinación completa
reduce el retorno a 4.24% al descartar 77% de las señales. Se
implementa únicamente el ganador individual.

## Validación

149→152 tests pasan (3 nuevos: `test_filtro_cross_sectional_rechaza_simbolo_con_percentil_bajo_en_largo_plazo`,
`test_filtro_cross_sectional_no_aplica_fuera_de_largo_plazo` en
`engine.py`, y el equivalente en `live_engine.py`) — confirman que el
filtro rechaza el símbolo de menor percentil relativo y que NO aplica
fuera de `largo_plazo`.

## Pendiente

- Esto es el primer día que corre en producción real (simulado y en
  vivo) — no se ha observado todavía su comportamiento con datos
  frescos del día, solo con walk-forward histórico.
- Si en unas semanas el comportamiento real diverge mucho de lo
  esperado por walk-forward, revisar — mismo criterio de vigilancia
  que ya se aplicó a Mean Reversion RSI(2) (ADR 0019/0026/0027).
