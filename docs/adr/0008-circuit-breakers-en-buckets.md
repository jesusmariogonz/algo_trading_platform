# ADR 0008 — Risk Engine real (circuit breakers) en los 3 buckets

## Estado
Aceptado. Cierra el pendiente que quedaba abierto en `docs/roadmap.md`
desde que se construyeron los Quant Portfolios: "integrar el Risk
Engine real (circuit breakers) al modelo de buckets también — hoy
solo lo tienen los Quant Portfolios."

## Contexto
Los Quant Portfolios (ver ADR 0005, hoy eliminados — ver ADR 0009)
tenían 2 circuit breakers reales (pérdida diaria, drawdown de
revisión) que de verdad bloqueaban operaciones, mientras el modelo de
buckets solo tenía el % de riesgo por operación como sugerencia de
tamaño de posición, sin ningún freno real ante una mala racha.

## Decisión
Se lleva la MISMA mecánica de `src/quant_portfolios/engine.py` a
`src/paper_trading/engine.py`, con límites crecientes según el riesgo
ya definido de cada bucket (1%/1%/2% riesgo por operación):

| Bucket | Pérdida diaria límite | Drawdown de revisión |
|---|---|---|
| Largo plazo | 1.0% | 6% |
| Mediano plazo | 1.5% | 10% |
| Riesgo alto | 2.0% | 15% |

Mecánica (idéntica en espíritu a los Quant Portfolios):

1. **Pérdida diaria**: al inicio de cada día nuevo se fija
   `day_start_equity` (equity con el que arrancó hoy). Si el equity
   de hoy cae más del límite desde ese punto, se bloquean NUEVAS
   entradas por el resto del día. Se resetea automáticamente al día
   siguiente. Los cierres (stop/señal de salida) nunca se bloquean —
   el breaker solo impide ABRIR más, nunca impide CERRAR.
2. **Drawdown de revisión**: si el equity cae más del límite desde su
   máximo histórico (`peak_equity`), el bucket queda SUSPENDIDO —no
   solo por hoy, sino hasta reautorización manual
   (`python -m src.paper_trading.reauthorize <bucket>`). Igual que en
   Quant Portfolios: **nunca liquida posiciones existentes**, solo
   bloquea aumentar exposición.

Implementación: el bloqueo se aplica vaciando la lista de estrategias
activas para ese tick (`strategies = []`) antes del paso de apertura
de posiciones — reutiliza el mismo bucle sin necesitar una rama
separada.

## Qué NO cambia
- Las condiciones de ENTRADA y el % de riesgo por operación de cada
  bucket no se tocaron.
- El trailing stop y el cash-en-benchmark (ADR 0007) siguen operando
  igual — los circuit breakers son una capa adicional, no un
  reemplazo.

## Pendiente
- Validar estos límites con más historial de paper trading real —
  hoy son una extrapolación razonable de los límites usados en Quant
  Portfolios, no un resultado de backtest específico para estos 3
  buckets con estos límites exactos.
