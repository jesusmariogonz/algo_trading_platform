# ADR 0022 — Broker real: IB Gateway vía IBC + adapter `ib_async`

## Contexto

El motor (`src/paper_trading/engine.py`) simula operaciones desde el
inicio del proyecto: las entradas/salidas se calculan directamente de
precios históricos ya descargados (yfinance), nunca se mandan a un
broker real. Se evaluó conectar la cuenta paper trading real de IBKR
(Interactive Brokers) para que las corridas lean posiciones/fills
reales en vez de simularlos.

Intentos descartados antes de llegar a esta decisión:

- **OAuth 1.0a**: confirmado por IBKR como exclusivo para clientes
  institucionales, no disponible para cuentas individuales/retail.
- **IBeam** (automatización del Client Portal Gateway vía Selenium):
  login web se completaba pero el Gateway entraba en un ciclo
  "Repeatedly reauthenticating failed 3 times" sin resolución — bug
  conocido y sin arreglo documentado en el propio proyecto (GitHub
  Issues #267, #152), reproducido de forma consistente en más de un
  tamaño de VM y en más de un día distinto, descartando recursos y
  ventana de mantenimiento como causa.

## Decisión

Usar **IBC** (`hartza-capital/IBC`, fork con soporte TOTP del proyecto
original retirado) para automatizar el login de **IB Gateway clásico**
(no el Client Portal Gateway que usa IBeam) en una VM dedicada de
Google Cloud (`us-central1-f`, Always Free tier). IBC maneja
usuario/password/TOTP (vía `Ib2FA` en `config.ini`) contra el diálogo
nativo de Gateway, sin pasar por el flujo web que falla en IBeam.

Arquitectura de red, de adentro hacia afuera:

1. **IB Gateway** escucha en `127.0.0.1:4002` (paper trading) — nunca
   expuesto a la red, ni siquiera dentro de la VM más allá de
   localhost.
2. **`trading-api`** (FastAPI/uvicorn, `127.0.0.1:8080`): única pieza
   con permiso de hablar con Gateway. Autenticada por token (no hay
   capa de usuarios, es un secreto compartido).
3. **Caddy**: reverse proxy con HTTPS automático (Let's Encrypt) en
   `https://ibkr.jgonzalez.app`, único punto expuesto a internet.

Esto evita dos problemas a la vez: nunca hay que exponer el puerto del
broker a internet, y cualquier cliente que solo pueda salir por HTTPS
(incluyendo sesiones de Claude Code en la nube, que no tienen salida
TCP arbitraria) puede disparar acciones en la VM sin SSH.

`src/broker/ibkr_adapter.py` es la única pieza del repo que importa
`ib_async` — conecta a Gateway, consulta cuenta/posiciones reales, y
manda órdenes de mercado esperando su fill real (`ejecutar_orden_mercado`,
con timeout explícito vía `OrdenNoLlenada` — el adapter nunca decide
qué hacer si una orden no se llena, eso es decisión del motor).

Validado en producción (VM real, cuenta paper real `DUR328470`):
conexión, `accountSummary()`, y `managedAccounts()` funcionando de
punta a punta vía `ib_async` contra el Gateway levantado por IBC.

## Pendiente (no resuelto por este ADR)

- **Reautenticación diaria**: IBKR cierra la sesión del Gateway cada
  noche (hora servidor); falta confirmar en producción, sin
  intervención manual, que IBC puede relogear solo al día siguiente.
  Si falla, el síntoma esperado es que el adapter no logre conectar
  — no es un bug de este adapter ni del motor.
- **Integración con `run_bucket_tick`**: hoy sigue 100% simulado. Este
  ADR solo deja lista la pieza de conexión/ejecución; reescribir el
  motor para usar fills reales en vez de precios de cierre históricos
  es un cambio de arquitectura más grande, decidido como entrega
  separada por su tamaño.
