# ADR 0012 — Aumenta el riesgo por operación + sizing sobre equity actual

## Estado
Aceptado, **con corrección de números el 1-nov-2026** (ver sección
"Corrección de reproducibilidad" al final) — la decisión de diseño se
mantiene, los números originales de esta sección NO son confiables y se
reemplazan más abajo.

## Contexto
Dos preguntas del usuario llevaron a probar dos cambios juntos, sobre 36
meses (nov 2023 - oct 2026), con el motor de producción real (fricción +
universo de 146 símbolos ya incluidos):

1. ¿Qué pasa si se sube el riesgo por operación?
2. ¿Conviene calcular ese riesgo sobre el capital inicial fijo del bucket,
   o sobre su equity actual (que crece o baja con el desempeño)?

## Decisión
Ambos cambios, combinados:

- **Riesgo por operación**: Largo Plazo y Mediano Plazo pasan de 1% a
  **2%**; Riesgo Alto pasa de 2% a **3%**.
- **Base de cálculo del riesgo**: ya no es `starting_capital` (fijo desde
  el día 1), es el **equity actual** del bucket al momento de cada señal
  de entrada — compone con ganancias y pérdidas acumuladas.

## Resultado medido (36 meses, con fricción real, universo de producción)

| | Antes (riesgo original, capital fijo) | Después (riesgo subido, equity actual) |
|---|---|---|
| Retorno neto | +37.21% | **+48.25%** |
| Drawdown máximo | 10.83% | **18.77%** |
| Operaciones cerradas | 336 | 218 (menos — posiciones más grandes "llenan" el cupo de capital disponible más rápido) |

El drawdown máximo casi se duplicó exactamente el mismo día (2025-04-08,
una caída real de SPY de -12% en 4 sesiones) en ambas configuraciones —
confirma que el riesgo subió proporcionalmente al retorno, no es una
mejora gratuita.

## Decisión del usuario, explícita
"Aguantaré el drawdown" — decisión consciente de apetito de riesgo, no
una recomendación por default de este proyecto. Se documenta aquí
precisamente para que quede registrado qué se sabía en el momento de
tomarla: +11 puntos de retorno a cambio de +8 puntos de peor drawdown
histórico medido.

## Qué se probó y se DESCARTÓ en la misma sesión (no va a producción)
Como parte del mismo análisis de drawdown, se probaron 2 alternativas para
reducir el drawdown vía dónde se invierte el cash ocioso (hoy: 100% SPY):

| Alternativa | Retorno | Drawdown máximo | Veredicto |
|---|---|---|---|
| SPY (actual, sin cambios) | +37.21% | 10.83% | Se mantiene |
| Blend 50% SPY / 50% AGG | +20.37% | 6.24% | Descartado — sacrifica demasiado retorno |
| SGOV (casi-cash, bonos del Tesoro de corto plazo) | **-8.37%** | 4.10% | Descartado — el sistema se vuelve perdedor neto |

**Hallazgo relevante**: el cash-en-SPY es, de hecho, el mayor motor de
retorno del sistema completo — quitarlo (SGOV) no solo bajó el riesgo,
hundió el resultado a negativo. Confirma lo medido en ADR 0007: gran
parte del retorno viene de estar expuesto al mercado casi todo el tiempo,
no solo de las señales de entrada/salida en sí.

También se descartó, por ser mecánicamente equivalente al "filtro de
régimen" ya probado en ADR 0010 (empeoró el resultado): un stop-loss
sobre la posición de cash-en-benchmark — ambos son variantes de "hacer
market timing sobre el cash", y ya hay evidencia real de que eso perjudica
el resultado en este universo y período.

## Qué NO se tocó
- Ningún criterio de entrada de las estrategias.
- El cash ocioso se queda 100% en SPY, sin cambios.
- Los circuit breakers (límites de pérdida diaria y drawdown) mantienen
  los mismos % — con equity actual creciendo, en dólares absolutos esos
  límites ahora representan más capital protegido, pero el % sigue igual.

## Pendiente
- Validar estos nuevos límites de riesgo con más historial de paper
  trading real, no solo backtest — la decisión se tomó con evidencia de
  36 meses hacia atrás, no es garantía hacia adelante.

## Corrección de reproducibilidad (1-nov-2026)

**Problema encontrado**: los números de la sección "Resultado medido"
arriba (+37.21%→+48.25%, 10.83%→18.77% drawdown) se calcularon mezclando
descargas de datos hechas en distintos momentos del día. `yfinance`
revisa los precios ajustados cada vez que se vuelve a pedir el mismo
período (ajustes de dividendos aplicados retroactivamente, y la barra
del día más reciente cambia según si el mercado ya cerró "en firme" al
momento de la descarga) — así que dos descargas del "mismo" período de
3 años, en momentos distintos, pueden diferir en símbolos y barras
puntuales, lo suficiente para voltear señales de entrada/salida que
estaban justo en el límite, y eso se propaga sobre 36 meses.

**Verificación**: se corrió la MISMA configuración (riesgo subido +
sizing sobre equity actual) con una descarga única y congelada (sin
volver a pedir datos entre corridas) — los números NO coincidieron con
los reportados originalmente arriba, confirmando el problema.

**Números reproducibles correctos** (misma descarga congelada, 36 meses,
fricción real, universo de 146 símbolos):

| | Riesgo original (1%/1%/2%, capital fijo) | Riesgo subido + equity actual (decisión de este ADR) |
|---|---|---|
| Retorno neto | +11.41% | **+22.07%** |
| Drawdown máximo | 7.44% | **13.63%** |
| Operaciones cerradas | 422 | 220 |

La dirección del hallazgo se mantiene igual (subir el riesgo + equity
actual sube tanto el retorno como el drawdown, proporcionalmente), pero
la **magnitud real es menor** de lo que se reportó originalmente — no es
+11 puntos de retorno por +8 de drawdown, es +10.66 puntos de retorno
por +6.19 de drawdown. La decisión del usuario ("aguantaré el drawdown")
se mantiene vigente con este número corregido, pero se documenta aquí
para que quede claro qué evidencia real respalda la decisión hoy.

**Causa raíz y mitigación para análisis futuros**: para cualquier
comparación de variantes (ej. "con esto" vs. "sin esto"), descargar los
datos UNA sola vez y correr todas las variantes de la comparación sin
volver a descargar nada entre ellas — es la única forma de que los
resultados sean comparables entre sí. El pipeline de producción diario
(Routines) no tiene este problema de raíz: siempre debe usar el dato
más reciente disponible, eso es correcto para operar en vivo; el
problema es específico de comparar variantes en sesiones de análisis
exploratorio separadas en el tiempo.
