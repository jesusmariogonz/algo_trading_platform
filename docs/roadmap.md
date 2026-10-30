# Roadmap

Fases adaptadas del documento de visión (`vision.md`), reordenadas
para validar la idea antes de invertir en infraestructura.

## Fase 0 — Research MVP (este repo, hoy)
- [x] Estructura del repo
- [x] Descarga de datos (yfinance)
- [x] Indicadores (SMA, RSI, ATR, volumen)
- [x] Estrategia A (Trend Following) como reglas configurables
- [x] Backtest con vectorbt + comisiones/slippage
- [x] Estrategia B (Momentum/Breakout, proxy VCP simplificado)
- [x] Fuerza relativa vs. benchmark (SPY)
- [x] Walk-forward testing (ventanas consecutivas, sin optimización de
      parámetros todavía — ver docstring de walk_forward.py)
- [x] Reparto de capital en 4 buckets (40/30/20/10 — ver README.md)
- [x] Screener diario (señales de hoy + position sizing por 1% de riesgo),
      limitado al bucket Mediano Plazo (el único con estrategia real)
- [ ] Evaluar con calma los resultados de walk-forward antes de avanzar
- [ ] Definir estrategia para Riesgo Alto y Muy Alta Volatilidad (hoy
      son buckets de capital sin lógica de inversión detrás)
- [ ] Definir la condición mencionada por el usuario de "escalar
      riesgo alto solo si el rendimiento anual supera 10%" — quedó
      pendiente de precisar, no implementada todavía

**Hallazgo del primer walk-forward (4 ventanas, 2021-2026):**
Trend Following fue consistente en 3/4 ventanas; Momentum/Breakout
solo en 2/4, con la ventana más reciente en negativo. Esto es una
señal de alerta real sobre Momentum/Breakout tal como está, no un
resultado a ignorar — antes de construir más infraestructura vale la
pena revisar si el proxy VCP simplificado necesita ajuste, o si la
estrategia simplemente no tiene edge suficiente.

**Criterio para avanzar a Fase 1:** el walk-forward de al menos una
estrategia debe mostrar consistencia (≥50% de ventanas con mayoría de
símbolos en positivo) y suficientes operaciones por ventana para no
ser ruido estadístico — no solo un buen resultado en el backtest
completo sin partir.

## Fase 1 — Foundation formal
- Postgres (modelo de datos de `vision.md` § 6)
- Migraciones (Alembic)
- Docker Compose (Postgres + app)
- Separación DEV/TEST/PROD
- CI con GitHub Actions (lint + tests)

## Fase 2 — Data Engineering formal
- `MarketDataProvider` como interfaz abstracta
- Pipeline Raw → Validation → Processing → Features → Persistence
- Versionado de datasets
- Calendario bursátil, zonas horarias, ajustes por splits/dividendos

## Fase 3 — Quantitative Research
- Estrategia B (Momentum/Breakout, VCP)
- Strategy Registry
- Ranking / scoring entre señales del universo

## Fase 4 — Backtesting avanzado
- In-sample / out-of-sample / walk-forward
- Análisis por régimen de mercado
- Reportes reproducibles por experimento (parcialmente ya en Fase 0)

## Fase 5 — Risk Management Engine
- Position sizing formal
- Límites de exposición, correlación, drawdown
- Kill Switch

## Fase 6 — Execution (Paper primero)
- Adaptador de broker (Alpaca para paper trading)
- Order Management, reconciliación
- Modos RESEARCH / BACKTEST / PAPER — LIVE permanece deshabilitado

## Fase 7 — Monitoring
- API (FastAPI)
- Dashboard (el candidato natural: una zona privada de jgonzalez.app
  que consuma esta API — ver ADR 0002)
- Alertas

## Fase 8 — Production readiness
- Seguridad, resiliencia, pruebas de carga
- Evaluación Go/No-Go explícita para habilitar LIVE
- Ningún capital real se arriesga sin esta evaluación
