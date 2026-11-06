# ADR 0032 — Fix: no confiar ciegamente en `trade.orderStatus.status`

## Contexto

Tras el fix del Error 10349 (ADR 0031), se corrió el motor en vivo
varias veces el 2026-11-05 para validarlo. Todas las corridas
reportaron las mismas 11 órdenes de entrada como fallidas (`Cancelled`
primero, `Inactive` después del fix de TIF) — pero al revisar
`/live/reconciliar` el 2026-11-06, la cuenta real de IBKR SÍ tenía
las 11 posiciones, en cantidades que son casi exactamente 4× lo
pedido en cada corrida individual (ej. ROKU: se pedían 2 acciones por
corrida, la cuenta real tenía 8 — consistente con 4 corridas
ejecutándose cada una de verdad, pese a que las 4 reportaron
"fallidas").

Causa raíz: `ejecutar_orden_mercado` (`src/broker/ibkr_adapter.py`)
decidía éxito/fracaso únicamente con `trade.orderStatus.status`. Ese
campo puede estar mal — no es un caso aislado del Error 10349, sino
una categoría más amplia de divergencia entre lo que `ib_async`
reporta y lo que IBKR ejecutó de verdad. El código original lanzaba
`OrdenNoLlenada` (y por tanto el motor registraba la orden como
fallida y NO la contabilizaba) sin verificar nunca si la orden,
pese al status, sí había cambiado la cuenta real.

## Decisión

`ejecutar_orden_mercado` ya no decide "no se llenó" solo con el
status. Orden de verificación, de más a menos confiable:

1. `trade.orderStatus.status == "Filled"` → éxito inmediato (caso
   normal).
2. Si no, revisa `trade.fills` — las ejecuciones reales que manda
   IBKR llegan ahí independientemente de si el campo de status quedó
   mal reportado. Si hay fills, se usa el precio promedio ponderado
   real de esas ejecuciones.
3. Si tampoco hay fills, como última verificación compara las
   posiciones reales de la cuenta (`posiciones_reales`) antes y
   después de mandar la orden. Si la cuenta cambió exactamente lo
   esperado, se trata como llenada — usando el precio de mercado
   actual (`reqTickers`) como aproximación, ya que no hay un precio
   de ejecución real reportado del que echar mano.
4. Solo si ninguna de las tres verificaciones confirma la ejecución,
   se lanza `OrdenNoLlenada` de verdad.

Nueva función `posiciones_reales_con_costo(ib)`: igual que
`posiciones_reales` pero devuelve también `avgCost` por símbolo
(ponderado si hay varios lotes) — necesaria para reconciliar P&L real
cuando el estado local y la cuenta real divergen, como pasó aquí.
Expuesta vía `GET /live/posiciones-reales` (solo lectura) para poder
diagnosticar divergencias sin pedir comandos manuales en la VM.

## Pendiente

- Reconciliar `data/paper_trading_live/state.json` contra las 11
  posiciones reales encontradas — el estado local sigue creyendo que
  no hay posiciones abiertas. Se hará en un cambio separado una vez
  confirmado el costo real de cada posición vía
  `/live/posiciones-reales`.
- No se investigó la causa exacta por la que `ib_async` reportó mal
  el status estas 11 veces (más allá del Error 10349 ya resuelto) —
  el fix de este ADR es defensivo (verificar la realidad en vez de
  arreglar por qué miente la librería), no una explicación completa
  del bug subyacente de `ib_async`.
