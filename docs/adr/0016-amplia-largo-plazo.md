# ADR 0016 — Amplía el universo de Largo Plazo de 13 a 26 ETFs

## Estado
Aceptado.

## Contexto
La validación oficial (ADR 0015) mostró a Largo Plazo como el bucket
más débil (+8.40% en 36 meses) pese a ser el que más capital recibe
(43.33%). Se diagnosticó, igual que en ADR 0010/0011 para los otros
buckets, que el problema no era la estrategia ni el monto asignado —
era un universo demasiado chico (13 ETFs) para que Time-Series
Momentum encontrara suficientes señales.

## Decisión
Se amplía `config/universe_largo_plazo.txt` de 13 a 26 ETFs, agregando
diversidad real (no solo más de lo mismo):

- **Internacional**: EEM (emergentes), EWJ (Japón), FXI (China)
- **Renta fija de distintos plazos/tipos**: SHY (corto plazo), LQD
  (corporativo grado de inversión), HYG (alto rendimiento), MUB
  (municipal), EMB (deuda emergente)
- **Commodities**: DBC (canasta amplia), SLV (plata), USO (petróleo)
- **Bienes raíces internacionales**: VNQI
- **Small/mid-cap internacional**: SCZ

## Resultado medido (36 meses, datos congelados, configuración de
producción: riesgo 2%/2%/3%, equity actual, cash blend 50% SPY/50% GLD,
fricción real)

| | Antes (13 ETFs) | Después (26 ETFs) |
|---|---|---|
| Largo Plazo | +8.40% (40 operaciones) | **+15.17%** (53 operaciones) |
| Total del sistema | +31.07% | **+34.00%** |
| Drawdown máximo del sistema | 13.83% | **12.91%** |

El retorno de Largo Plazo casi se duplicó, y a diferencia de otros
cambios probados en este proyecto, esta vez el drawdown total del
sistema también **bajó** — no es un trade-off de más riesgo por más
retorno, es más diversificación real dentro de un bucket que ya era,
por diseño, el más conservador.

**Esta corrida reemplaza a ADR 0015 como la cifra oficial de referencia
del proyecto.**

## Qué NO se tocó
- El % de capital de Largo Plazo (43.33%) no cambió — se descartó la
  opción de diluirlo, porque el diagnóstico mostró que el problema era
  el universo chico, no el monto asignado.
- Ningún criterio de entrada de Time-Series Momentum se relajó.
- Mediano Plazo y Riesgo Alto sin cambios.

## Pendiente
- Validar con más historial de paper trading real.
