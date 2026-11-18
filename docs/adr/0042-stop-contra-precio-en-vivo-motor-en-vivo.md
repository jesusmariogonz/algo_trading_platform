# ADR 0042 — Stop contra precio en vivo en el motor en vivo (IBKR)

## Contexto

Hoy el motor en vivo revisa stop/señal de salida dos veces al día
(apertura y cierre), siempre contra el `close` diario (yfinance) del
universo. Entre esas dos corridas, una posición puede romper su stop a
media mañana y el motor no se entera hasta la corrida de cierre —
horas de exposición de más sin ninguna razón técnica para esperar, ya
que a diferencia del motor simulado (`engine.py`, puramente histórico
por diseño — ver ADR 0001), el motor en vivo sí corre contra Gateway
real y ya usa cotizaciones en vivo en otra parte del código
(`ejecutar_orden_mercado` las usa como respaldo de precio tras una
orden).

No se cambia la cadencia de las corridas (siguen siendo 2x/día,
apertura/cierre) — solo el dato que se usa para decidir si el stop ya
se rompió dentro de esa corrida.

## Decisión

`src/broker/ibkr_adapter.py`: nueva función `precio_en_vivo(ib,
symbol)` — cotización de mercado vía `reqTickers` (mismo mecanismo ya
usado como respaldo en `ejecutar_orden_mercado`), con el último cierre
del ticker como segundo respaldo si no hay mid-price. Devuelve `None`
si Gateway no tiene nada disponible, en vez de tronar.

`src/paper_trading/live_engine.py`, dentro de `run_bucket_tick_live`:
el chequeo de `stop_hit` ahora usa `precio_en_vivo(ib, symbol)` cuando
está disponible, con fallback explícito al `close` diario si la
consulta falla por cualquier razón (sin suscripción de datos, símbolo
no encontrado, Gateway lento, o — en los tests — un `ib` que no
implementa `reqTickers`). La señal de salida (`exit_signal`) sigue
siendo diaria a propósito: depende de indicadores calculados sobre
velas diarias, no tiene un equivalente "en vivo" sin rediseñar la
estrategia misma. El precio de salida registrado sigue siendo el fill
real de `ejecutar_orden_mercado`, no el precio en vivo usado para
decidir — mismo patrón ya establecido para el stop guardado (ver test
`test_cierra_posicion_usa_el_fill_real_no_el_stop_guardado`).

Alcance explícito: solo el motor en vivo. El motor simulado
(paper, `engine.py`) no tiene datos intradía — yfinance no es
apto para eso (ADR 0001) — así que no aplica.

## Validación

249 tests pasan (antes: 243). Nuevos: 3 en `test_live_engine.py`
(cierra por precio en vivo aunque el cierre diario no toque el stop;
no cierra si el precio en vivo sigue arriba del stop; cae al cierre
diario si `precio_en_vivo` lanza una excepción) y 3 en
`test_ibkr_adapter.py` para `precio_en_vivo` (usa market price, cae al
close del ticker si no hay market price, devuelve `None` si no hay
ningún precio disponible).

## Pendiente

Desplegar a la VM (`git pull` + `pytest` + `systemctl restart
trading-api`) — manual, igual que el resto de los cambios de esta
sesión.
