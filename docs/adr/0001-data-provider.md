# ADR 0001 — Proveedor de datos y broker para la Fase 0

## Estado
Aceptado (Fase 0 — Research MVP).

## Contexto
El documento de visión (`vision.md`) proponía Interactive Brokers
como primer broker y no fijaba proveedor de datos. El usuario
propuso eToro; se investigó y **eToro no ofrece una API pública de
trading retail** (su programa OpenAPI fue descontinuado; solo existe
integración a nivel institucional/white-label). No es viable para
este proyecto.

## Decisión
- **Datos (Fase 0):** `yfinance`. Gratuito, sin registro, suficiente
  para investigación y backtest. Limitación conocida: no apto para
  datos intradía de producción ni para ejecución en tiempo real —
  se reevaluará en Fase 2 (candidatos: Polygon.io, Alpaca Market Data).
- **Broker (Fase 6, cuando llegue):** Alpaca como primera opción.
  Razones: API REST moderna y bien documentada, SDK de Python
  maduro, paper trading gratuito sin fricción, soporta acciones y
  ETFs de EE.UU. (el mercado inicial del proyecto). Interactive
  Brokers queda como alternativa si Alpaca resulta insuficiente
  (p. ej. al expandir a Forex o mercados fuera de EE.UU.).
- **Indicadores técnicos:** librería `ta` (pure Python) en lugar de
  TA-Lib. TA-Lib requiere compilar una dependencia C que complica el
  entorno de desarrollo sin aportar algo que `ta` no resuelva para
  los indicadores de la Estrategia A/B. Se puede reevaluar si se
  necesita algún indicador específico no cubierto.

## Consecuencias
- Ningún dato de esta fase debe tratarse como apto para producción.
- La integración de broker no comienza hasta Fase 6, y queda
  explícitamente fuera del alcance de este ADR.
- Si en el futuro se evalúa un broker distinto a Alpaca o IBKR, debe
  documentarse en un nuevo ADR antes de implementarlo.
