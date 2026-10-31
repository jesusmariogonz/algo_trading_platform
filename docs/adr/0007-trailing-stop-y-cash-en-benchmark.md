# ADR 0007 — Trailing stop + cash ocioso invertido en benchmark

## Estado
Aceptado. Aplica a los 3 buckets del modelo (ver ADR 0006) — reemplaza
el comportamiento original de `src/paper_trading/engine.py` (stop fijo
en el precio de entrada, cash ocioso sin invertir).

## Contexto
El ejercicio exploratorio de simular el modelo con capital real (ver
ADR 0006) mostró un problema concreto: en 6 meses de datos reales
(may-oct 2026), el modelo original dio -0.08% mientras SPY comprar-y-
mantener dio +6.76% en el mismo período. El diagnóstico, con datos:
muy pocas operaciones por mes (riesgo acotado a 1-2% por operación) y
el capital sin posición se quedaba en cash puro, sin generar nada,
la mayoría del tiempo.

Se probaron dos cambios, comparando backtests reales contra el modelo
original en 3 ventanas (6, 22 y 34 meses):

## Decisión 1 — Trailing stop
El stop ya no se fija en el precio de entrada y se queda ahí. Cada día
se recalcula con la MISMA fórmula que ya usa cada estrategia para todo
el historial (`close - multiplicador_ATR * ATR_14`, ver
`src/strategies/*.py`) y el guardado solo sube si el nuevo cálculo es
más alto — nunca baja. Deja correr ganadores (ej. SOFI cerró en v1 con
señal de salida en -4.11%/+2.16% según el período; con trailing stop,
la misma posición corrió hasta +38.97% en la ventana de 22 meses)
sin aumentar el riesgo ya asumido al entrar.

**Excepción probada y descartada**: en el bucket de cripto (ya
eliminado, ver ADR 0006) el trailing stop no ayudó — la volatilidad
diaria alta sacaba posiciones por ruido normal, no por reversión real
(-12.11% vs -12.95%, prácticamente neutro). Como el bucket se eliminó
por otras razones, esto quedó sin efecto práctico, pero se documenta
porque si se reintrodujera cripto algún día, el trailing stop ahí
necesitaría revisión aparte.

## Decisión 2 — Cash ocioso invertido en el benchmark del bucket
El efectivo que no está en ninguna posición abierta se invierte en
SPY (el benchmark de los 3 buckets de acciones) en vez de quedarse
parado. Se marca a mercado cada día (`bench_shares` en el estado); al
abrir una posición nueva se vende la porción de benchmark necesaria
para financiarla, y el producto de cerrar una posición se reinvierte
en el benchmark.

Este fue el cambio con mayor impacto medido, por una razón simple:
con pocas señales de entrada por mes, la mayoría del capital pasa la
mayoría del tiempo sin posición — "estacionado en cash" significaba
renunciar a casi todo el movimiento del mercado de fondo mientras se
esperaba. Resultado medido (ver ADR 0006 para la tabla completa):
+0.23% → +17.75% en 22 meses, +29.92% → sin cambio (ya incluido) en
34 meses tras aplicar ambos cambios.

## Decisión — alcance
Ambos cambios aplican a los 3 buckets de acciones restantes
(`largo_plazo`, `mediano_plazo`, `riesgo_alto`), todos con SPY como
benchmark (`BENCHMARK_SYMBOL` en `engine.py`). No aplica a los Quant
Portfolios (`src/quant_portfolios/`), que son un motor completamente
separado con su propia lógica de rebalanceo a pesos objetivo — ahí no
aplica el concepto de "cash ocioso esperando señal" de la misma forma.

## Qué NO cambia
- Las condiciones de ENTRADA de cada estrategia no se tocaron —
  mismas señales, mismos umbrales. Solo cambia qué pasa con el stop
  una vez dentro, y qué pasa con el capital sin posición.
- El % de riesgo por operación (1% largo/mediano plazo, 2% riesgo
  alto) no cambió.

## Pendiente
- Evaluar un filtro de régimen de mercado para decidir si estacionar
  cash en SPY tiene sentido o no (ej. no comprar el índice "a ciegas"
  si SPY mismo está en tendencia bajista confirmada) — en el período
  probado (predominantemente alcista) este mecanismo no tuvo que
  demostrar su comportamiento en un mercado bajista prolongado.
- Revisar si Riesgo Alto se beneficiaría de un multiplicador de ATR
  distinto para el trailing (hoy usa el mismo que la entrada original).
