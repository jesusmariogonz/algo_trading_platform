# EXP-003 — Capa 2: Sesgo de supervivencia

Código: `capa2_sesgo_supervivencia.py`. Última de las 7 capas de
EXP-003. Mismo motor de simulación que las capas anteriores
(`harness.simulate_bucket`, capital compartido, sizing por riesgo
sobre equity actual, fricción real).

## Método

`docs/roadmap.md` ya advertía esto sin resolverlo: "corrido sobre
nuestros 30 símbolos actuales que incluyen NVDA, SMCI, AVGO, PLTR —
elegidos a mano porque HOY sabemos que fueron ganadores del rally de
IA 2023-2025". Un proveedor de datos point-in-time (constituyentes
históricos exactos de hace 3-5 años) no es viable gratis/rápido en
este entorno — en vez de eso, se construyó un **universo neutral**:
una muestra estratificada (cada 3er símbolo, orden alfabético — 168 de
503) de los constituyentes ACTUALES del S&P 500 (fuente pública:
`github.com/datasets/s-and-p-500-companies`, confirmado accesible
desde este entorno).

**Qué tipo de sesgo SÍ mide esto, y cuál NO**: esta comparación no
elimina el sesgo de supervivencia completo (los 503 miembros son los
de HOY, no los de hace 5 años — una empresa que quebró o salió del
índice en ese período no aparece en ninguno de los dos universos). Lo
que SÍ elimina es el sesgo de **selección manual con hindsight**:
elegir 26-79 nombres específicos porque ya se sabe que ganaron, en vez
de tomar un corte objetivo de un índice amplio. Es la pregunta más
relevante y la más barata de responder con los datos disponibles — se
documenta la distinción explícitamente, no se presenta como una
medición completa de supervivencia.

**Autoverificación**: el universo curado reproduce exacto lo ya
publicado — mediano_plazo Sharpe 1.39/retorno 209.36%, riesgo_alto
Sharpe 0.91/retorno 165.28%. El harness está siendo reusado
correctamente.

## Alcance: 2 de 3 buckets

Solo `mediano_plazo` (`trend_following`) y `riesgo_alto`
(`momentum_breakout`) — son los 2 universos de ACCIONES INDIVIDUALES
donde aplica el tipo de sesgo que `roadmap.md` documentó. `largo_plazo`
es un universo de ETFs de CLASE DE ACTIVO (SPY=equity, AGG=bonos,
GLD=oro, VNQ=REIT...) — "elegir qué ETF representa cada clase de
activo" no es el mismo fenómeno que "elegir qué acción individual ya
sabemos que ganó". Construir un universo neutral de ETFs (ej. todos
los SPDR sectoriales) testearía una pregunta distinta (concentración
sectorial), ya cubierta por la Capa 5 — forzar esa comparación aquí
sería de bajo valor informativo. Se documenta como limitación
explícita.

## Resultado

| Bucket | Universo curado | Universo neutral (S&P 500, 168 símbolos) | Diferencia | Label |
|---|---|---|---|---|
| mediano_plazo | 74 símbolos, retorno anual **30.92%** | 165 símbolos, retorno anual **30.65%** | 0.9% | **VALIDATED** |
| riesgo_alto | 44 símbolos, retorno anual **26.21%** | 165 símbolos, retorno anual **11.57%** | **55.9%** | **REJECTED** |
| largo_plazo | — | — | No aplica (ver "Alcance" arriba) | **INCONCLUSIVE** (razón documentada, no por falta de esfuerzo) |

Detalle completo (Sharpe, drawdown, trades) en `resultados_capa2.json`.

### mediano_plazo — sesgo bajo

El universo curado de `mediano_plazo` (large/mid-cap diversificado:
AAPL, MSFT, JPM, XOM, etc.) y una muestra neutral del S&P 500 dan
retornos anualizados casi idénticos (30.92% vs. 30.65%). Tiene
sentido: ese universo ya se parece bastante a "un corte representativo
de empresas grandes conocidas", no a una lista de ganadores
específicos de un rally reciente.

### riesgo_alto — sesgo material, confirma la advertencia de roadmap.md

El universo curado (PLTR, SMCI, COIN, RIVN, SOFI...) rinde **más del
doble** por año que una muestra neutral del S&P 500 corrida con la
MISMA estrategia (`momentum_breakout`): 26.21% vs. 11.57% anual. Esto
confirma cuantitativamente, por primera vez, la advertencia que
`roadmap.md` dejó sin resolver desde Fase 0: una parte sustancial del
rendimiento reportado de `riesgo_alto` depende de que el universo esté
compuesto por nombres que YA se sabe que fueron ganadores del rally de
IA/growth 2023-2025, no de que la estrategia tenga una ventaja
sistemática replicable sobre cualquier universo similar.

**Limitación honesta en la dirección opuesta**: el S&P 500 es un índice
de EMPRESAS GRANDES Y ESTABLECIDAS — `riesgo_alto` está diseñado para
operar small/mid-cap de alta volatilidad, un universo estructuralmente
más parecido a PLTR/SMCI/RIVN que a AAPL/JPM. Esto significa que la
comparación de arriba probablemente **subestima** el sesgo real: un
universo neutral de small/mid-cap de alta volatilidad (en vez de
large-cap establecido) tendría más oportunidades de generar señales de
momentum extremas por azar, no menos — el 55.9% de diferencia medido
aquí es, si algo, un piso, no un techo.

### largo_plazo — INCONCLUSIVE, por diseño

No se intentó una comparación de bajo valor informativo. Ver
"Alcance" arriba para la razón completa.

## Veredicto de esta capa (no de EXP-003 completo — esta síntesis la
hace el coordinador con las 7 capas visibles)

**mediano_plazo: VALIDATED. riesgo_alto: REJECTED — el número de
producción de ese bucket debe tratarse como cota superior, no
estimador puntual: una parte material de su rendimiento histórico
reportado depende de la selección manual con hindsight del universo,
no solo de la estrategia. largo_plazo: INCONCLUSIVE** (el tipo de
sesgo medido aquí no aplica de la misma forma a un universo de ETFs de
clase de activo).
