# ADR 0004 — Bucket Muy Alta Volatilidad (criptomonedas)

## Estado
Aceptado para la infraestructura de datos. **Resultado del backtest:
negativo — ver "Hallazgo" abajo.** No se recomienda confiar en estas
estrategias para cripto todavía.

## Contexto
El usuario definió este bucket (10% del capital) específicamente para
criptomonedas, sin usar las mismas estrategias "tal cual" era un
requisito — se asumió reutilizarlas por consistencia con el resto del
sistema, pero debía validarse.

## Decisión — fuente de datos
- **Binance (CCXT)**, la opción original del master prompt, está
  bloqueada desde este entorno (HTTP 451 — restricción geográfica).
- **CoinGecko** (gratuita) se probó: su API pública degrada la
  granularidad a velas de 4 días para historiales largos en el tier
  gratuito — inútil para indicadores diarios (SMA 200 necesita 200
  puntos diarios reales, no uno cada 4 días).
- **Kraken** (pública, sin API key) da hasta 720 velas diarias reales
  (open/high/low/close/volumen) por símbolo — la opción elegida.
  Limitación real: ~2 años de historia, no 5 como las acciones.

Universo: BTC, ETH, SOL, XRP, ADA, AVAX, DOT, LINK, LTC (`config/universe_cripto.txt`).
Cada vela diaria está anclada a medianoche UTC — se trata como "un
día de mercado" igual que una sesión bursátil, aunque cripto opere
24/7; no se modificó el resto del pipeline (indicadores, paper
trading siguen asumiendo una fila por día).

Benchmark de fuerza relativa: **BTC**, no SPY — comparar un altcoin
contra el mercado accionario no tiene sentido; la pregunta relevante
en cripto es "¿esto le está ganando a Bitcoin?". Requirió agregar
`--universe` a `relative_strength.py` para no sobrescribir la fuerza
relativa de las acciones (vs. SPY) al correr la de cripto (vs. BTC)
— bug real encontrado y corregido en el camino.

## Decisión — riesgo por operación
**2%, igual que Riesgo Alto — asumido, no confirmado por el usuario.**
No se definió un número distinto para cripto. Dado que cripto ya es
estructuralmente más volátil que las acciones de Riesgo Alto, podría
justificarse un % menor (ej. 1.5%) para el mismo nivel de riesgo
monetario real. Ajustable en `src/screening/daily_signals.py`
(`BUCKET_CONFIG["muy_alta_volatilidad"]["risk_pct"]`).

## Hallazgo — backtest negativo, no oculto

Corriendo Trend Following y Momentum/Breakout (sin ningún ajuste,
las mismas reglas que en acciones) sobre el universo cripto completo
(2024-11 a 2026-10):

| Estrategia | Resultado |
|---|---|
| Trend Following | BTC -46.9%, la mayoría de los demás negativos; solo DOT en 0% (sin operaciones) |
| Momentum/Breakout | Peor aún: SOL -54%, XRP -59%, DOT -67%; solo BTC en 0% (sin operaciones) |

Esto NO es necesariamente que "cripto no se puede tradear con estas
reglas" — es evidencia de que las reglas diseñadas para el
comportamiento de acciones (SMA 50/150/200, rupturas de 20/55
sesiones) no transfieren automáticamente a la dinámica de cripto en
este período, que incluyó una corrección importante. Posibles causas
a investigar, NO implementadas todavía: parámetros de ATR/stop
demasiado ajustados para la volatilidad real de cripto, el filtro de
volumen no es igual de informativo 24/7, o simplemente el período
analizado fue malo para seguimiento de tendencia en general.

## Decisión — qué hacer con esto

Se agrega el bucket a `BUCKET_CONFIG` y al motor de paper trading de
todas formas, a propósito: el paper trading sirve exactamente para
esto — confirmar con datos en vivo si el patrón negativo del backtest
se sostiene, sin arriesgar capital real. Si después de 3-4 semanas el
patrón se mantiene negativo, la conclusión correcta es ajustar o
abandonar estas estrategias para cripto, no forzarlas.

## Pendiente
- Validar si --risk_pct 2% es el número correcto para cripto (no 1.5%
  u otro).
- Investigar por qué el backtest es tan malo antes de confiar en
  cualquier resultado futuro de paper trading en este bucket.
- Evaluar si cripto necesita sus propios parámetros de estrategia
  (ej. ATR multiple distinto) en vez de reusar los de acciones tal cual.
