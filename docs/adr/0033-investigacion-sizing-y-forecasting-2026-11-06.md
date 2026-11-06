# ADR 0033 — Investigación de filtros de sizing y forecasting probabilístico (2026-11-06)

## Contexto

Tras un research externo (compartido por el usuario, basado en
literatura real: Daniel & Moskowitz sobre momentum crashes
predecibles, Moreira/Muir sobre volatility-managed portfolios, Gu
Kelly & Xiu sobre modelos no lineales en predicción cross-sectional)
se probaron 10 hipótesis de "capa superior" sobre las 3 estrategias
activas en producción (ADR 0027): `time_series_momentum`
(largo_plazo), `trend_following` + `momentum_breakout`
(mediano_plazo/riesgo_alto). Ninguna cambia la señal de entrada/salida
existente — todas operan sobre el TAMAÑO de la posición o sobre si
una señal ya generada se ejecuta o no.

Metodología en todos los casos: walk-forward rolling, 5 ventanas (12
meses train / 6 meses test, paso 4 meses), ~36 meses de historia,
código en `exploracion_2026_11/` (gitignored, nunca se commitea —
este ADR es el registro persistente, el código en sí puede
perderse si el contenedor de una sesión termina). **Nada de esto se
implementó en producción** — es investigación pura.

## Resultado por hipótesis

| # | Hipótesis | Mecánica | Resultado |
|---|---|---|---|
| 1 | Vol-regime sizing | Multiplicador 0.25-1.00x según tendencia SPY + percentil de volatilidad | Neutro en largo_plazo; en mediano_plazo baja varianza pero parte el retorno a la mitad; empeora riesgo_alto. **Descartada.** |
| 2 | Correlation-adjusted sizing | Penaliza tamaño si el candidato correlaciona (60d) con lo ya abierto en el bucket | Mejora largo_plazo (Sharpe 1.33→2.00, std más bajo de todas: 0.96, retorno 8.91%→12.80%, DD 8.76%→6.19%) y riesgo_alto. Empeora mediano_plazo. **Candidata.** |
| 3 | Cross-sectional momentum | Exige momentum absoluto>0 Y percentil≥70 de retorno relativo del universo | Mejora fuerte largo_plazo (Sharpe 1.33→2.25, retorno 8.91%→19.14%, DD 8.76%→6.99%), pero descarta 67.5% de señales. Ambiguo en mediano_plazo, empeora riesgo_alto. **Candidata.** |
| 4 | Market breadth | Multiplicador de tamaño: menos % del universo con señal simultánea = más tamaño | Mejora largo_plazo (Sharpe 1.33→1.63, retorno 13.48%). Sin relación en mediano_plazo, sin datos suficientes en riesgo_alto. |
| 5 | Trend efficiency ratio (Kaufman) | Multiplicador según qué tan "suave" vs. errático es el movimiento reciente | Mejora fuerte mediano_plazo/trend_following (Sharpe 0.96→1.75) y largo_plazo (modesto). Rompe riesgo_alto/momentum_breakout (Sharpe 1.49→0.42, 3/5 ventanas negativas). |
| 6 | Momentum acceleration | M3 vs. mitad de M6 | Señal débil/invertida a 60-120 días. **Descartada**, no se construyó filtro. |
| 7 | Residual momentum | Retorno del activo menos lo explicado por su beta a SPY | Mejora largo_plazo (Sharpe 1.33→1.79). Empeora mediano_plazo y riesgo_alto. |
| 8 | Proximidad a máximo 52 semanas | Distancia al máximo de 252 días | Resultado opuesto al esperado — lejos del máximo rinde mejor (reversión, no continuación). **Descartada.** |
| 9 | Lead/lag entre señales | ¿Señal de un "líder" predice señal de un "seguidor"? | Parecía fuerte, pero era correlación contemporánea disfrazada (XLK compuesto ~35-40% por AAPL+MSFT+NVDA, señales autocorrelacionadas en el tiempo). **Descartada**, confirma el riesgo de overfitting que ya advertía el research. |
| 10 | Meta-modelo ML (trade-level) | Regresión logística, 7 features, P(trade ganador) | Overfitting confirmado numéricamente: AUC in-sample 0.93, AUC OOS 0.25 (peor que azar). Solo 51 trades históricos en largo_plazo, insuficiente para 7 variables. Sharpe cae de 2.28 a 1.12 en trading real. **Descartada.** |

## Combinar los filtros ganadores (#2, #3, #4, #5, #7)

Se solapan 78% entre sí (correlación de Pearson 0.05-0.36 entre
ellos) — miden variantes de la misma idea ("esta señal es de más
calidad"). Combinarlos empeora progresivamente el retorno cuantos
más se apilan: los 5 juntos dan el drawdown más bajo (2.67%) y cero
ventanas perdedoras, pero descartan 77% de las señales y el retorno
cae a 4.24% — demasiado restrictivo para ser práctico. **Ninguna
combinación superó al mejor filtro individual.**

## Pieza acotada de forecasting probabilístico (propuesta externa más grande)

El usuario compartió una segunda propuesta: Forecast Engine en
paralelo al Signal Engine, con quantile forecasting, predicción de
régimen, ensemble de 5 modelos, "Alpha Score". Antes de construir
esa arquitectura completa se probó una sola pieza: regresión
cuantílica (P10/P25/P50/P75/P90) de retorno a 20 días, a nivel
símbolo/día (15,000-45,000 observaciones por universo — muchos más
datos que el meta-modelo de trades), con las mismas variables de las
hipótesis #2-#7.

**Resultado: no calibra.** El intervalo "80%" solo cubrió 70-73% en
promedio (hasta 47% en la peor ventana de 5); el intervalo "50%"
estuvo mal calibrado en las 15 ventanas evaluadas sin excepción
(~44% real). El P50 ni siquiera superó la predicción ingenua
(promedio histórico) en pinball loss, en ninguno de los 3 universos.
A diferencia del meta-modelo de trades, aquí el problema no es
cantidad de datos — es que las variables disponibles no explican lo
suficiente del retorno futuro a 20 días. **No se recomienda
construir la arquitectura más grande sobre esta base.**

## Decisión pendiente — candidatos finales para `largo_plazo`

Solo dos, ninguno combinado, ninguno implementado todavía:

| Candidato | Sharpe OOS prom (std) | Retorno % | Drawdown % | Ventanas negativas | Frecuencia de trading |
|---|---|---|---|---|---|
| Baseline (producción actual) | 1.33 (1.56) | +8.91 | 8.76 | 1/5 | Normal |
| **#3 Cross-sectional momentum** | **2.25** (1.43) | **+19.14** | 6.99 | 0/5 | ~3x menos (descarta 67.5% de señales) |
| #2 Correlation-adjusted sizing | 2.00 (**0.96**) | +12.80 | **6.19** | 0/5 | Normal (nunca descarta, solo achica tamaño) |

**Por los criterios de mayor retorno + drawdown bajo + rendimiento
positivo consistente, Cross-sectional momentum (#3) gana en 2 de 3
ejes** (retorno más que duplicado vs. baseline, cero ventanas
negativas) y pierde solo marginalmente en drawdown (6.99% vs. 6.19%
de #2, diferencia de 0.8 puntos). Correlation-adjusted sizing (#2)
gana en consistencia pura (menor varianza del Sharpe entre ventanas:
0.96 vs 1.43) y mantiene el ritmo normal de operaciones, mientras que
#3 opera ~3 veces menos seguido al descartar dos de cada tres
señales.

**Trade-off real a decidir** (no implementado, pendiente de que el
usuario decida): #3 para maximizar retorno ajustado a riesgo; #2 si
se prefiere un cambio menos invasivo que no reduzca la frecuencia de
trading y priorice la consistencia entre periodos sobre el retorno
pico.
