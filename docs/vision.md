# Visión — Algorithmic Trading Platform (arquitectura objetivo)

Este documento condensa el master prompt original del proyecto. Es la
**visión a 12+ meses**, no el plan de esta semana — ver `roadmap.md`
para el orden real de construcción, empezando por el MVP de
investigación en este mismo repo.

## Objetivo
Plataforma personal de inversión cuantitativa: identificar
oportunidades, evaluar estrategias, administrar riesgo, ejecutar
operaciones y monitorear rendimiento. Capital de referencia ≤ USD
1,000. Mercado inicial: acciones/ETFs de EE.UU. Horizonte: swing
trading, temporalidad diaria. Lenguaje: Python.

Arranca en modo investigación/simulación. **LIVE (dinero real)
permanece deshabilitado hasta superar criterios de validación
explícitos** — no se habilita automáticamente al completar el MVP.

## Principios
Clean Architecture · DDD donde aporte valor · Separation of Concerns
· SOLID · Event-driven donde sea necesario · API-first ·
Configuration-driven · Observabilidad · Security by Design · TDD en
componentes críticos · Reproducibilidad de experimentos.

El motor de estrategias **nunca** ejecuta órdenes directamente. Toda
operación pasa por el Risk Management Engine antes de llegar al
broker.

## Módulos (arquitectura objetivo)
1. **Market Data** — interfaz `MarketDataProvider` para cambiar de
   proveedor sin tocar el motor de estrategias. Calendarios,
   timezones, ajustes por splits/dividendos, validación de integridad.
2. **Data Engineering** — pipeline Raw → Validation → Processing →
   Features → Persistence. Evita look-ahead bias y survivorship bias.
3. **Strategy Engine** — Estrategia A (Trend Following) y Estrategia
   B (Momentum/Breakout, VCP, filtros Minervini/O'Neil/Weinstein).
   Cada estrategia: id, nombre, versión, parámetros, entrada, salida,
   stop/take profit, resultados históricos. Strategy Registry.
4. **Risk Management Engine** (crítico) — position sizing, riesgo
   máximo por operación (1%), R:R mínimo 2:1, apalancamiento 1x,
   riesgo agregado abierto 2-3%, exposición por activo/sector,
   correlación, drawdown máximo, límite de pérdida diaria, Kill
   Switch. Rechaza automáticamente operaciones que incumplan reglas.
5. **Portfolio Management** — capital, posiciones abiertas/cerradas,
   costo promedio, P&L realizado/no realizado, comisiones,
   dividendos, reconciliación periódica contra el broker.
6. **Execution Engine** — Order Management, fills parciales,
   reintentos idempotentes, reconciliación. Modos: RESEARCH,
   BACKTEST, PAPER, LIVE. LIVE deshabilitado por defecto; no se
   habilita con un simple cambio de parámetro — requiere controles
   explícitos de configuración + autorización + validación de riesgo.
7. **Monitoring & Analytics** — valor de portafolio, CAGR, max
   drawdown, Sharpe, Sortino, win rate, profit factor, exposición,
   señales generadas/rechazadas, estado de APIs. Alertas por errores
   de conexión, datos desactualizados, órdenes rechazadas,
   posiciones no reconciliadas, exceso de riesgo, Kill Switch.

## Backtesting
Comisiones, spread, slippage, gaps, liquidez, ejecución de stops,
dividendos, splits, disponibilidad temporal de información.
In-sample / out-of-sample / walk-forward. Benchmark SPY. Análisis de
sensibilidad y por régimen de mercado. No optimizar exclusivamente
para maximizar retorno histórico. Reportes reproducibles con
parámetros conservados por experimento.

## Modelo de datos objetivo (PostgreSQL)
`instruments`, `markets`, `market_prices`, `corporate_actions`,
`technical_indicators`, `strategies`, `strategy_versions`,
`strategy_parameters`, `trading_signals`, `portfolios`,
`portfolio_positions`, `orders`, `executions`, `risk_events`,
`backtest_runs`, `backtest_metrics`, `system_events`. PKs, FKs,
índices, restricciones, timestamps, auditoría, migraciones. No
sobrescribir historial de órdenes/señales/ejecuciones.

## Seguridad y resiliencia
Variables de entorno / secret management (nunca API keys en código),
validación de entradas, logs estructurados, manejo de excepciones,
reintentos controlados, prevención de órdenes duplicadas,
recuperación ante desconexiones, health checks, Kill Switch
independiente, ambientes DEV/TEST/PROD separados. Si los datos están
desactualizados o no se pueden validar, el sistema bloquea nuevas
operaciones. Si el estado de posiciones del broker es desconocido,
suspende ejecución y reconcilia antes de continuar.

## Stack objetivo
Backend: Python, FastAPI, Pydantic, SQLAlchemy. Data: Pandas, NumPy,
Polars, PyArrow, Parquet. Research: VectorBT, SciPy, Statsmodels,
indicadores técnicos, scikit-learn (futuro). Persistencia: Postgres,
Parquet, MLflow (futuro). Infra: Docker, Docker Compose, GitHub
Actions. Dashboard: Streamlit (operativo) / Power BI (analítico) —
o, según ADR 0002, una zona privada de jgonzalez.app. Broker:
Alpaca primero (ver ADR 0001), IBKR como alternativa futura; CCXT
para cripto más adelante.

## Stack real de la Fase 0 (este repo, hoy)
yfinance, pandas, pyarrow, vectorbt, `ta` (no TA-Lib, ver ADR 0001),
pytest. Sin Postgres, sin FastAPI, sin Docker todavía — llegan en
Fase 1+ según `roadmap.md`.

## Criterios de aceptación del MVP completo (no de la Fase 0)
Descarga y valida datos históricos · calcula indicadores · ejecuta
≥2 estrategias · genera señales reproducibles · backtest con costos
· calcula métricas de rendimiento · controla riesgo · administra
portafolio simulado · ejecuta en PAPER · reconcilia posiciones y
órdenes · genera reportes · mantiene auditoría completa · tiene
pruebas automatizadas. **No habilita LIVE automáticamente.**
