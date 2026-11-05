# ADR 0029 — Límite explícito de $2,000 USD en el motor en vivo

## Contexto

El reset de balance de la cuenta paper (pedido en sesión anterior,
ver ADR 0028) sí se aplicó, pero a **$100,000 pesos mexicanos**, no
dólares — la cuenta paper tiene como moneda base MXN. Convertido,
son ~$5,400 USD de equity real, confirmado con el nuevo endpoint
`/live/equity`.

El usuario decidió trabajar con lo que hay, pero pidió usar
**única y exclusivamente $2,000 USD** del total disponible, no todo
el equity de la cuenta — un límite deliberado, no el resultado de
`/live/ejecutar` repartiendo el equity real completo como hace en su
primera corrida.

## Decisión

Nuevo endpoint `POST /admin/live/reiniciar-capital?total_usd=2000`
en `src/api/trading_api.py`:

- Reparte `total_usd` entre los 3 buckets con las mismas proporciones
  que `BUCKETS` (13/10/7).
- Llama `live_engine.init_bucket_state(bucket, monto, ib)` por cada
  uno — invierte el capital inicial completo en el blend SPY/GLD con
  órdenes reales, igual que la primera corrida normal (ADR 0028).
- Seguridad: se niega con 409 si cualquier bucket tiene
  `open_positions` — hay que cerrarlas antes, no las toca.

Se usó una vez, vía HTTPS, para fijar el capital en vivo a $2,000 USD
el 2026-11-05 (estado previo: ~$1,006.88 USD en cash puro, sin
posiciones abiertas, remanente de la migración de ADR 0027 — se
confirmó vacío de posiciones antes de reinicializar).

## Por qué no simplemente usar el equity completo (~$5,400 USD)

Decisión explícita del usuario, no una limitación técnica — preferir
operar con un capital acotado y conocido en vez del total disponible
en la cuenta, mientras se sigue validando el motor en vivo.
