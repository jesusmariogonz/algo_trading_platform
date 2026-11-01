# ADR 0018 — Se descartan Donchian Breakout y Risk Parity (vol. inversa)

## Contexto

Tras cerrar la configuración oficial en ADR 0016 (+34.00%/36mo,
drawdown 12.91%), se evaluó una lista externa de modelos candidatos
para diversificar el comportamiento del sistema más allá de la familia
momentum/trend-following que domina los 3 buckets actuales. Las dos
primeras prioridades de esa lista eran:

- **EXP-02 Donchian Channel Breakout** (Turtle Trading clásico):
  entrada por ruptura de máximo de 20 sesiones, salida por mínimo de
  10 sesiones o stop ATR — sin filtro de volumen ni fuerza relativa, a
  diferencia de Momentum Breakout que ya corre en el sistema.
- **EXP-04 Risk Parity / Volatility Targeting**: re-ponderación mensual
  de los 3 buckets por volatilidad inversa realizada (ventana 63d),
  en vez de la repartición fija 43.33/33.33/23.33.

Metodología: una sola descarga/carga congelada de datos (evita el bug
de reproducibilidad de ADR 0012/13), réplica exacta del control oficial
confirmada antes de medir cualquier variante (+34.00%/12.91% reproducido
exacto, 229 operaciones).

## Resultado

| Variante | Retorno 36mo | Drawdown máx | Operaciones |
|---|---|---|---|
| Control (oficial) | +34.00% | 12.91% | 229 |
| + Donchian Breakout | +18.47% | 11.37% | 264 |
| Risk Parity (vol. inversa) | +17.80% | 13.39% | 249 |

Ambas variantes empeoran el retorno de forma significativa sin una
mejora de drawdown que lo compense.

### Por qué falló Donchian

Se agregó como tercera estrategia en Mediano Plazo y Riesgo Alto (no
reemplazó nada, compite por el mismo símbolo vía `open_symbols`). El
problema no fue la calidad de la señal en sí: Donchian generó señales
de entrada con más frecuencia que Momentum Breakout y le ganó el cupo
del símbolo en la mayoría de los casos — en Riesgo Alto, Momentum
Breakout pasó de 6 operaciones (control) a solo 1, mientras Donchian
tomó 34. El resultado fue diluir la estrategia que ya funcionaba mejor
en el sistema, no sumar una fuente de retorno independiente.
Conclusión: agregar una estrategia adicional dentro del mismo pool de
símbolos sin una regla de prioridad/arbitraje entre señales no
diversifica — compite y generalmente pierde contra la señal más fuerte
ya existente.

### Por qué falló Risk Parity (y un bug real encontrado en el camino)

La primera corrida de este experimento dio un resultado absurdo
(+103,254% en 36 meses, equity de ~$7M desde $1,000) por un bug real
en la lógica de rebalanceo mensual: cuando un bucket con posiciones
abiertas pesaba más que su nuevo peso objetivo (ej. porque su
volatilidad subió y el algoritmo quiso reducirle asignación), el
código clipeaba su `bench_shares` objetivo a 0 sin redistribuir el
déficit — dejándole intacto TODO su valor en posiciones sin que
cediera nada al resto del pool. Esto inyectaba dinero de la nada cada
mes, compuesto 36 veces. Se corrigió conservando exactamente el pool
total de cash/bench en cada rebalanceo (ver
`exp_donchian_riskparity.py` en el scratchpad de la sesión, función de
rebalanceo con normalización por `scale = pool_total / desired_total`).

Con el fix, el resultado real: repartir capital por volatilidad inversa
sobre-asigna a Largo Plazo (su volatilidad realizada es la más baja de
los 3 buckets), que es precisamente el bucket más débil del sistema
(+15.17% en el control, el más bajo de los 3). El drawdown tampoco
mejoró (13.39% vs 12.91%, ligeramente peor). Conclusión: la hipótesis
de que "menor volatilidad por bucket = mejor candidato para más
capital" no se sostiene aquí porque la volatilidad baja de Largo Plazo
no viene de ser una estrategia más sólida, sino de operar con un
universo donde Time-Series Momentum genera señales con mucha menor
frecuencia — hay una diferencia entre "poca volatilidad" y "buena
relación riesgo/retorno" que esta heurística simple no distingue.

## Decisión

Se descartan ambos. Ningún cambio a producción. El sistema sigue en
+34.00%/36mo, drawdown 12.91% (ADR 0016), sin modificaciones.

## Lección para el futuro

Ambos intentos compartían un patrón: tratar de mejorar el sistema
añadiendo complejidad DENTRO de la misma familia de comportamiento
(momentum/trend, o una re-ponderación basada en métricas derivadas del
mismo comportamiento) en vez de agregar una fuente de retorno con
lógica de entrada genuinamente distinta. Los candidatos que quedan
pendientes en la lista original (Mean Reversion, con lógica de entrada
opuesta — comprar debilidad, no fortaleza) tienen en teoría menor
riesgo de "competir por el mismo cupo" porque no buscan los mismos
símbolos en los mismos momentos que las estrategias actuales.
