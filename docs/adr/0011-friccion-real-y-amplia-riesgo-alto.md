# ADR 0011 — Fricción real en el motor + amplía Riesgo Alto a 45 símbolos

## Estado
Aceptado. Cierra la ronda de mejoras iniciada en ADR 0010.

## Contexto
Dos pendientes quedaron explícitos tras ADR 0010:

1. El motor de paper trading (`src/paper_trading/engine.py`) ejecutaba
   cada entrada/salida exactamente al precio de cierre o al stop, sin
   ninguna fricción — a diferencia del backtest formal
   (`src/backtesting/run.py`), que sí asume 0.05% comisión + 0.05%
   slippage por lado desde el principio. Esto hacía que los números
   de paper trading fueran más optimistas que el propio backtest
   formal del proyecto, sin razón.
2. Riesgo Alto fue el bucket que más se benefició de ampliar el
   universo (ADR 0010: +18.94% → +45.28% del ejercicio anterior),
   señal de que tenía más margen relativo que Largo/Mediano Plazo.

## Decisión 1 — Fricción real en el motor
Se agrega `FRICCION_POR_LADO = 0.001` (0.05% comisión + 0.05%
slippage, idéntico al backtest formal) a `src/paper_trading/engine.py`:

- **Entrada**: `entry_price = precio_cierre * (1 + fricción)` — el
  costo base ya incluye la fricción, así que el position sizing (1-2%
  de riesgo) la contempla automáticamente.
- **Salida**: `proceeds = precio_salida * acciones * (1 - fricción)`
  — el producto de vender ya descuenta la fricción antes de
  reinvertirse en el benchmark o sumarse al cash.

## Decisión 2 — Amplía Riesgo Alto de 30 a 45 símbolos
Se agregan 15 small/mid-cap adicionales diversos (SQ/XYZ — Block Inc.
cambió de ticker —, SHOP, DOCU, ZM, OKTA, BILL, FVRR, UPWK, W, ETSY,
PENN, TTD, ASAN, CARG, WOLF) a `config/universe_riesgo_alto.txt`,
mismo criterio de diversidad que ADR 0010 (no solo ganadores
conocidos).

## Resultado medido (34 meses, ene 2024-oct 2026, con fricción YA
incluida en ambas corridas, split de producción 43.33/33.33/23.33)

| Cambio | Operaciones cerradas | Retorno neto total |
|---|---|---|
| Antes (117 símbolos, Riesgo Alto=30) | 309 | — (medido sin fricción en ADR 0010: +32.22%) |
| **Después (146 símbolos, Riesgo Alto=45, CON fricción)** | **336** | **+32.76%** |

Riesgo Alto específicamente: +45.28% → **+47.59%** con el universo
ampliado — confirma que era el bucket con más margen, incluso después
de pagar fricción real en 27 operaciones adicionales.

**Dato relevante:** el retorno final (+32.76%) es más alto que el
número anterior sin fricción (+32.22%) a pesar de incluir ahora un
costo real de operar en 336 trades — las dos mejoras (ampliar Riesgo
Alto + más operaciones en general) compensaron de sobra el costo
nuevo que se está modelando con más honestidad.

## Qué NO se tocó
- Ningún criterio de entrada de las estrategias.
- Largo Plazo y Mediano Plazo mantienen su universo de ADR 0010
  (13 y 74 símbolos respectivamente) — solo Riesgo Alto se amplió más.
- Trailing stop ancho y filtro de régimen siguen descartados (ver
  ADR 0010) — no se revisitaron en esta ronda.

## Pendiente
- SQ (Block Inc.) cambió de ticker a XYZ durante este ejercicio — se
  corrigió en el universo, pero es una señal de que los universos
  manuales necesitan revisión periódica por cambios corporativos
  (splits, renombres, delistings), no solo al construirlos la primera
  vez.
