# ADR 0025 — Barrido exploratorio de 11+ estrategias nuevas: se descarta Bollinger %B, ningún 5to candidato listo

## Contexto

Tras aprobar Mean Reversion RSI(2) como 4to bucket (ADR 0019), se pidió
un barrido exploratorio amplio para ver si existía un 5to candidato
razonable: catálogo curado de ~9 familias de estrategias no presentes
en el sistema (breakout de volatilidad, pairs trading, estacionalidad,
señal de volumen, reversión a la media con Bollinger %B, momentum
cross-sectional, filtro de régimen alternativo con ADX, dual momentum)
más 3 experimentales (ensemble de señales, position sizing por
volatility targeting, un modelo de ML ligero), todas aisladas con
capital propio sobre los mismos 36 meses de datos reales congelados
usados en ADR 0018/0019.

Todo el código del barrido vive sin comitear en `exploracion_2026_11/`
del repo (no se subió a git — es exploración pura, no parte del
historial de producción).

## Resultado del barrido inicial (muestra completa, sin validación)

| Estrategia | Retorno 36mo | Drawdown máx | Sharpe | Correlación con control |
|---|---|---|---|---|
| Reversión a la media (Bollinger %B) | +104.87% | 11.87% | 2.04 | 0.362 |
| Breakout + filtro ADX | +78.67% | 15.91% | 1.52 | 0.472 |
| Señal de volumen (OBV) | +73.24% | 16.01% | 1.31 | 0.548 |
| Breakout de volatilidad (squeeze) | +31.46% | 14.73% | 0.87 | 0.349 |
| ML (Gradient Boosting) | +29.25% | 7.25% | 1.96 | 0.412 |
| Volatility targeting (sizing sobre trend_following) | +27.78% | 15.27% | 0.71 | 0.701 |
| Rotación cross-sectional / Dual momentum | +20.99% | 24.78% | 0.42 | 0.627 |
| Ensemble (2 de 3 señales coinciden) | +8.88% | 16.83% | 0.28 | 0.640 |
| Pairs trading (V/MA) | +2.61% | 3.39% | 0.28 | -0.051 |
| Estacionalidad fin de mes | -0.63% | 4.27% | -0.04 | 0.133 |

Bollinger %B destacó como único candidato con retorno Y Sharpe mejores
que todo lo demás, con correlación relativamente baja (0.362) —
patrón superficialmente similar al que validó Mean Reversion RSI(2).

## Por qué se descartó: no sobrevivió la validación fuera de muestra

El modelo de ML mostró la señal de alerta clásica de inmediato
(accuracy 71.4% en entrenamiento -> 53.2% fuera de muestra,
esencialmente azar) y se descartó sin más análisis. Bollinger %B
parecía distinto — no colapsó igual de rápido — así que se le aplicó
la misma barra de evidencia que a Mean Reversion RSI(2) en su momento:
no solo un backtest aislado, sino walk-forward y sensibilidad de peso.

**Walk-forward con 2 splits fijos** (60/40 y 80/20): Sharpe cayó de
~2.2-2.5 en muestra a 0.75-1.87 fuera de muestra — degradación real
pero sin colapso. Los parámetros óptimos encontrados coincidían con
los defaults usados en el barrido original (no hubo que forzar nada
exótico). Con solo esta evidencia, parecía razonable seguir evaluando.

**Walk-forward ROLLING con 5 ventanas** (12 meses entrenamiento / 6
meses prueba, paso de 4 meses) — la prueba decisiva, y la que expuso
el problema real:

| Ventana | OOS | Sharpe OOS | Retorno OOS |
|---|---|---|---|
| 1 | nov-2024 a may-2025 | **-0.81** | **-7.41%** |
| 2 | mar-2025 a sep-2025 | 2.58 | +22.66% |
| 3 | jul-2025 a ene-2026 | 2.98 | +20.41% |
| 4 | nov-2025 a may-2026 | **-0.92** | **-6.12%** |
| 5 | mar-2026 a sep-2026 | 1.55 | +11.03% |

**2 de 5 ventanas (40%) perdieron dinero fuera de muestra**, con
Sharpe negativo. Los 2 splits probados antes casualmente cayeron en
periodos favorables (ventanas equivalentes a la 2-3-5 de esta tabla),
por eso no habían expuesto el problema. Sharpe promedio 1.076,
desviación estándar 1.652 — casi tan grande como el promedio mismo.

Sensibilidad de peso promediada sobre las 5 ventanas: sí aparece un
pico en 35% (coincide con el óptimo de Mean Reversion RSI(2)), pero la
mejora de Sharpe al subir de 0% a 35% es de solo +11%, mientras la
variabilidad entre ventanas casi se duplica (std 1.045 -> 1.424) — el
beneficio promedio es pequeño y el riesgo de caer en una ventana mala
crece más rápido que la mejora.

## Decisión

**No se abre un 5to bucket con Bollinger %B.** Comparado contra la
barra real de este proyecto (Mean Reversion RSI(2), ADR 0019):
correlación más alta (0.362 vs. 0.142 — menos valor de
diversificación), y sobre todo, inconsistencia temporal real que RSI(2)
nunca mostró en su validación. El +104.87% del barrido inicial fue
mayormente producto de capturar 2-3 ventanas favorables dentro de los
36 meses, no un edge estructural confiable.

Ninguna otra estrategia del catálogo llegó siquiera a la etapa de
walk-forward — todas quedaron por debajo de Bollinger %B en la
primera pasada, así que no se invirtió tiempo en validar algo con un
resultado inicial ya peor.

## Condición para reconsiderar Bollinger %B en el futuro

Repetir la validación walk-forward ROLLING (no splits fijos) con
resultados consistentemente positivos en la mayoría de las ventanas
(hoy: 3 de 5) — no basta con que el promedio se vea bien si 2 de cada
5 periodos reales pierden dinero.

## Lección para el futuro

Un walk-forward de 1-2 splits fijos puede dar una falsa sensación de
robustez si, por azar, ambos caen en periodos favorables — el walk-
forward ROLLING con varias ventanas es el que realmente expone
inconsistencia temporal. Vale la pena aplicarlo como estándar antes de
promover cualquier candidato futuro a Fase 2 (sensibilidad de peso),
no solo después.
