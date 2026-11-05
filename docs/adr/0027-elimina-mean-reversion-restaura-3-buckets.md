# ADR 0027 — Se elimina Mean Reversion RSI(2), se restauran los 3 buckets originales

## Contexto

ADR 0019 agregó Mean Reversion RSI(2) como 4to bucket (35% del
capital) basado en un backtest de muestra completa (+47.90% retorno
aislado, correlación 0.142 con el resto del sistema). ADR 0026
documentó una auditoría que aplicó la misma validación de walk-forward
rolling usada para descartar Bollinger %B (ADR 0025) y encontró que
la estrategia no la sostiene: Sharpe OOS promedio **-0.032** (peor que
Bollinger, que salió rechazado con +1.076), 2 de 5 ventanas con
pérdida, y ningún peso de asignación mejora el portafolio de control
en la validación — monotónicamente peor cuanto más peso se le da.

Una investigación de seguimiento (referenciada en ADR 0026) encontró
que el +47.90% original **no es reproducible**: con el mismo código,
mismo universo y mismo `risk_pct`, el backtest de hoy da +19.09% — casi
el mismo número de operaciones (157 vs. 156 documentadas), pero
resultado financiero muy distinto, consistente con el mismo tipo de
problema de revisión retroactiva de datos de `yfinance` ya confirmado
en ADR 0020 (no se pudo confirmar al 100% por falta de un snapshot
histórico de precios para comparar).

## Decisión

Se elimina `mean_reversion` como bucket activo, en ambos motores
(simulado y en vivo contra IBKR). Se restaura la proporción original
13/10/7 entre los 3 buckets de siempre:

- Largo Plazo: 28.17% -> **43.33%**
- Mediano Plazo: 21.67% -> **33.33%**
- Riesgo Alto: 15.17% -> **23.33%**

El código de la estrategia (`src/strategies/mean_reversion_rsi2.py`)
y su entrada en `SIGNAL_FNS` se conservan — no se borra el archivo,
solo se desactiva como bucket (sale de `BUCKET_CONFIG` en
`daily_signals.py`, `BENCHMARK_SYMBOL` y `RISK_LIMITS` en
`engine.py`). Puede reconsiderarse en el futuro si aparece evidencia
mejor, pero no como está hoy.

## Migración de capital

Mean Reversion RSI(2) no tenía ninguna posición abierta en ningún
motor (0 en simulado, 0 en vivo) — toda su asignación estaba como
cash-en-blend (simulado) o cash puro (vivo). Esto simplifica la
migración: no hace falta vender nada, solo redistribuir el valor en
dólares a los 3 buckets restantes en proporción 13/10/7, re-baseando
`starting_capital`/`peak_equity`/`last_equity`/`day_start_equity` de
cada bucket receptor (lección de ADR 0019: nunca mover capital sin
re-basear, o los circuit breakers lo malinterpretan como drawdown
real).

### Motor simulado (`data/paper_trading/state.json`)

Capital liberado de mean_reversion: $257.06.

| Bucket | Recibe | starting_capital antes -> después |
|---|---|---|
| largo_plazo | +$111.39 | $317.13 -> $428.52 |
| mediano_plazo | +$85.69 | $281.81 -> $367.50 |
| riesgo_alto | +$59.98 | $151.66 -> $211.64 |

Verificado: tick de prueba corrido limpio tras la migración, sin
alertas de salto de equity (ADR 0017) ni suspensiones falsas.

### Motor en vivo (`data/paper_trading_live/state.json`, en la VM)

Mismo procedimiento, aplicado directo en la VM de Google Cloud (ese
archivo nunca se versiona en git, ver ADR 0023 — vive solo en el
filesystem de la VM). Mean_reversion tampoco tenía posiciones reales
abiertas en IBKR, así que tampoco hizo falta vender nada ahí — pura
redistribución de cash entre buckets dentro de la misma cuenta.

## Verificación antes de las corridas automáticas de mañana

Ambos sistemas (la Routine del motor simulado y los triggers de
`/live/refrescar-datos-y-ejecutar` para IBKR) iteran sobre
`BUCKET_CONFIG`/`ACTIVE_BUCKETS`, que ahora solo tienen 3 entradas —
no requieren ningún cambio adicional de código para funcionar
correctamente con la nueva asignación en su próxima corrida
(apertura y cierre de mañana, 6-nov-2026).

## Lección para el futuro

Segunda vez en esta sesión que un backtest de muestra completa resulta
no reproducible con datos de hoy, ambas veces en buckets relacionados
con el mismo problema de fondo (revisiones retroactivas de datos). A
partir de ahora, cualquier número de backtest que se use para aprobar
una decisión de capital real debería re-verificarse como reproducible
poco antes de la aprobación final, no solo confiar en el número
documentado en el momento en que se corrió originalmente.
