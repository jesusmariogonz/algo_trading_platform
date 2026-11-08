# ADR 0035 — Candado de horario regular + reconciliación automática en bloque

## Contexto

El motor en vivo quedó con 14 posiciones reales en IBKR que el estado
local desconocía (`/live/reconciliar` mostraba divergencia completa).
Investigando el log (`journalctl`), se encontró la causa real: varias
corridas manuales de prueba del 5-nov (noche, después del cierre de
mercado) mandaron órdenes de entrada que IBKR **no rechazó** —
las encoló para el siguiente open regular, con el aviso "Warning 399:
Your order will not be placed at the exchange until ... 09:30:00
US/Eastern". `ejecutar_orden_mercado` solo espera
`FILL_TIMEOUT_SEGUNDOS` (30s) antes de rendirse — nunca alcanza a ver
esas órdenes llenarse horas después, así que el motor las registró
como fallidas (`OrdenNoLlenada`) aunque sí se ejecutaron de verdad en
la apertura del viernes 6-nov. Esto NO es el mismo bug que ADR
0031/0032 (Error 10349 / fills fantasma con status mal reportado) —
es una categoría distinta: la orden sí se procesa correctamente, solo
que mucho después de que nuestro código dejó de esperarla.

## Decisión 1 — No abrir posiciones nuevas fuera de horario regular

`src/paper_trading/live_engine.py`: nueva función
`_mercado_regular_abierto_ahora()` — aproximación simple de horario
NYSE (9:30am-4:00pm ET, lunes a viernes, sin calendario de feriados).
En `run_bucket_tick_live`, el bloque de entradas se salta por completo
(`strategies = []`, igual que cuando el bucket está `blocked`) si el
mercado no está en horario regular — mismo patrón que los circuit
breakers existentes. Las SALIDAS (stop/señal) se siguen evaluando
siempre; solo las entradas nuevas se posponen.

No se intentó resolver esto alargando el timeout (esperar horas
dentro de una llamada HTTP síncrona no es viable) — la solución
correcta es simplemente no iniciar una orden que sabemos de antemano
que quedará encolada sin que podamos confirmarla en esta misma
llamada.

## Decisión 2 — Reconciliación automática en bloque

Nueva función `reconciliar_posiciones_automatico(ib)` y endpoint
`POST /admin/live/reconciliar-automatico`: compara las posiciones
reales de IBKR (`posiciones_reales_con_costo`) contra lo que cada
bucket cree tener abierto, y agrega automáticamente cualquier símbolo
real que el estado local no conozca — con su costo real (`avgCost`)
restado del cash del bucket, y el `stop_price` recalculado con la
fórmula real de la estrategia de ese bucket sobre el dato más
reciente (no un placeholder inventado). No toca símbolos ya
conocidos, ni SPY/GLD (blend, se trackea aparte). Reemplaza el
proceso manual símbolo por símbolo usado hasta ahora
(`/admin/live/fijar-estado-bucket`, que sigue existiendo para casos
que esta reconciliación automática no pueda resolver sola, ej.
símbolos ambiguos entre universos).

## Validación

155→157 tests pasan — incluye un test dedicado que confirma que el
candado de horario bloquea entradas nuevas (sin llamar
`ejecutar_orden_mercado` en absoluto) y dos tests de
`reconciliar_posiciones_automatico` (agrega lo desconocido, no toca
lo ya conocido).

## Pendiente

- Ejecutar `/admin/live/reconciliar-automatico` una vez para
  absorber las 14 posiciones reales encontradas el 2026-11-08 —
  se hace en una sesión interactiva, no automatizado en este ADR.
- La aproximación de horario no tiene en cuenta feriados de NYSE
  (ej. Thanksgiving) — si una Routine automática corre en un día
  feriado, el candado la dejará creer que el mercado está abierto
  cuando no lo está. No se consideró crítico resolver esto ahora
  (las Routines ya están programadas en horario laboral normal, el
  caso real que causó este bug fue prueba manual fuera de horario,
  no un feriado).
