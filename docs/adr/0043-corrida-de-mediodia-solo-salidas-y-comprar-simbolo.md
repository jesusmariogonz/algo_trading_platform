# ADR 0043 — Corrida de mediodía (solo salidas) + endpoint comprar-simbolo

## Contexto

El motor en vivo corre 2x/día (apertura 9:35am ET, cierre 4:30pm ET).
Con el stop ya chequeado contra precio en vivo (ADR 0042), una
posición que rompe su stop a media mañana no se cierra hasta la
corrida de cierre — y si esa corrida cae justo al cierre de mercado,
la orden puede quedar "PreSubmitted" (encolada, no confirmada) en vez
de ejecutarse, como pasó el 18-nov con MRK y XLV en mediano_plazo.

Por separado, al deslaverancar `largo_plazo` cerrando DBC manualmente
(ADR 0035/ventana de incidente), `/live/reconciliar` reveló que la
cuenta real terminó en **corto** en DBC (-10) y XYZ (-1) — ningún
bucket cree tener esas posiciones. Hipótesis: la posición real ya
estaba en cero por un desajuste previo (otro remanente del incidente
del 5-nov) antes de que el motor mandara su venta, así que la venta
"normal" la volvió corta en vez de cerrarla. No hay forma de aplanar
esto sin un endpoint de compra puntual — existía `vender-simbolo` para
el caso simétrico (residuo huérfano largo) pero no su contraparte.

## Decisión 1 — Corrida de mediodía, solo revisión de salidas

`run_bucket_tick_live`/`run_daily_tick_live` (`live_engine.py`) y
`/live/ejecutar`, `/live/refrescar-datos-y-ejecutar`,
`/live/refrescar-en-segundo-plano` (`trading_api.py`) ganan un
parámetro `evaluar_entradas: bool = True`. En `False`, la sección de
entradas se salta por completo (ninguna señal nueva se evalúa, ninguna
orden BUY se manda) — las salidas (stop contra precio en vivo /
señal) se siguen revisando siempre, sin cambios.

No se repite la decisión de entrada porque las señales son diarias
(no cambian de valor entre apertura y mediodía) — correr las entradas
otra vez solo repetiría exactamente lo mismo que ya se decidió en la
apertura, sin ganar nada y complicando el historial del día.
`_fusionar_descartados` (ya existente, pensada justo para corridas
repetidas el mismo día) preserva sin cambios la lista de candidatos
descartados de la apertura cuando esta corrida no genera ninguno
nuevo — no hizo falta tocarla.

Un nuevo trigger programado ("Trading en vivo IBKR — mediodía, solo
salidas") llama a `/live/refrescar-en-segundo-plano?evaluar_entradas=false`
entre la apertura y el cierre.

## Decisión 2 — Endpoint `/admin/live/comprar-simbolo`

Simétrico a `/admin/live/vender-simbolo`: compra a mercado un símbolo
puntual fuera de cualquier bucket trackeado, sin tocar `state.json`.
Para aplanar los residuos cortos de DBC/XYZ a cero (comprar de vuelta
exactamente las shares en corto) una vez identificados vía
`/live/posiciones-reales`.

## Validación

254 tests pasan (antes: 249). Nuevos: 2 en `test_live_engine.py`
(entradas no se abren con `evaluar_entradas=False` aunque haya señal;
las salidas se siguen revisando igual) y 3 en `test_trading_api.py`
para `comprar-simbolo` (requiere token, compra y desconecta, reporta
encolada en vez de 500 — mismo patrón que `vender-simbolo`). Varios
tests existentes que stub-eaban `run_daily_tick_live`/
`_ejecutar_live_sin_auth`/`_refrescar_y_ejecutar_sin_auth` con firmas
sin el nuevo parámetro se ajustaron para aceptarlo.

## Pendiente

- Desplegar a la VM (`git pull` + `pytest` + `systemctl restart
  trading-api`) — manual, igual que el resto de los cambios de esta
  sesión.
- Una vez desplegado, comprar de vuelta DBC (10) y XYZ (1) vía
  `comprar-simbolo` para dejar la cuenta real en cero en ambos
  símbolos.
- Investigar con más detalle (logs de la VM, `journalctl`) cómo
  llegaron esos dos símbolos a estar en corto antes de la venta que
  los encontró en cero — no se identificó la causa exacta, solo el
  síntoma y la corrección.
