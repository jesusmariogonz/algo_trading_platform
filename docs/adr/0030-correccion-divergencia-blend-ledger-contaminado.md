# ADR 0030 — Corrección de divergencia: ledger de blend contaminado con datos de prueba

## Contexto

Al fijar el capital del motor en vivo a $2,000 USD (ADR 0029), el
estado devuelto mostró `blend_spy_shares`/`blend_gld_shares` en 0 para
los 3 buckets, pero `/live/reconciliar` mostró 1 acción de GLD REAL en
la cuenta IBKR. Se confirmó con el usuario (Client Portal de IBKR):
**solo existe 1 posición real, GLD, comprada a $376.12** — ninguna
posición de SPY. Matemáticamente consistente: de los 3 buckets
($866.67 / $666.67 / $466.67), solo `largo_plazo` tenía suficiente
capital (mitad ≈ $433) para comprar 1 acción de GLD a ~$376; los otros
dos no alcanzaban ni para eso. SPY (~$700+) no alcanzó en ningún
bucket.

Al inspeccionar `data/paper_trading_live/blend_ledger.json` vía el
nuevo endpoint `/live/blend-ledger` (agregado para este diagnóstico),
apareció contaminado: ~36 renglones duplicados de compras de SPY y
GLD, todos a exactamente **$101.00** — un precio que SPY y GLD nunca
han tenido. Es la misma clase de contaminación ya documentada en ADR
0028 (un archivo de prueba real había aparecido antes por pruebas
manuales sin mockear del todo `live_engine`/`trading_api`). El archivo
nunca refleja realmente la compra de GLD a $376.12 que sí ocurrió.

## Decisión

Dos endpoints nuevos, de uso puntual (no rutina automática):

- `POST /admin/live/limpiar-blend-ledger`: vacía
  `blend_ledger.json` a `[]`. Se usó una vez para descartar los ~36
  renglones contaminados — no se intentó reconstruir el historial
  real perdido (no hay forma confiable de hacerlo), se empieza limpio
  desde ahora.
- `POST /admin/live/fijar-estado-bucket?bucket=...&cash=...&blend_spy_shares=...&blend_gld_shares=...`:
  corrige a mano `cash`/acciones de blend de un bucket que ya existe
  en `state.json`, sin tocar `starting_capital` ni posiciones
  abiertas. Se niega si el bucket tiene `open_positions` (protección
  contra corromper más el estado mientras hay una posición real a
  medio camino).

Se usó una vez para corregir `largo_plazo`: `cash` de $866.67 a
$490.55 (= 866.67 − 376.12, el costo real de la GLD comprada),
`blend_gld_shares` de 0 a 1. `mediano_plazo` y `riesgo_alto` no se
tocaron — su cash real ($666.67 y $466.67) ya coincidía con la
realidad (no compraron nada).

## Causa raíz, sin resolver del todo

No se identificó con certeza CÓMO se contaminó el archivo esta vez —
la hipótesis más probable sigue siendo pruebas manuales anteriores
(vía Bash en la VM) que usaron las rutas de archivo reales en vez de
un mock/tmp_path completo, igual que la vez anterior documentada en
ADR 0028. No se tomó acción adicional de hardening (ej. forzar que
`LIVE_BLEND_LEDGER_PATH` solo pueda escribirse desde dentro de
`trading-api.service`) — queda como posible mejora futura si se
repite.
