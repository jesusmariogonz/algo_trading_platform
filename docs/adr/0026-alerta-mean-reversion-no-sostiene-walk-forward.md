# ADR 0026 — ALERTA ABIERTA: Mean Reversion RSI(2) no sostiene walk-forward rolling

## Estado: ALERTA ABIERTA, sin resolver. No se tomó acción sobre producción todavía.

## Contexto

Tras descartar Bollinger %B en el barrido exploratorio (ADR 0025) por
no sobrevivir walk-forward rolling, el usuario preguntó explícitamente
si la aprobación de Mean Reversion RSI(2) como 4to bucket (ADR 0019)
había pasado por el mismo nivel de escrutinio. No había pasado: ADR
0019 se aprobó con un backtest de muestra completa (36 meses,
+47.90% aislado, correlación 0.142) y una tabla de sensibilidad de
peso calculada también sobre esa misma muestra completa — exactamente
el tipo de evidencia sin validar fuera de muestra que acababa de
tumbar a Bollinger.

Se auditó Mean Reversion RSI(2) con la misma metodología aplicada a
Bollinger %B (walk-forward rolling, 5 ventanas de 6 meses OOS cada
una, paso de 4 meses). Nota metodológica: esta estrategia no tiene
hiperparámetros ajustables en producción (RSI(2)<10/>70, sma_5, ATR
2.0x son fijos por diseño) — el walk-forward aquí mide consistencia
temporal pura, no hubo grid search que hacer.

## Hallazgos

### Walk-forward rolling (5 ventanas)

| Ventana | OOS | Sharpe OOS | Retorno OOS |
|---|---|---|---|
| 1 | nov-2024 a may-2025 | 0.45 | +2.36% |
| 2 | mar-2025 a sep-2025 | 0.44 | +2.28% |
| 3 | jul-2025 a ene-2026 | **-1.54** | **-9.22%** |
| 4 | nov-2025 a may-2026 | 0.46 | +1.97% |
| 5 | mar-2026 a sep-2026 | 0.03 | -0.04% |

Sharpe OOS promedio: **-0.032**. Desviación estándar: 0.771. 2 de 5
ventanas con pérdida.

### Sensibilidad de peso (promediada sobre las 5 ventanas)

| Peso | Sharpe promedio |
|---|---|
| 0% (control puro) | **1.443 (máximo)** |
| 35% (asignación real en producción hoy) | 1.170 |
| 65% | 0.660 |

**Monotónicamente decreciente** — ningún peso mayor a 0% mejoró el
portafolio en esta validación. Agregar Mean Reversion RSI(2) diluyó
el Sharpe del control en vez de ayudarlo.

### Comparación directa contra Bollinger %B (ADR 0025, ya descartado)

| | Mean Reversion RSI(2) | Bollinger %B |
|---|---|---|
| Sharpe OOS promedio | **-0.032** | 1.076 |
| Ventanas con pérdida | 2/5 | 2/5 |
| Peor ventana | -9.22% | -7.41% |
| ¿Algún peso ayuda? | No, nunca | Sí, hasta 35-50% |

**Mean Reversion RSI(2) salió peor que la estrategia que se acaba de
rechazar.**

### Dato agravante

En la ventana 3 (-9.22%), el portafolio de control combinado ganó
+11.9% en el mismo periodo — la estrategia falló activamente justo
cuando el resto del sistema iba bien, el peor momento posible para
algo que se supone aporta diversificación.

### Discrepancia sin resolver: +47.90% (ADR 0019) vs. +19.09% (reproducción directa)

Al replicar el backtest de muestra completa original (mismo código,
mismo universo de 119 símbolos, mismos 36 meses), el resultado fue
**+19.09% / Sharpe 0.67 / 157 operaciones** — no el +47.90% que
documenta ADR 0019. No se investigó la causa todavía (bandera
levantada, no resuelta en esta auditoría) — posibles explicaciones:
revisiones retroactivas de datos de yfinance (mismo tipo de problema
que causó ADR 0020), una diferencia metodológica no documentada entre
cómo se corrió el backtest original y esta reproducción, o un error
en uno de los dos cálculos. **Investigación de esta discrepancia en
curso, ver seguimiento más abajo cuando se resuelva.**

## Impacto real

Mean Reversion RSI(2) está corriendo HOY con dinero (paper) real, con
35% del capital, en DOS sistemas: el motor simulado
(`src/paper_trading/engine.py`) y el motor en vivo contra IBKR
(`src/paper_trading/live_engine.py`, ADR 0023).

## Decisión tomada en este ADR

Por ahora: **ninguna acción sobre producción** — ni se reduce el peso,
ni se pausa el bucket, ni se cambia `allocation.py`. Decisión explícita
del usuario: primero investigar la causa de la discrepancia
+47.90%/+19.09% antes de decidir qué hacer con la asignación real.
Esta alerta queda documentada y abierta mientras tanto.

## Lección para el futuro

El mismo patrón se repitió dos veces en una sesión: una estrategia se
ve espectacular en un backtest de muestra completa y se aprueba (o
casi se aprueba) sin walk-forward rolling. A partir de ahora, ningún
candidato futuro debería pasar a fase de aprobación/asignación de
capital sin walk-forward rolling de al menos 5 ventanas — un
backtest de muestra completa, por bueno que se vea, no es evidencia
suficiente por sí solo.
