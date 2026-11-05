# ADR 0031 — Fix del Error 10349: fijar TIF explícito en las órdenes

## Contexto

Desde el reset de la cuenta paper a $100,000 MXN, TODAS las órdenes
de mercado del motor en vivo se cancelaban instantáneamente
(<200ms), con el mensaje `Error 10349, reqId N: Order TIF was set to
DAY based on order preset.` en el log. Se descartaron varias
hipótesis probadas en vivo contra la cuenta real sin éxito: Trading
Permissions (Stocks ya habilitado), certificación de Market Data
API, "Read-Only Access" en Client Portal, y un reinicio completo de
la sesión de IB Gateway.

El usuario encontró la causa real, documentada en un hilo de GitHub
de `ib_async` (la librería que usa `src/broker/ibkr_adapter.py`):
https://github.com/ib-api-reloaded/ib_async/discussions/190

Cuando el campo `tif` (Time In Force) de la orden se deja vacío,
TWS/Gateway aplica el default de su "order preset" y manda el aviso
10349 — informativo, no un rechazo real. Versiones de `ib_async`
anteriores al fix en la rama `next` interpretan ese aviso como
cancelación de la orden y reportan `orderStatus.status = "Cancelled"`,
aunque la orden real pudiera seguir viva en TWS. Es un bug de la
librería cliente, no una restricción real de la cuenta — por eso
ningún cambio de configuración en IBKR tuvo efecto.

## Decisión

`src/broker/ibkr_adapter.py::ejecutar_orden_mercado`: se fija
`orden.tif = "DAY"` explícitamente en el objeto `MarketOrder` antes
de `ib.placeOrder`, en vez de dejarlo vacío (default implícito de
`ib_async`). Con `tif` fijado explícitamente, TWS no necesita aplicar
el default de su preset y no manda el Error 10349.

## Pendiente de confirmar

Este fix no se probó todavía contra una orden real después del
cambio (se aplicó y desplegó, pero la siguiente corrida con entradas
de verdad es la rutina automática de mañana, 2026-11-06, 9:00am ET).
Si el fix no es suficiente (ej. si además hay que confirmar el estado
real de la orden contra IBKR en vez de confiar ciegamente en el
evento de cancelación, como recomienda el mismo hilo de GitHub para
versiones de `ib_async` sin el fix completo), se revisará en esa
corrida.
