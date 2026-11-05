# ADR 0028 — Ledger de transacciones del blend + inversión real en el motor en vivo

## Contexto

Dos pedidos del usuario tras preguntar cuánto había generado el blend
SPY/GLD hasta ahora:

1. Un reconstrucción manual de esa ganancia no cuadró con el
   `bench_shares` real guardado en `state.json` — no hay un registro
   explícito de transacciones del blend, solo el saldo final. Sin eso,
   cualquier intento de atribuir la ganancia es una reconstrucción
   aproximada, no un hecho verificable.
2. El motor en vivo (IBKR), desde ADR 0023, deliberadamente NO invierte
   el cash ocioso en el blend (se queda como cash puro) — decisión
   tomada para minimizar volumen de órdenes reales durante la
   validación inicial. El usuario decidió revertir esa decisión:
   quiere que el motor en vivo se comporte EXACTAMENTE igual que el
   motor simulado.

## Decisión 1 — Ledger de transacciones del blend

`src/paper_trading/blend_ledger.py`: cada vez que cash entra o sale
del blend, en cualquiera de los dos motores, se registra un renglón
(`bucket`, `fecha`, `tipo` compra/venta, `símbolo`, `monto_usd`,
`precio`, `shares`, `motivo`). Append-only, igual que `history.json`.
Dos archivos separados, uno por motor:
`data/paper_trading/blend_ledger.json` (simulado) y
`data/paper_trading_live/blend_ledger.json` (en vivo, vive solo en la
VM, igual que el resto de datos del motor en vivo — ver ADR 0023).

El motor simulado registra cada vez que `bench_shares` cambia
(capital inicial, financiar una entrada, recibir el producto de una
salida) con símbolo `"BLEND_SPY_GLD"` (no distingue SPY de GLD, igual
que siempre). `blend_ledger.ganancia_por_bucket()` calcula la ganancia
real a partir del ledger, sin necesitar reconstrucción manual nunca
más.

## Decisión 2 — El motor en vivo invierte el cash ocioso en el blend, con órdenes reales

`src/paper_trading/live_engine.py` ahora invierte el cash ocioso en
SPY+GLD (50/50 por valor), con órdenes reales vía
`src.broker.ibkr_adapter.ejecutar_orden_mercado` — a diferencia del
motor simulado, aquí SPY y GLD se registran como posiciones separadas
(`blend_spy_shares`, `blend_gld_shares` por bucket), porque IBKR no
soporta fracciones de acción vía orden de mercado: cada pata se
redondea hacia abajo a acciones enteras, y el sobrante (lo que no
alcanzó para una acción más) se queda como cash sin invertir.

Mecánica:
- `init_bucket_state(bucket, starting_capital, ib)`: si se pasa `ib`,
  invierte el capital inicial completo en el blend de entrada (igual
  que ADR 0007 en el motor simulado). Si `ib` es `None` (compat hacia
  atrás, usado en tests que no necesitan una conexión real), se queda
  como cash puro — comportamiento de antes de este ADR.
- Al abrir una posición: si el cash disponible no alcanza, se liquida
  primero la porción de blend necesaria (`_liquidar_de_blend`, vende
  proporcional por valor, redondeado hacia arriba para no quedar
  cortos) antes de mandar la orden de compra de la acción.
- Al cerrar una posición: el producto se reinvierte en el blend
  (`_invertir_en_blend`), no se queda como cash.
- `equity` ahora incluye el valor de mercado del blend
  (`cash + blend_spy_shares*precio_spy + blend_gld_shares*precio_gld + no_realizado`),
  antes solo era `cash + no_realizado`.

Toda compra/venta de SPY o GLD por este mecanismo queda en el ledger
del motor en vivo, igual que el simulado.

## Advertencia real: el tamaño actual de la cuenta hace esto poco efectivo todavía

SPY cotiza alrededor de $766/acción. Con el capital actual por bucket
(~$200-$430, ver ADR 0027), la mitad destinada a SPY casi nunca
alcanza para comprar ni **una sola acción** — la inversión en blend
se reduce casi completamente a GLD (~$372/acción, más alcanzable) o
queda sin invertir por el redondeo. Esto no es un bug: es la
consecuencia directa y esperada de operar acciones enteras con un
capital pequeño.

Esto se resuelve solo cuando el reset de la cuenta paper a $100,000
(solicitado el mismo día, procesándose "para el día siguiente" según
IBKR) se haga efectivo — con ese tamaño, cada pata del blend sí
alcanza para varias acciones de SPY y GLD cómodamente.

## Pendiente

- No se corrió todavía una validación de costo real (fricción de
  rebalancear el blend en cada entrada/salida vs. el rendimiento
  esperado del blend) — el usuario pidió avanzar directo con la
  implementación en vez de simularlo primero. Vale la pena revisar
  esto con datos reales una vez que haya suficiente historial en el
  ledger del motor en vivo.
- No se ha desplegado ni probado este código contra IBKR real todavía
  — se prueba primero en la VM (mismo proceso de siempre: git pull,
  pytest, restart del servicio) antes de dejar que una Routine
  automática lo dispare con dinero (paper) real.
