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
- [ ] Correr ambos backtests y evaluar si hay evidencia de mérito
- [ ] Walk-forward testing

**Criterio para avanzar a Fase 1:** el backtest de al menos una
estrategia debe mostrar métricas razonables (Sharpe > 0.5, max
drawdown controlado, suficientes operaciones para ser estadísticamente
no-ruido) en un out-of-sample real, no solo en el período de ajuste.

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
