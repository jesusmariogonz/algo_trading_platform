# ADR 0024 — Corrige la distorsión de ~25.6% heredada del bug de ADR 0020

## Contexto

El usuario reportó ver -23.75% de retorno acumulado en `riesgo_alto` y
`mean_reversion` en el dashboard público, el mismo día que debían estar
cerca de 0% (recién migrados/creados el 31-oct y 1-nov). Primer
diagnóstico (incorrecto): se asumió que era un artefacto de no
re-basear `starting_capital` en la migración de capital de ADR 0019 —
pero ADR 0019 documenta explícitamente que ese re-baseo sí se hizo
correctamente en su momento.

Diagnóstico real, confirmado con los datos: el equity de AMBOS buckets
cayó exactamente **-25.6%** entre el 2026-10-30 y el 2026-11-02 — el
mismo porcentaje en los dos, el mismo rango de fechas en que ocurrió
el bug descrito en ADR 0020 (revisión retroactiva de `yfinance` que
desplazó el índice del blend SPY/GLD ~25.6% completo, antes del fix
del cálculo incremental el 3-nov). `largo_plazo` y `mediano_plazo`
casi no se vieron afectados porque la mayoría de su capital estaba en
posiciones abiertas, no en el blend — `riesgo_alto` y `mean_reversion`
estaban 100% en cash-en-blend (0 posiciones abiertas ninguno de los
dos desde su creación), así que absorbieron toda la distorsión sin
nada que la diluyera.

El fix de ADR 0020 evita que esto vuelva a pasar hacia adelante, pero
nunca corrigió el daño ya hecho en el `state.json`/`history.json` de
producción — `bench_shares` de ambos buckets quedó anclado al precio
distorsionado del blend, y el cálculo incremental (correcto desde el
fix) siguió avanzando correctamente desde esa base ya equivocada.

## Corrección aplicada

Como ninguno de los dos buckets tuvo ninguna operación (0 posiciones
abiertas/cerradas desde su creación), `bench_shares` nunca debió
cambiar por trading — solo el precio del blend. Esto simplifica la
corrección a:

```
equity_correcto(fecha) = starting_capital × (precio_blend(fecha) / precio_blend(2026-10-30))
```

usando el precio del blend ya recalculado con la lógica corregida de
ADR 0020 (datos limpios de hoy, sin la distorsión retroactiva). Se
recalculó `bench_shares`, `blend_last_price/date/components`,
`last_equity`, `peak_equity` y `day_start_equity` en `state.json`, y
se corrigió la curva completa en `history.json` (los 3 días con dato:
10-30, 11-02, 11-03, 11-04) para que la curva de equity del dashboard
no muestre un salto artificial seguido de una corrección abrupta.

Resultado: el retorno real del blend SPY/GLD en ese periodo fue
**+3.08%**, no -25.6%. Equity corregido:

| Bucket | Antes (distorsionado) | Después (correcto) |
|---|---|---|
| riesgo_alto | $115.64 (-23.75%) | $156.33 (+3.08%) |
| mean_reversion | $190.15 (-23.75%) | $257.06 (+3.08%) |

## Por qué este método es seguro

No se asumió ningún valor — se partió del único punto de anclaje
verificado como correcto (`starting_capital` en la fecha de creación
de cada bucket, documentado en ADR 0019) y se avanzó con el precio
real del blend, ya con el cálculo corregido de ADR 0020. El método
solo es válido porque ninguno de los 2 buckets tuvo trading de por
medio — si hubiera habido operaciones reales, este atajo no aplicaría
y habría que reconstruir el estado operación por operación.

## Lección para el futuro

Un fix que previene un bug hacia adelante (ADR 0020) no repara el
estado ya corrompido en producción — hace falta un paso explícito de
reparación de datos cuando se descubre que un bug ya escribió valores
incorrectos en `state.json`/`history.json`, no solo corregir el código
que lo causó.
