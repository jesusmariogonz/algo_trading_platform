# ADR 0039 — "benchmark_diversificado": 4ª canasta de comparación (solo motor simulado)

## Contexto

El usuario propuso EXP-003 (en `pulso-research-lab`): una validación estadística
rigurosa de las 3 canastas en vivo (walk-forward, DSR sobre todo el espacio
explorado, PBO, placebo, stress de costos) antes de confiar en el motor para
dinero real. Mientras esa validación corre (semanas, no días), el usuario pidió
un punto de comparación simple y diversificado, arrancando limpio desde hoy,
para saber honestamente si el motor activo le está ganando a algo mucho más
simple — no solo mirar el +34% de un backtest viejo (ADR 0016) que ya no
corresponde a la configuración actual (predata el filtro cross-sectional de
ADR 0034, el riesgo al 5% de ADR 0038, y Mean Reversion que se probó y se
revirtió — ver ADR 0019/0026/0027).

Se decidió explícitamente **no** tocar el motor en vivo (el que corre contra
IBKR real-paper, `live_engine.py`): ese motor deliberadamente NO invierte el
cash ocioso en ningún blend (ADR 0023, "sin inversión de cash ocioso en
benchmark") para no generar órdenes reales solo por "estacionar" dinero.
Agregar ahí una canasta de comprar-y-mantener exigiría mandar órdenes reales
(aunque sea cuenta paper) para comprar los 4 activos una sola vez, y el usuario
pidió explícitamente empezar por el motor simulado local, sin tocar IBKR ni la
VM en vivo.

## Decisión

Nueva canasta `benchmark_diversificado`, **solo en el motor simulado local**
(`src/paper_trading/engine.py` + `run_daily_tick()`, estado en
`data/paper_trading/`), con:

- **Composición**: 40% SPY (acciones) / 30% AGG (bonos) / 20% GLD (oro) / 10%
  VNQ (REIT) — `BENCHMARK_DIVERSIFICADO_WEIGHTS` en `engine.py`.
- **Sin estrategia**: `BUCKET_CONFIG["benchmark_diversificado"]` tiene
  `strategies = []` y `risk_pct = 0.0` — nunca abre ni cierra una posición
  propia. El 100% de su capital se invierte desde el día 1 en el blend de los
  4 activos y se queda ahí para siempre (comprar y mantener real, sin
  rebalanceo periódico — se decidió no rebalancear para no introducir un
  parámetro de diseño adicional a algo que debe ser lo más simple posible).
- **Mecanismo reusado, no reinventado**: el blend se calcula con
  `_blend_incremental_price`, la MISMA función ya probada en producción para
  el cash ocioso de las otras 3 canastas (blend SPY/GLD, ADR 0007/0014/0020) —
  generalizada para aceptar un diccionario de pesos por parámetro en vez de
  usar siempre el global `BLEND_WEIGHTS`. Hereda gratis la protección contra
  revisiones retroactivas de precios de yfinance (ADR 0020).
- **Capital inicial**: $1,683.23 — el equity real total de las 3 canastas del
  motor EN VIVO (IBKR paper) al 2026-11-13 ($512.27 + $703.27 + $467.69), para
  que la comparación sea "la misma cantidad de dinero, invertida de dos formas
  distintas", no un número arbitrario. No está ligado al libro de inyecciones
  de `allocation.py` (ese libro reparte capital entre las 3 canastas con
  estrategia; esta es un punto de comparación aparte, con su propio capital
  fijo, ver `BENCHMARK_DIVERSIFICADO_STARTING_CAPITAL`).
- **Circuit breakers presentes pero inofensivos**: límites de pérdida
  diaria/drawdown puestos deliberadamente en 100% (nunca se disparan) solo
  para que `daily_loss_pct`/`drawdown_pct` se calculen y se puedan comparar
  en el dashboard, no para bloquear nada (no hay nada que bloquear: nunca
  abre posiciones).
- Universo nuevo `config/universe_benchmark_diversificado.txt` con un único
  símbolo (SPY) — sirve solo para anclar la fecha de "hoy" en el motor; la
  composición real del blend no depende de ese archivo.

## Consecuencias

- No modifica ninguna de las 3 canastas existentes ni sus reglas, pesos,
  riesgo o universos — es puramente aditivo.
- No toca `live_engine.py` ni manda ninguna orden real a IBKR (ni siquiera de
  cuenta paper). No aparece todavía en el dashboard de jgonzalez.app (ese
  dashboard muestra el motor EN VIVO, no el simulado local) — si más adelante
  se quiere ahí, es una decisión y un trabajo aparte (requeriría órdenes
  reales vía el adapter de IBKR y desplegar el código a la VM).
- Requiere datos descargados de AGG y VNQ (antes no estaban en ningún universo
  del proyecto) — agregados a la descarga vía
  `python -m src.data.download --universe <archivo con SPY/AGG/GLD/VNQ>`.
- `_blend_incremental_price` ahora recibe los pesos por parámetro (con
  default `BLEND_WEIGHTS` para no romper las 3 canastas existentes ni
  `live_engine.py`, que importa `BLEND_WEIGHTS` directo) — cambio de firma
  retrocompatible, confirmado por la suite completa (232/232 tests, incluidos
  los 16 de `test_blend_bucket.py`/`test_blend_ledger.py` ya existentes).
- Esta canasta es deliberadamente la más simple posible (sin rebalanceo, sin
  parámetros que ajustar) — es un benchmark, no otra estrategia a optimizar.
- Bug encontrado y corregido de paso: `blend_ledger.registrar()` tenía
  `simbolo="BLEND_SPY_GLD"` escrito a mano en los 3 sitios donde se registra
  una compra/venta del blend, en vez de leer el símbolo real del bucket
  (`BENCHMARK_SYMBOL.get(bucket)`). Antes de esta canasta no importaba
  (las 3 canastas existentes usan ese mismo blend), pero con
  `benchmark_diversificado` el ledger hubiera quedado mal etiquetado
  (diciendo "BLEND_SPY_GLD" cuando en realidad es "BLEND_DIVERSIFICADO") —
  corregido para que el ledger sea una bitácora de auditoría confiable.
