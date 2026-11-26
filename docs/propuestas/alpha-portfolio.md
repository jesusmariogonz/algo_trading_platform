# Propuesta de experimento — Bucket Alpha ("Alpha Portfolio")

**Estado: IDEA, no ejecutada.** Guardada el 2026-11-26 a pedido
explícito del usuario — "solo que lo guardes como un experimento que
quiero realizar, llámalo el Alpha portafolio". Nada de lo descrito
aquí se ha construido, corrido ni asignado a ningún bucket real.

**Nombre:** nada de "ALPHA-01" — el usuario pidió explícitamente que
no se le asigne un nombre propio aparte. Cuando se decida empezar,
este experimento toma el **siguiente número EXP-NNN disponible en ese
momento** (el mismo registro numerado que ya usa `pulso-research-lab`
para EXP-000 a EXP-005, y que este repo ya usó para
`research/exp-003-validacion-motor-produccion/`) — no un número fijado
hoy, porque para cuando se ejecute puede que ya existan más
experimentos numerados. La carpeta sigue la convención de
`research/exp-0NN-alpha-portfolio/` (mismo patrón que exp-003, no el
patrón `<AAAA-MM>-<slug>` de investigaciones menores — ver
`research/README.md`), y si sobrevive la validación, en su propio ADR.

## Filosofía

No es "comprar más cosas con mejores stops" — eso sería repetir
Mediano Plazo/Riesgo Alto con otro nombre. Es selección extrema:
pocas posiciones (3-5), cada una respaldada por varias evidencias
independientes de momentum simultáneamente, con el filtro de régimen
de mercado decidiendo cuánto (o si nada) se expone.

> "Tus buckets actuales: Largo Plazo (tendencia amplia), Mediano Plazo
> (tendencia intermedia), Riesgo Alto (oportunidades agresivas).
> Alpha: selección extrema + momentum relativo + confirmación de
> régimen + pocas posiciones + pérdidas pequeñas + ganadoras libres."

Límite explícito que el usuario puso a la idea: no existe un bucket
que garantice "ganar, ganar, ganar" — lo que se puede diseñar es uno
con más potencial de retorno y reglas que intenten evitar que una
mala racha lo destruya. No se construye sobre Largo Plazo o Mediano
Plazo existentes; sería un **cuarto bucket experimental**, separado.

## Score de entrada (0-100)

| Componente | Puntos | Criterio |
|---|---|---|
| Momentum | 35 | retorno 20d, 60d, 120d; precio vs. SMA50; precio vs. SMA200 |
| Fuerza relativa | 25 | el activo debe estar en el percentil ~85-90 de su universo (top 10-15%), no solo tener "una señal" |
| Tendencia | 20 | precio > SMA200; SMA50 > SMA200; pendiente de SMA200 positiva; cerca de máximos de 52 semanas |
| Calidad del movimiento | 10 | ATR razonable; volumen suficiente; evitar entrar después de un movimiento explosivo; evitar spreads/volatilidad extremos |
| Mercado (régimen) | 10 | ver Regime Gate abajo |

Umbral de entrada: **score ≥ 80/100** para posición completa.

### Alpha Conviction Score (tamaño según score)

| Score | Acción |
|---|---|
| 90-100 | Posición completa |
| 80-89 | Posición completa |
| 70-79 | Media posición |
| < 70 | No comprar |

## Regime Gate

No es solo "SPY arriba/abajo de SMA200" — combina SPY trend + breadth
+ volatilidad + momentum:

| Régimen | Condición | Exposición de Alpha |
|---|---|---|
| 🟢 Bull | SPY > SMA200, SMA50 > SMA200, breadth > 55%, VIX moderado | 100% |
| 🟡 Neutral | 2 de las 4 condiciones anteriores | 50% |
| 🔴 Bear | SPY < SMA200, breadth deteriorándose, volatilidad elevada | 0-25% |

## Selección (funnel)

```
Universo: 100-150 activos (ETF + acciones líquidas)
  ↓ filtros básicos
50 candidatos
  ↓ momentum
20
  ↓ tendencia
10
  ↓ fuerza relativa
5
  ↓ score ≥ 80
Top 3 (máximo)
```

Máximo **3 posiciones**. Si solo califican 2 → 2. Si solo 1 → 1. Si
ninguna → **cash real** (no SPY/GLD como proxy — ver abajo). No operar
también es una decisión; el motor no tiene la obligación de invertir.

## Position sizing — riesgo constante, no monto fijo

Riesgo fijo por operación (ej. 1.5% del equity), no un monto fijo en
dólares. El tamaño de la posición se deriva de la distancia al stop:

```
riesgo_maximo = equity * 1.5%
tamaño_posición = riesgo_maximo / distancia_al_stop_%
```

Ejemplo: equity $20,000, riesgo 1.5% = $300. Si el stop está 5% abajo
→ posición de $6,000. Si el stop está 10% abajo → posición de $3,000.
La volatilidad del activo determina cuánto capital se le asigna, no
cuánto se puede perder.

## Stops

Dos stops simultáneos, el que ocurra primero manda:

1. **Trailing dinámico — 2.5 ATR desde el máximo alcanzado**, nunca se
   baja. Ejemplo: entrada $100, ATR $3 → stop inicial $92.50. Precio
   sube a $110 → stop $102.50. Precio sube a $120 → stop $112.50.
2. **Hard stop / catastrophic stop — ej. -8%** (o un límite basado en
   riesgo), como barrera absoluta independiente del trailing. Motivo
   explícito: evitar que una posición llegue a algo como el -13.69%
   que tuvo ETSY en la cuenta real de IBKR sin una barrera dura.

### Profit protection progresiva (no mover el stop de inmediato)

No mover el stop después de +1% — eso mata tendencias nacientes.
Progresión sugerida:

| Movimiento | Acción sobre el stop |
|---|---|
| +1 ATR | Nada |
| +2 ATR | Nada, o ligera mejora |
| +3 ATR | Aproximar a breakeven |
| +4 ATR | Empezar a proteger capital |
| +5 ATR+ | Trailing agresivo |

## Salida adicional (no solo el stop)

Si `score < 60` **y** el momentum de 20d/60d se está deteriorando →
salir, sin esperar necesariamente a que el stop se active.

## Cash ocioso: cash real, no proxy

A diferencia del resto de los buckets (que invierten el cash ocioso
en el blend 50% SPY / 50% GLD — ver ADR 0014), Alpha debe medir su
propio edge sin contaminación: si no hay señal, el cash se queda en
cash. La pregunta que debe poder responderse limpia es "¿el algoritmo
gana dinero cuando tiene una señal?", sin mezclar el resultado con
otra estrategia. Un benchmark de "costo de oportunidad" se construye
aparte, no mezclado en el propio resultado de Alpha.

## Criterio de éxito — no optimizar por retorno histórico

Explícitamente **no** se optimiza para "mayor retorno en backtest" —
eso fabrica fácilmente un resultado que luego se destruye en vivo
(paralelo directo con el hallazgo real de ADR 0033: AUC in-sample 0.93
vs. OOS 0.25 en el meta-modelo ML descartado). Se optimiza/evalúa por:

- Expectancy
- Sharpe out-of-sample
- Maximum drawdown
- Profit factor
- Calmar ratio

## Protocolo de validación antes de cualquier capital

No se implementa directo a producción. Se construye como el
experimento EXP-NNN que le toque en turno (ver nota de nombre arriba)
y se corre, en el **mismo período histórico exacto**, contra:

1. Largo Plazo (configuración actual)
2. Mediano Plazo (configuración actual)
3. Riesgo Alto (configuración actual)
4. Benchmark Diversificado
5. Bucket Alpha (este experimento)

Secuencia de validación, en orden, antes de asignarle capital de Paper
(y mucho antes de capital real): **IS → OOS → Walk-Forward → Bootstrap
→ Monte Carlo → Paper**. Solo si sobrevive esa secuencia completa se
considera seriamente como candidato al bucket "quiero ganar, ganar,
ganar" que el usuario pidió — diseñado para intentar ganar sin
autoengañarse con un backtest bonito.

La pregunta que este experimento tiene que contestar, en los términos
del propio usuario: **¿Bucket Alpha realmente genera más alpha, o
solamente estamos inventando otra estrategia bonita que funciona en
backtest?**
