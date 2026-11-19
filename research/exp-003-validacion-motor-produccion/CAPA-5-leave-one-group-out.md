# EXP-003 — Capa 5: Cross-sectional leave-one-group-out

Código: `capa5_leave_one_group_out.py`. Mismo motor de simulación que
las Capas 1/6/7 (`simulate_bucket` del harness de ADR 0040 — capital
compartido, sizing por riesgo sobre equity actual, trailing stop,
fricción real), corrido sobre todo el período disponible, sin
ventanas. Universo completo construido UNA vez por bucket
(`harness.signaled_universe`, params de producción); cada variante
"sin grupo" es un subconjunto de ese mismo universo — nunca se
recalculan señales (`sma_200`/`atr_14`/`relative_strength_63` son
métricas por símbolo contra su propio historial o contra SPY, no
contra el resto del universo del bucket, así que quitar otros símbolos
no cambia la señal de los que quedan).

**Validación de la reconstrucción**: el universo completo reproduce
Sharpe 0.78/1.39/0.91 y retorno 45.96%/209.36%/165.28% para
largo_plazo/mediano_plazo/riesgo_alto — idéntico a lo ya reportado en
Capas 1/6/7.

## Cómo se agruparon los símbolos (criterio documentado)

- **largo_plazo** (universo de ETFs): por clase de activo —
  Equity EE.UU., Equity internacional, Bonos, REIT, Commodities. Es la
  unidad natural para este universo, no requiere clasificación
  adicional.
- **mediano_plazo / riesgo_alto** (universos de acciones individuales):
  `src/portfolio/asset_types.py` es demasiado grueso para esto (casi
  todo cae en "Stock" por default) — se construyó una clasificación
  sectorial GICS aproximada A MANO (documentada íntegra en el código
  fuente, `GRUPOS_MEDIANO_PLAZO`/`GRUPOS_RIESGO_ALTO`), agrupando cada
  ETF sectorial (ej. XLF) junto con las acciones de ese mismo sector,
  no como su propio grupo aparte. 10 grupos en mediano_plazo, 9 en
  riesgo_alto — varios grupos de riesgo_alto quedan con 1 solo símbolo
  (RIVN, CELH, LYFT) por no tener un par temático claro en este
  universo; se reportan igual, con la limitación explícita de que un
  grupo de 1 símbolo prueba concentración en ese nombre, no en un
  clúster correlacionado.

`ROKU` (riesgo_alto) no tiene señal calculada (mismo problema de datos
ya documentado en Capa 4: descarga corrupta/incompleta) — excluido
automáticamente por `signaled_universe`, sin intervención manual.

## Resultado por bucket

### largo_plazo (5 grupos)

| Grupo quitado | Símbolos | Sharpe | Caída vs. baseline (0.78) |
|---|---|---|---|
| US_Equity | 7 | 0.98 | -25.6% (mejora) |
| Intl_Equity | 7 | 0.84 | -7.7% (mejora) |
| Bonds | 7 | 0.78 | 0.0% |
| REIT_US | 1 | 0.78 | 0.0% |
| **Commodities** | 4 | 0.77 | **1.3%** (peor caída) |

**Label: VALIDATED.** Ningún grupo individual produce una caída de
Sharpe mayor al 40% — la mayor caída real es 1.3%, y varios grupos
directamente mejoran el Sharpe al quitarse (lo que indica que ese
grupo diluía, no sostenía, el resultado).

### mediano_plazo (10 grupos)

| Grupo quitado | Símbolos | Sharpe | Caída vs. baseline (1.39) |
|---|---|---|---|
| Broad_Market_ETF | 2 | 1.63 | -17.3% (mejora) |
| Technology | 14 | 1.19 | 14.4% |
| Communication_Services | 6 | 1.45 | -4.3% (mejora) |
| Consumer_Discretionary | 8 | 1.88 | -35.3% (mejora) |
| Consumer_Staples | 6 | 1.32 | 5.0% |
| Financials | 11 | 1.34 | 3.6% |
| Energy | 3 | 1.21 | 12.9% |
| Healthcare | 9 | 1.73 | -24.5% (mejora) |
| Industrials | 12 | 1.33 | 4.3% |
| **Utilities** | 3 | 0.97 | **30.2%** (peor caída) |

**Label: VALIDATED.** La caída más fuerte (Utilities, 30.2%) queda por
debajo del umbral de 40% — aunque es la más cercana al límite de las 3
buckets, no lo cruza. Ningún grupo vuelve el Sharpe negativo.

### riesgo_alto (9 grupos)

| Grupo quitado | Símbolos | Sharpe | Caída vs. baseline (0.91) |
|---|---|---|---|
| Fintech_Crypto | 8 | 1.09 | -19.8% (mejora) |
| Enterprise_Software_Security | 12 | 1.14 | -25.3% (mejora) |
| Ecommerce_Marketplace | 9 | 1.22 | -34.1% (mejora) |
| Consumer_Internet_Media | 6 | 0.92 | -1.1% (mejora) |
| **Hardware_Semis** | 3 | 0.75 | **17.6%** (peor caída) |
| Gaming_Betting_Leisure | 3 | 0.91 | 0.0% |
| EV_Auto (RIVN) | 1 | 0.92 | -1.1% (mejora) |
| Consumer_Staples_Beverage (CELH) | 1 | 0.85 | 6.6% |
| Mobility_Rideshare (LYFT) | 1 | 0.91 | 0.0% |

**Label: VALIDATED.** La caída más fuerte (Hardware_Semis — SMCI,
IONQ, WOLF — 17.6%) queda muy por debajo del 40%.

## Veredicto de esta capa (no de EXP-003 completo)

**Los 3 buckets: VALIDATED.** A diferencia de la Capa 4 (placebo, los
3 REJECTED) y parcialmente la Capa 7 (largo_plazo REJECTED), esta capa
no encuentra evidencia de que el resultado de ningún bucket dependa de
un solo sector o clúster correlacionado — el patrón de caídas/mejoras
al quitar grupos está disperso (varios grupos incluso MEJORAN el
Sharpe al quitarse, lo que indica dilución más que dependencia
concentrada). Esto responde una pregunta distinta a la de la Capa 4:
aquí la pregunta es "¿depende de un sector específico?" (no) — la
Capa 4 ya respondió una pregunta más dura ("¿el orden temporal real
aporta algo sobre un reordenamiento al azar?", con resultado negativo
en los 3 buckets). Ambos resultados son compatibles entre sí: un
resultado puede estar bien distribuido entre sectores Y seguir sin ser
distinguible de ruido en su conjunto — esta capa no revierte ni
confirma el hallazgo de la Capa 4, responde una pregunta ortogonal.
