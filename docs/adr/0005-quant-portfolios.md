# ADR 0005 — Quant Portfolios: 3 productos con identidad propia

## Estado
Aceptado. **Coexiste a propósito** con el modelo de 4 buckets por
horizonte (`src/portfolio/allocation.py`, `src/paper_trading/`) —
decisión explícita del usuario de comparar ambos enfoques en paralelo,
no una migración.

## Contexto
El usuario propuso rediseñar el reparto de capital no como "4 buckets
por horizonte de inversión" sino como "3 productos cuantitativos con
identidad de riesgo propia" (Conservative Alpha / Balanced Growth /
Aggressive Momentum), inspirado en cómo una plataforma de inversión
real empaquetaría sus ofertas. Cada uno con su propio universo, motor
algorítmico, reglas de rebalanceo, límites de riesgo y benchmark.

## Decisión — arquitectura

Vive en `src/quant_portfolios/`, completamente separado del motor de
buckets (`src/paper_trading/`):

- `definitions.py`: los 3 portafolios, con sus pesos, filtro de
  tendencia, frecuencia de rebalanceo y parámetros de riesgo —
  preservados tal cual los propuso el usuario (pesos y objetivos de
  volatilidad son HIPÓTESIS DE DISEÑO, no resultado de optimización).
- `trend_filters.py`: 3 funciones, una por portafolio — deciden si un
  activo recibe su peso objetivo completo o uno "defensivo" (una
  fracción menor, nunca cero) en el próximo rebalanceo.
- `engine.py`: rebalanceo a pesos objetivo + circuit breakers reales.

## Decisión — simplificación declarada de las estrategias

No se construyeron 3 motores de trading completamente literales a
las reglas académicas originales (eso habría sido mucho más trabajo
sin evidencia de que valga la pena). En su lugar, cada portafolio usa
una adaptación razonable:

- **Conservative Alpha**: SMA 200 + momentum de 6 meses. Si un activo
  pierde la condición, su peso baja a 50% del objetivo (no a 0% —
  "reduce exposición", no "liquida").
- **Balanced Growth**: cruce SMA 50/200 + momentum combinado de 3, 6
  y 12 meses (promedio simple). Peso defensivo: 40%.
- **Aggressive Momentum**: ruptura Donchian de 20 sesiones (mismo
  concepto que `momentum_breakout.py`) + confirmación EMA 20>50.
  Revisión DIARIA (no mensual, como pidió el usuario para este
  portafolio). Peso defensivo: 20% (el más agresivo en reducir
  cuando no hay tendencia).

Esto NO es pyramiding de Turtle Trading real, ni rebalanceo activo
de posiciones individuales — es "¿este activo recibe su peso
objetivo completo o reducido en el próximo rebalanceo?". Simplificación
declarada, no oculta.

## Decisión — Risk Engine real (no solo sugerencias)

A diferencia del modelo de buckets (donde el "1% de riesgo" es una
sugerencia de tamaño de posición), aquí se implementaron 2 circuit
breakers que de verdad bloquean:

1. **Pérdida diaria máxima**: si el equity cae más del límite diario
   (0.25%/0.40%/0.60%... en realidad son los límites de PÉRDIDA
   DIARIA 1%/1.5%/2% — no confundir con riesgo por operación) desde
   el inicio del día, se bloquean nuevas compras por el resto del
   día. Se resetea automáticamente al día siguiente.
2. **Drawdown de revisión**: si el equity cae más del límite de
   drawdown (6%/10%/15%) desde su máximo histórico, el portafolio
   queda **suspendido** — no solo por hoy, sino hasta reautorización
   manual (`src/quant_portfolios/reauthorize.py`). Regla textual del
   usuario: "revisa posiciones y exige autorización para reactivarse.
   No significa liquidar automáticamente toda la cartera" — por eso
   la suspensión NUNCA vende nada, solo bloquea aumentar exposición.

## Decisión — instrumentos nuevos

SGOV, VOO, BND, VXUS, GLDM, QQQM, SMH — ninguno estaba en el universo
anterior. Se descargan vía yfinance igual que el resto (no requirió
una fuente de datos nueva). IWM y BTC se reusan de los universos ya
existentes.

## Decisión — capital

Los 3 portafolios parten del mismo $1,000 de referencia del proyecto,
repartido en partes iguales (~$333 cada uno) — siguiendo la propia
recomendación del usuario (sección 6 de su propuesta): "usaría los
tres portafolios como modelos alternativos... probaría cada modelo
con el mismo capital virtual... después seleccionaría el que
demuestre mejor comportamiento fuera de muestra."

## Pendiente

- Ejecución real contra Alpaca: el usuario decidió explícitamente que
  por ahora son productos simulados, no conectados a una cuenta real
  — ver conversación. Cuando exista Execution Engine (Fase 6+), se
  conecta encima de este mismo motor sin rediseñarlo.
- Catálogo dinámico de Alpaca (tradable/fractionable/shortable) — no
  aplica todavía, solo relevante al conectar ejecución real.
- El circuit breaker de pérdida diaria usa los % que el usuario llamó
  "riesgo por operación" en su tabla pero que, por definición
  (pérdida acumulada del DÍA, no de una operación), se implementaron
  como límite de pérdida diaria — los valores que el usuario puso
  bajo "riesgo por operación" (0.25%/0.40%/0.60%) se usaron para
  `risk_per_trade_pct` (guardado en el snapshot, no aplicado todavía
  a ningún sizing de operación individual porque este motor no abre
  posiciones por señal individual sino por peso objetivo — queda
  documentado para cuando se necesite).
