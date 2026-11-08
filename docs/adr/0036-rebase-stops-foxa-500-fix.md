# ADR 0036 — Rebase de capital inicial, recálculo de stops, y fix del 500 en vender-simbolo

## Contexto

Tras reconciliar las 13 posiciones reales (ADR 0035), el usuario pidió
"borrón y cuenta nueva" a partir del lunes 2026-11-09: mantener las
posiciones ya abiertas (no cerrarlas ni reabrirlas), pero que el
retorno acumulado arranque en 0% desde ese punto y que los stops estén
bien calculados — en vez de arrastrar el capital inicial original
($2,000 repartido el 2026-11-05) contra el equity ya movido por la
reconciliación.

## Decisión 1 — `rebasar_y_recalcular_stops()`

Nueva función en `live_engine.py` + `POST
/admin/live/rebasar-y-recalcular-stops`: para cada bucket, recalcula
el `stop_price` de cada posición abierta con el dato más fresco
(tomando el máximo contra el guardado — nunca lo baja, misma regla
del trailing stop normal), y re-basa `starting_capital`,
`peak_equity` y `day_start_equity` al equity actual (cash + valor del
blend + valor de mercado de las posiciones abiertas). No cierra ni
abre ninguna posición, no manda ninguna orden — es contabilidad pura.

## Decisión 2 — Fix del 500 en `/admin/live/vender-simbolo`

Al vender FOXA (residuo huérfano, ver ADR 0035) un domingo, la orden
quedó correctamente encolada por IBKR para el lunes (mismo patrón ya
documentado en ADR 0031/0035), pero `vender_simbolo_live` no
capturaba `OrdenNoLlenada` y devolvía un 500 genérico en vez de
reportar el estado real. Ahora devuelve
`{"status": "encolada_o_fallida", "detalle": ...}` en ese caso.

## Validación

159→163 tests pasan — incluye un test que confirma que el stop solo
sube (nunca baja) y que el capital/equity se re-basa correctamente.
