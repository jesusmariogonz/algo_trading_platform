# EXP-003 — Capa 3: DSR + PBO sobre el espacio de búsqueda histórico

## ⚠ Hallazgo crítico, previo al resultado de esta capa: el harness compartido NO incluye el filtro de ADR 0034 en `largo_plazo`

Antes de reportar DSR/PBO, un hallazgo que afecta la validez de
**todas** las capas anteriores de EXP-003 para `largo_plazo`
específicamente (Capas 1, 4, 5, 6, 7 — no afecta `mediano_plazo` ni
`riesgo_alto`):

`research/2026-11-filtros-sizing-adr0033/harness.py` (`signaled_universe()`)
genera la señal de `largo_plazo` llamando directo a
`time_series_momentum.generate_signals` — **sin** el filtro de
cross-sectional momentum que ADR 0034 puso en producción real.
Confirmado leyendo el código fuente actual de
`src/paper_trading/engine.py`:

```python
CROSS_SECTIONAL_FILTER_BUCKETS = {"largo_plazo"}
CROSS_SECTIONAL_PERCENTIL_MIN = 0.70
```

Este filtro exige, además de la señal propia de la estrategia,
`return_126d > 0 AND percentil ≥ 0.70` dentro del universo — y está
**activo en producción hoy**, para el motor simulado y el motor en
vivo de IBKR. ADR 0034 reporta su propio walk-forward: Sharpe OOS
prom. **2.25** (vs. 1.33 del baseline sin filtro), retorno +19.14%,
drawdown 6.99%, 0/5 ventanas negativas — un perfil sustancialmente
mejor que el Sharpe 0.78 que todas las capas de EXP-003 han usado
hasta ahora como "baseline de producción" de `largo_plazo`.

**Consecuencia concreta**: los labels REJECTED/INCONCLUSIVE de
`largo_plazo` en Capas 1, 4, 7 (y los números de Capa 6) corresponden
a una versión de la estrategia que YA NO es exactamente la que corre
en producción — son válidos como caracterización de
`time_series_momentum` puro, pero no representan la configuración
completa vigente hoy. Esta capa reporta el DSR de `largo_plazo` con
**ambos** números (0.78 sin filtro, 2.25 con filtro real) en vez de
elegir uno solo — ver resultado abajo. No se corrigieron las capas
anteriores en este commit (está fuera del alcance de esta tarea
puntual); se documenta aquí como hallazgo a resolver antes de
considerar cerrado el veredicto de `largo_plazo` en EXP-003.

## Paso 1 — Catálogo de variantes (N=47)

Código: `capa3_dsr_pbo.py` (catálogo completo con `id`/ADR de
origen/descripción en `CATALOGO_VARIANTES`, auditable línea por
línea). Leídos los 43 ADR del repo (`docs/adr/0001` a `0043`);
contadas solo las configuraciones con un Sharpe o retorno comparable
reportado contra un control, sin repetir la misma variante descrita
en más de un ADR.

| Grupo | ADR | # variantes | Resumen |
|---|---|---|---|
| A | 0004/0006 | 4 | Bucket cripto + 3 esquemas de reparto de capital sin cripto |
| B | 0007 | 3 | Trailing stop (general + excepción cripto) + cash-en-SPY |
| C | 0010 | 4 | 2 ampliaciones de universo + 2 candidatos descartados (ATR 3.0x, filtro de régimen) |
| D | 0011 | 1 | Riesgo Alto a 45 símbolos + fricción real |
| E | 0012 | 3 | Riesgo 2%/2%/3%+equity actual + 2 cash-holders descartados (SPY/AGG, SGOV) |
| F | 0013 | 2 | Semis/defensa descartado + 100% GLD (superseded) |
| G | 0016 | 1 | Largo Plazo a 26 ETFs (universo de producción actual) |
| H | 0018 | 2 | Donchian Breakout + Risk Parity, ambos descartados |
| I | 0019/0026/0027 | 5 | Mean Reversion RSI(2) aislado + 4 pesos de asignación (15/25/35/50%) |
| J | 0025 | 10 | Barrido de 10 estrategias nuevas, todas descartadas |
| K | 0033 | 10 | Las 10 hipótesis de filtros de sizing/entrada |
| L | 0040 | 1 | Swap estrategia×universo (`trend_following`×riesgo_alto) nuevo, no probado antes de EXP-003 |
| **Total** | | **47** | |

El código valida `assert len(CATALOGO_VARIANTES) == 47` — si alguien
edita la lista sin actualizar el conteo, el script falla ruidosamente
en vez de desincronizarse en silencio.

## Paso 2 — Deflated Sharpe Ratio

Fórmula de Bailey & López de Prado (2014), misma derivación del
appendix de EXP-002 (constante de Euler-Mascheroni, teoría de valores
extremos para el máximo esperado de N trials). `sigma_SR` (dispersión
de Sharpe entre trials) se estima empíricamente de los 18 valores de
Sharpe REALMENTE reportados en el catálogo (no se inventa — de los 47
trials, solo 18 tienen un Sharpe explícito en su ADR de origen; el
resto solo reporta retorno/drawdown sin Sharpe):

```
muestra = [0.67, 2.04, 1.52, 1.31, 0.87, 1.96, 0.71, 0.42, 0.28, 0.28,
           -0.04, 2.00, 2.25, 1.75, 0.42, 1.33, 0.96, 1.49]
sigma_SR = 0.7101
```

`sigma_SR_hat` (error estándar del Sharpe de cada bucket) usa T=1052
observaciones diarias y la asimetría/curtosis real de cada serie de
retornos — calculado corriendo el mismo harness de producción sin
filtros, igual que las capas anteriores.

| Bucket | Sharpe usado | T | skew | kurt. exceso | SR₀ (máximo esperado por azar, N=47) | z | **DSR** |
|---|---|---|---|---|---|---|---|
| largo_plazo (harness, SIN filtro ADR 0034) | 0.78 | 1052 | -0.218 | 1.482 | 1.5995 | -20.44 | **0.0000** |
| **largo_plazo (producción REAL, CON filtro ADR 0034)** | **2.25** | 1052* | -0.218* | 1.482* | 1.5995 | **8.68** | **1.0000** |
| mediano_plazo | 1.39 | 1052 | 0.867 | 5.499 | 1.5995 | -3.75 | **0.0001** |
| riesgo_alto | 0.92 | 1052 | 3.133 | 27.553 | 1.5995 | -10.68 | **0.0000** |

\* T/skew/kurtosis del Sharpe "con filtro" son una aproximación (se
usa la serie sin filtro porque este harness no reproduce el filtro de
ADR 0034) — declarado explícitamente, no se tiene la serie de
retornos exacta de la configuración real con filtro.

**Lectura directa**: con 47 intentos documentados y una dispersión de
Sharpe de 0.71 entre ellos, el máximo que se esperaría conseguir por
puro azar es Sharpe≈1.60. `mediano_plazo` (1.39) y `riesgo_alto`
(0.92) quedan claramente por debajo de ese techo — su Sharpe no es
estadísticamente distinguible de "el mejor resultado que cualquier
sistema sin ninguna habilidad real produciría con 47 intentos".
`largo_plazo` SIN el filtro de ADR 0034 (0.78) también queda muy por
debajo; CON el filtro (2.25, el número real de producción), supera
holgadamente ese techo.

## Paso 3 — PBO (Combinatorially Symmetric Cross-Validation)

Código: `capa3_pbo.py`. Variantes re-simulables disponibles con
Sharpe por ventana: las 3 de ADR 0040 (`baseline`, `trend_efficiency`,
`correlation_adjusted`), ya producidas y auto-verificadas en esa
investigación — reusadas tal cual, sin volver a correr el backtest.
20 particiones evaluadas por bucket (las C(5,2)=10 formas de elegir 2
ventanas in-sample + las C(5,3)=10 formas de elegir 3), midiendo si el
ganador in-sample cae en la mitad inferior por Sharpe promedio
out-of-sample.

| Bucket | Variantes comparadas | Particiones | **PBO** |
|---|---|---|---|
| largo_plazo | baseline / trend_efficiency / correlation_adjusted | 20 | **0.00** |
| mediano_plazo | baseline / trend_efficiency / correlation_adjusted | 20 | **0.00** |
| riesgo_alto | baseline / trend_efficiency / correlation_adjusted | 20 | **0.15** |

Los 3 buckets quedan muy por debajo del umbral de 0.5 — dentro de
este conjunto específico de 3 variantes, el que gana in-sample
también tiende a ganar out-of-sample. **Importante no sobre-leer
esto**: PBO aquí solo cubre 3 de las 47 variantes del catálogo (las
únicas con datos ventana-por-ventana re-simulables disponibles) — un
PBO bajo en esta comparación acotada no contradice un DSR bajo sobre
las 47, son preguntas distintas (¿es la variante ganadora un
artefacto DENTRO de este grupo chico de 3? vs. ¿es el resultado
distinguible de 47 intentos de azar en total?).

## Label por bucket (criterio: VALIDATED si DSR>0.95 Y PBO<0.5; INCONCLUSIVE si DSR 0.5-0.95 o PBO no calculable; REJECTED si DSR≤0.5)

| Bucket | DSR | PBO | **Label** |
|---|---|---|---|
| largo_plazo (harness, consistente con Capas 1/4/5/6/7) | 0.0000 | 0.00 | **REJECTED** |
| largo_plazo (con el Sharpe real de producción, ADR 0034) | 1.0000 | 0.00 | **VALIDATED** |
| mediano_plazo | 0.0001 | 0.00 | **REJECTED** |
| riesgo_alto | 0.0000 | 0.15 | **REJECTED** |

**`largo_plazo` queda en dos labels contradictorios según qué Sharpe
se use — esto no se resuelve en esta capa, queda explícitamente
abierto** (ver sección inicial). `mediano_plazo` y `riesgo_alto`
quedan REJECTED sin ambigüedad bajo cualquier lectura: 47 intentos
documentados en la historia de este proyecto son suficientes para que
el Sharpe observado de ambos no distinga de la mejor racha que ese
volumen de búsqueda produciría sin ninguna habilidad real.

## Consistencia con las capas anteriores

- `mediano_plazo` y `riesgo_alto` REJECTED aquí es consistente con la
  Capa 4 (placebo, también REJECTED en los 3 buckets) — dos pruebas
  independientes, con metodologías completamente distintas, señalando
  el mismo problema para estos 2 buckets.
- `largo_plazo` (harness, sin filtro) REJECTED aquí también coincide
  con el REJECTED de la Capa 4 para ese mismo número — pero esta capa
  es la primera en exponer que ese número puede no ser el correcto.

## Veredicto de esta capa (no de EXP-003 completo)

**mediano_plazo: REJECTED. riesgo_alto: REJECTED. largo_plazo:
AMBIGUO — depende de si se usa el Sharpe del harness (REJECTED) o el
Sharpe real de producción con el filtro de ADR 0034 (VALIDATED).**
Antes de considerar cerrado el veredicto de `largo_plazo` en EXP-003
hace falta decidir: o se extiende el harness para incluir el filtro
de ADR 0034 y se re-corren las Capas 1, 4, 6, 7 con la configuración
real completa, o se acepta documentar esta capa como la única con el
número real y las demás como caracterización de la estrategia
base sin el filtro.
