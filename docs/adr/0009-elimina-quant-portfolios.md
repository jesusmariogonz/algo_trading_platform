# ADR 0009 — Elimina los Quant Portfolios

## Estado
Aceptado. Revierte la decisión de ADR 0005 (coexistencia explícita de
dos modelos) — el usuario decidió no seguir manteniendo los Quant
Portfolios una vez que el modelo de buckets recibió sus propias
mejoras (ver ADR 0006, 0007, 0008).

## Contexto
ADR 0005 construyó los 3 Quant Portfolios (Conservative Alpha /
Balanced Growth / Aggressive Momentum) para coexistir con el modelo de
4 (luego 3) buckets por horizonte, con la intención explícita de
"correr ambos modelos en paralelo durante la ventana de paper trading
y comparar cuál conviene seguir" (ver roadmap). Esa comparación nunca
llegó a completarse — el usuario pidió directamente eliminar los
Quant Portfolios una vez que el modelo de buckets quedó con trailing
stop, cash-en-benchmark y circuit breakers reales (mismas mejoras que
los Quant Portfolios ya tenían, ahora también en buckets).

## Decisión
Se elimina por completo:

- `src/quant_portfolios/` (módulo entero: definitions.py, engine.py,
  trend_filters.py, reauthorize.py, run_daily_tick.py, export.py).
- `tests/test_quant_portfolios_engine.py`,
  `tests/test_quant_portfolios_trend_filters.py`.
- `data/quant_portfolios/{state,history}.json`.
- `config/universe_quant_portfolios.txt` (universo exclusivo de este
  modelo — SGOV, VOO, BND, VXUS, GLDM, QQQM, SMH; IWM y BTC se siguen
  usando en otros universos, no se tocan).
- En jesus-site: `app/trading/portafolios/` (índice + detalle),
  `app/api/quant-portfolios/route.js`, `lib/quant-portfolios-snapshot.json`,
  y el link desde `/trading` hacia `/trading/portafolios`.
- Los pasos de Quant Portfolios en las 2 Routines diarias
  (`run_daily_tick`/`export` de ese módulo).

## Qué NO se elimina
- **ADR 0005** se mantiene como registro histórico de por qué y cómo
  se construyeron — no se borra documentación de decisiones pasadas,
  solo se marca como superseded por este ADR.
- BTC sigue descargándose (`src/data/download_crypto.py`) porque no
  depende de Quant Portfolios — es infraestructura de datos genérica,
  sin consumidor activo por ahora, sin costo de mantenerla.
- El capital que tenían los Quant Portfolios nunca fue capital real
  (eran productos 100% simulados, nunca conectados a Alpaca) — no hay
  reconciliación de dinero real que hacer al eliminarlos.

## Pendiente
- Ninguno — esta decisión cierra la rama de comparación "buckets vs.
  quant portfolios" que quedaba pendiente en el roadmap, al eliminar
  uno de los dos lados de la comparación.
