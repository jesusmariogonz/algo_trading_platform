# ADR 0010 — Amplía el universo de los 3 buckets

## Estado
Aceptado.

## Contexto
El ejercicio exploratorio de simular el modelo completo (ver ADR 0006,
0007, 0008) mostró un problema de fondo: muy pocas operaciones por
mes porque el universo original era chico (12/12/8 símbolos por
bucket), no porque las reglas de entrada carecieran de edge. Se probó
ampliar el universo en dos pasos, sobre 34 meses (ene 2024-oct 2026),
con fricción real (0.05% comisión + 0.05% slippage por lado, igual
que `src/backtesting/run.py`) y con el split de producción
(43.33/33.33/23.33):

| Universo | # símbolos | Operaciones cerradas | Retorno neto |
|---|---|---|---|
| Original | 32 (12+12+8) | 99 | +30.50% |
| Ampliado (paso 1) | 75 (42+20+13) | 235 | +31.14% |
| **Ampliado (paso 2, elegido)** | **117 (74+30+13)** | **309** | **+32.22%** |

Rendimientos decrecientes pero sin revertirse en el rango probado —
cada ampliación siguió sumando, aunque cada vez menos por símbolo
agregado (ver advertencia abajo sobre por qué no se sigue ampliando
indefinidamente).

## Decisión
Se adoptan como universos de producción (archivos
`config/universe*.txt`) los símbolos de la ronda 2 del ejercicio:

- **Mediano Plazo**: 74 símbolos — las 12 originales + 30 large-caps
  líquidas diversas por sector (bancos, energía, salud, consumo,
  industrial, tecnología) **incluyendo nombres históricamente
  mediocres a propósito** (IBM, T, VZ, GE) para no empeorar el sesgo
  de supervivencia ya documentado — no es una lista optimizada con el
  diario de hoy.
- **Riesgo Alto**: 30 símbolos — las 12 originales + 18 small/mid-cap
  adicionales (cripto-adyacentes como COIN/MARA, consumo digital como
  LYFT/SNAP/CHWY, software como NET/DDOG/CRWD), sin criptomonedas.
- **Largo Plazo**: 13 ETFs — las 8 originales + TLT, IJH, IJR, VNQ,
  GLD (bonos largos, mid/small-cap amplio, bienes raíces, oro) para
  diversificar más allá de solo índices de acciones.

Se eligió la ronda 2 (117 símbolos) sobre la ronda 1 (75) porque
siguió mejorando el resultado neto (+31.14% → +32.22%) sin señales de
reversión — no se sigue ampliando más allá de esto en esta iteración
(ver advertencia).

## Qué se probó y se DESCARTÓ (no va a producción)
Dos candidatos adicionales se probaron sobre el universo de 117
símbolos, con fricción, mismo período — ninguno mejoró el resultado:

- **Trailing stop con ATR 3.0x en Riesgo Alto** (más ancho que el
  1.75x/2.5x original): empeoró ese bucket (+45.28% → +41.78%).
- **Filtro de régimen para el cash-en-benchmark** (solo invertir en
  SPY si SPY > su propia SMA 200): empeoró fuertemente el total
  (+32.22% → +22.56%) — el período probado es predominantemente
  alcista con correcciones cortas, y el filtro sacaba el cash justo
  antes de los rebotes, el error clásico de market timing.

Ninguno de los dos se descartó por intuición — ambos se probaron con
el mismo motor y se reportan aquí exactamente como salieron,
incluyendo el resultado negativo.

## Advertencia — por qué no se sigue ampliando indefinidamente
Más símbolos ayuda hasta cierto punto, pero con rendimientos
decrecientes y riesgos crecientes documentados explícitamente:

1. **Correlación, no diversificación real** — símbolos adicionales de
   EE.UU. se mueven con el mismo régimen macro que los ya incluidos;
   más operaciones no es automáticamente más edge independiente.
2. **Calidad decreciente de los candidatos marginales** — nombres
   menos líquidos tendrían spreads reales mayores al 0.05%+0.05% que
   se está asumiendo, lo cual el modelo no refleja todavía.
3. **Riesgo de sobreajuste al elegir símbolos a mano** — cuantos más
   se agreguen manualmente, más fácil contaminar el resultado sin
   darse cuenta. Por eso se usó una lista deliberadamente diversa, no
   una optimizada.

## Pendiente — no incluido en este ADR
- **Fricción real (comisión + slippage) en `src/paper_trading/engine.py`**:
  el motor de producción todavía NO la tiene (solo el backtest formal
  la tiene). Se midió su efecto en el ejercicio (-0.44 puntos sobre
  32 buckets originales) pero el usuario pidió explícitamente NO
  incluirla en este cambio — queda como pendiente separado a decidir.
- Universo de 500+ símbolos (S&P 500 completo) — no se probó por
  tiempo de descarga/cómputo en este ejercicio, no por descartarlo de
  antemano.
