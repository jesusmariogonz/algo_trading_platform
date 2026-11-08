# ADR 0037 — `initial_stop_price` y `asset_type` para el dashboard

## Contexto

El usuario pidió más columnas en la tabla de operaciones del
dashboard (`jgonzalez.app/pulso-mercado/trading`): stop inicial,
trailing stop actual, stop de cierre, tipo de activo, "momentum
score" y "horizonte de predicción". Los últimos dos no existen como
conceptos en este sistema (no hay un score unificado de momentum ni
forecasting de ningún tipo — de hecho se probó forecasting
probabilístico esta misma semana y no calibró, ver ADR 0033) —
quedan pendientes de que el usuario aclare qué espera exactamente,
para no inventar un número sin sentido.

Los otros 3 sí eran agregables con los datos ya existentes:

- **Trailing stop actual**: ya existía (`stop_price` en
  `open_positions`), solo faltaba exponerlo bien en el frontend.
- **Stop de cierre**: ya existía implícitamente — `closed_positions`
  se construye con `{**pos, ...}`, que ya incluye el `stop_price`
  vigente en el momento del cierre (sea por stop o por señal).
- **Stop inicial**: NO existía — `stop_price` se sobreescribe cada
  vez que el trailing stop sube, perdiendo el valor original de
  entrada.
- **Tipo de activo**: no existía ninguna clasificación.

## Decisión

- Nuevo campo `initial_stop_price` en `open_positions`, fijado una
  sola vez al abrir la posición (igual en `engine.py`,
  `live_engine.py`, y en `reconciliar_posiciones_automatico`) —
  nunca se toca después, a diferencia de `stop_price` que sigue
  subiendo con el trailing stop.
- Nuevo módulo `src/portfolio/asset_types.py`:
  `asset_type_de(symbol) -> str`, mapeo manual mantenido a mano
  (Commodity/Bond ETF/Equity ETF/Crypto/Stock por default) — no hay
  fuente de datos que ya traiga esto, así que es una lista explícita
  cubriendo los símbolos reales de los 3 universos.
- `src/paper_trading/export.py`: agrega `asset_type` a cada posición
  (abierta y cerrada) usando ese mapeo.

## Pendiente

- `momentum_score` y `prediction_horizon_days`: sin definición
  todavía — pendiente de que el usuario aclare qué espera
  exactamente antes de implementar nada.
- Falta actualizar `jesus-site/app/trading/page.js` para mostrar las
  columnas nuevas (`initial_stop_price`, `asset_type`) en la tabla —
  se hace en un commit aparte de ese otro repo.
- Posiciones ya abiertas ANTES de este cambio (ej. las 14
  reconciliadas el 2026-11-08) no tienen `initial_stop_price` en su
  registro histórico — solo las que se abran de aquí en adelante. No
  se intentó reconstruir retroactivamente (no hay forma confiable de
  saber cuál era el stop exacto en el momento real de entrada para
  esas 13).
