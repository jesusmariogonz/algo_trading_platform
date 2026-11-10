# ADR 0038 — Riesgo por operación de Riesgo Alto: 3% → 5%

## Contexto

Con ~$215 de equity (simulado) el riesgo por operación al 3% era ~$6.46.
Las acciones de este bucket son volátiles: la distancia al stop (precio de
entrada menos stop por ATR) fue de $7.62 a $34.91 por acción entre el 30-oct
y el 9-nov-2026. Ninguna cabía en el presupuesto, así que el dimensionamiento
daba 0 acciones y el motor descartaba todas las señales: Riesgo Alto nunca
abrió una posición propia (todo su capital quedó en el blend de cash ocioso).

## Decisión

`riesgo_alto.risk_pct` pasa de 0.03 a 0.05 en `BUCKET_CONFIG`
(`src/screening/daily_signals.py`). Es la misma configuración para el motor
simulado y para el motor en vivo, así que ambos cambian a la vez. Con $215
el presupuesto sube a ~$10.77: habilita DOCU y XYZ (1 acción cada una).

No cambian los circuit breakers (pérdida diaria 2%, drawdown de revisión 15%),
ni las estrategias ni el universo.

## Consecuencias

- Cada operación pierde más si toca su stop (hasta 5% del equity del bucket
  en vez de 3%).
- Sigue sin garantizar operaciones: solo se abre si hay señal y cabe al menos
  1 acción. Con bucket tan chico la mayoría de las señales (CRWD, SHOP, W,
  ETSY) seguirán sin caber.
- No se validó con un backtest walk-forward: es una decisión del usuario para
  que el bucket opere. Cualquier comparación de retornos de Riesgo Alto antes
  y después de este cambio mezcla dos niveles de riesgo.
