# ADR 0023 — Motor de paper trading EN VIVO, en paralelo al simulado

## Contexto

El motor simulado (`src/paper_trading/engine.py`) seguía siendo 100%
simulación: las entradas/salidas se calculan de precios históricos ya
descargados, nunca tocan un broker real. Con el adapter de IBKR ya
validado (ADR 0022), el usuario pidió explícitamente tener el esquema
"productivo" (órdenes reales contra la cuenta paper de IBKR)
**funcionando ya**, sin esperar a migrar o reemplazar el simulado —
los dos deben poder correr en paralelo para comparar resultados.

## Decisión

`src/paper_trading/live_engine.py` reusa la MISMA lógica de señales,
trailing stop y circuit breakers que el motor simulado (importa
`_signals_for_symbol`, `_last_row_as_of`, `RISK_LIMITS` y
`FRICCION_POR_LADO` directo de `engine.py` — una sola fuente de verdad
para las reglas de estrategia), pero:

- Cada entrada/salida manda una orden de mercado REAL vía
  `src.broker.ibkr_adapter.ejecutar_orden_mercado` y usa el **fill
  real** (`Fill.precio_promedio`) como precio de entrada/salida, en
  vez de asumir el precio de cierre del día.
- Si una orden no se llena (`OrdenNoLlenada`), la posición se queda
  exactamente como estaba (abierta si se intentaba cerrar, sin abrir
  si se intentaba entrar) y se registra en `ordenes_fallidas_hoy` —
  nunca se asume un fill que no ocurrió.
- Estado completamente separado: `data/paper_trading_live/` (propio
  `state.json`/`history.json`), para no mezclar ni arriesgar el
  histórico ya acumulado del motor simulado.

### Diferencia deliberada: sin inversión de cash ocioso en benchmark

El motor simulado invierte el cash sin usar en el blend SPY/GLD (ADR
0007/0014) para no reportar un equity "parado". El motor en vivo NO
hace esto — el cash ocioso se queda como cash real en la cuenta.
Razón: invertir el cash ocioso en vivo significa mandar órdenes reales
de SPY/GLD constantemente solo para "parquearlo", multiplicando el
volumen de operaciones reales sin aportar nada a la pregunta que este
motor está validando (¿las señales se ejecutan bien contra un broker
real?). Consecuencia conocida: el equity de un bucket con mucho cash
ocioso no será 1:1 comparable al equity del mismo bucket en el motor
simulado — es una limitación aceptada, no un bug, y debe tenerse en
cuenta al comparar resultados entre ambos esquemas.

### Alcance: los 4 buckets desde el día uno

Decisión explícita del usuario: arrancar los 4 buckets
(`largo_plazo`, `mediano_plazo`, `riesgo_alto`, `mean_reversion`) con
órdenes reales desde el primer día, en vez de validar con uno solo
primero. Implica que un bug en la lógica de órdenes podría afectar a
los 4 buckets simultáneamente — riesgo aceptado conscientemente
(cuenta paper, no hay dinero real en juego).

### Reconciliación de posiciones

`posiciones_reconciliadas(ib)` compara lo que el estado local cree
tener abierto (sumado por símbolo, a través de los 4 buckets) contra
`src.broker.ibkr_adapter.posiciones_reales(ib)` — la fuente de verdad
real de la cuenta. Pensado para correrse como chequeo de salud
periódico, no está (todavía) integrado en `run_daily_tick_live()`.

## Endpoint real: `src/api/trading_api.py`

Reemplaza la app mínima que se creó a mano directo en la VM (solo
tenía `/health`) — desde este commit el código de la API vive
versionado en el repo:

- `POST /live/ejecutar`: corre un día del motor en vivo para los 4
  buckets. En la PRIMERA corrida (estado local vacío), reparte el
  equity real de la cuenta (`equity_de_cuenta_usd`, no
  `allocation.get_balances()` — esa reporta el capital del portafolio
  SIMULADO) entre los 4 buckets con las mismas proporciones de
  `src.portfolio.allocation.BUCKETS`. Corridas siguientes no vuelven a
  pedir equity (el estado ya existe por bucket).
- `GET /live/estado`: último snapshot guardado, sin conectar a Gateway
  ni arriesgar mandar ninguna orden.
- `GET /live/reconciliar`: compara posiciones esperadas (estado local)
  vs. reales (IBKR).

Todos protegidos por el mismo token Bearer que ya usaba `/health`.
`conectar()`/`desconectar()` del adapter se llaman en cada request
(no se mantiene una conexión persistente) — `desconectar()` corre
siempre en un `finally`, incluso si la ejecución del día falla a
medio camino.

## Pendiente

- No se ha confirmado todavía que IBC reautentique solo tras el cierre
  nocturno de sesión de IBKR (ver ADR 0022, sección Pendiente) — si el
  motor en vivo falla con error de conexión, es la primera causa a
  revisar, no un bug de este motor.
- Falta desplegar `src/api/trading_api.py` a la VM (reemplazando la
  app mínima creada a mano) y conectar las Routines reales a
  `POST /live/ejecutar`.
