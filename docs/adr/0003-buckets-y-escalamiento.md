# ADR 0003 — Definición de los 4 buckets y regla de escalamiento

## Estado
Aceptado para la definición de buckets. **Pendiente de implementación
real** la regla de escalamiento (requiere datos que este proyecto
todavía no tiene — ver "Consecuencias").

## Contexto
El usuario definió un reparto de capital en 4 buckets por horizonte/
riesgo (ver `src/portfolio/allocation.py`): 40% largo plazo, 30%
mediano plazo, 20% riesgo alto, 10% muy alta volatilidad. Pidió
además una condición para escalar el bucket de riesgo alto.

## Decisión — definición de cada bucket

| Bucket | % | Instrumentos | Estrategia | Riesgo por operación |
|---|---|---|---|---|
| Largo plazo | 40% | ETFs amplios | Buy & hold, sin señales activas | N/A |
| Mediano plazo | 30% | Acciones/ETFs líquidos de EE.UU. (`config/universe.txt`) | Trend Following + Momentum/Breakout | 1% (regla base del master prompt) |
| Riesgo alto | 20% | Acciones small/mid-cap de alta volatilidad, **sin criptomonedas** (`config/universe_riesgo_alto.txt`) | Mismas estrategias (Trend Following + Momentum/Breakout) | **2%** — deliberadamente más laxo que Mediano Plazo, decisión explícita del usuario de asumir más riesgo por operación, no solo instrumentos más volátiles |
| Muy alta volatilidad | 10% | Criptomonedas | Sin construir todavía | N/A |

## Decisión — regla de escalamiento de Riesgo Alto

Cuando el **rendimiento acumulado anualizado del portafolio total**
(los 4 buckets juntos, valuado en vivo) alcance **≥10% anual**, se
autoriza una **inyección adicional de capital al bucket de Riesgo
Alto** (monto a decidir por el usuario en ese momento — esta regla no
fija un monto automático).

## Consecuencias — por qué esto NO se implementa como un trigger automático todavía

Evaluar "rendimiento acumulado del portafolio total" requiere **valor
de mercado en vivo de posiciones reales**: cuánto vale hoy cada
posición abierta, comparado contra el capital inyectado. Este
proyecto, en Fase 0, no tiene:

- Ejecución real ni siquiera en PAPER (Fase 6, pendiente)
- Valuación de portafolio reconciliada contra el broker (Fase 1+5)
- Una fuente de verdad del P&L más allá de backtests históricos

Fabricar ese número ahora con datos de backtest sería presentar una
simulación como si fuera rendimiento real — exactamente lo que el
master prompt prohíbe explícitamente ("no inventes resultados de
backtesting ni señales de mercado").

Lo que SÍ queda listo en este incremento:

- `src/portfolio/allocation.py` acepta inyecciones de capital
  dirigidas a un bucket específico (ya existente desde su diseño
  original) — cuando se cumpla la condición, la inyección extra a
  `riesgo_alto` se registra con el mismo mecanismo, sin cambios de
  código.
- Esta regla queda documentada formalmente aquí para no perderla,
  y como criterio explícito a verificar manualmente (revisando tus
  propios estados de cuenta) hasta que exista Portfolio Management
  real.

## Pendiente
Implementar el cálculo automático del rendimiento total en cuanto
exista Fase 6 (paper trading) con reconciliación — ver
`docs/roadmap.md`. El bucket de criptomonedas (Muy Alta Volatilidad)
requiere su propio ADR cuando se diseñe su ingesta de datos (API
distinta a yfinance, calendario 24/7, sin splits/dividendos).
