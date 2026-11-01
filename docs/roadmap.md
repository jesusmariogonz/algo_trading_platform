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
- [x] Riesgo Alto: estrategia definida (mismas estrategias, universo
      small/mid-cap sin cripto, 2% riesgo/operación — ver ADR 0003)
- [x] Regla de escalamiento de Riesgo Alto precisada y documentada
      (ADR 0003) — implementación real pendiente de Fase 6 (requiere
      valuación de portafolio en vivo, no se puede fabricar antes)
- [ ] Muy Alta Volatilidad (cripto): sin construir — requiere su
      propio motor de datos (API distinta a yfinance, calendario 24/7,
      sin splits/dividendos). Su propio ADR cuando se diseñe.
- [x] Estrategia C: Time-Series Momentum (12m/6m), para el bucket
      Largo Plazo — walk-forward 3/4 ventanas consistente.
- [x] Cross-Sectional Momentum (ranking + rebalanceo mensual) como
      método de selección, no estrategia de entrada/salida.

**⚠ Sesgo de supervivencia detectado en el backtest de Cross-Sectional
Momentum**: corrido sobre nuestros 30 símbolos actuales (que incluyen
NVDA, SMCI, AVGO, PLTR — elegidos a mano porque HOY sabemos que
fueron ganadores del rally de IA 2023-2025), dio 591% de retorno vs.
78% de SPY. Ese número está inflado por el universo, no por la
estrategia — no es un resultado limpio. Antes de confiar en esto hace
falta correrlo sobre un universo mucho más amplio y neutral (ej. todo
el S&P 500 de hace 5 años, incluyendo las que después cayeron o
fueron excluidas del índice), no una lista curada con el diario de
hoy. Pendiente explícito, no resuelto.

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
- [x] In-sample / out-of-sample / walk-forward
- [x] Monte Carlo (sensibilidad al orden de las operaciones)
- [x] Stress testing (costos elevados + peor ventana histórica real)
- [ ] Análisis por régimen de mercado (más allá del peor drawdown)
- [x] Reportes reproducibles por experimento

## Fase 5 — Risk Management Engine
- Position sizing formal
- Límites de exposición, correlación, drawdown
- Kill Switch

## Fase 6 — Execution (Paper primero)
- [x] Paper trading SIMULADO (src/paper_trading/), sin broker real
      todavía — abre/cierra posiciones con las reglas del screener,
      guarda historial diario, exportado al dashboard de jgonzalez.app
- [ ] **En curso: 3-4 semanas de paper trading antes de evaluar
      dinero real** (base final: **$1,000 USD** — se probó con $3,000
      el mismo día por una aclaración del usuario sobre el monto, pero
      se corrigió de vuelta a $1,000 minutos después, también el mismo
      día, antes de que afectara el historial de evaluación. A partir
      de aquí el usuario inyecta/retira capital el mismo avisándolo
      explícitamente — ver data/paper_trading/history.json)
- [x] Conversión MXN->USD automática (`allocation.py inject-mxn`),
      vía open.er-api.com (gratuita, sin key). El tipo de cambio usado
      se guarda en el ledger para auditoría — nunca se oculta.
      $3,000 MXN de referencia ≈ $159 USD al tipo de cambio del
      2026-10-30 (18.83 MXN/USD).
- [x] Inyección mensual: el usuario decidió registrarla a mano, no
      automatizada — no se construyó una Routine para esto.
- [x] ~~Quant Portfolios (src/quant_portfolios/)~~ — se construyeron
      (ver ADR 0005) y luego se **ELIMINARON por completo el
      31-oct-2026** (ver ADR 0009), decisión explícita del usuario. La
      comparación "buckets vs. quant portfolios" que estaba pendiente
      quedó cerrada al eliminar uno de los dos lados.
- [x] **Rediseño del modelo de buckets (31-oct-2026)**: tras comparar
      backtests reales con capital simulado sobre 3 ventanas (6, 22 y
      34 meses), se eliminó el bucket de cripto (rindió peor en las 3
      ventanas sin excepción — ver ADR 0006) y se agregó trailing stop
      + cash ocioso invertido en SPY a los 3 buckets restantes (ver
      ADR 0007). Nuevo split: 43.33% / 33.33% / 23.33%. Se reinició
      `data/portfolio/ledger.json` y `data/paper_trading/*.json` para
      arrancar limpio con el modelo nuevo.
- [x] **Risk Engine real (circuit breakers) en los 3 buckets
      (31-oct-2026)**: pérdida diaria (1%/1.5%/2%) y drawdown de
      revisión (6%/10%/15%), llevado desde el diseño de los Quant
      Portfolios antes de eliminarlos — ver ADR 0008. Nunca liquida
      posiciones existentes, solo bloquea abrir nuevas.
- [x] **Amplía el universo de los 3 buckets (31-oct-2026)**: de 32 a
      117 símbolos, probado contra 34 meses con fricción real —
      309 operaciones cerradas (antes 99), retorno neto +32.22%
      (antes +30.50%). Se probaron y DESCARTARON (empeoraron el
      resultado): trailing stop más ancho en Riesgo Alto, filtro de
      régimen para el cash-en-benchmark — ver ADR 0010.
- [x] **Fricción real en el motor + amplía Riesgo Alto a 45 símbolos
      (31-oct-2026)**: `src/paper_trading/engine.py` ya cobra 0.05%
      comisión + 0.05% slippage por lado en cada entrada/salida,
      igual que el backtest formal. Riesgo Alto pasó de 30 a 45
      símbolos (era el bucket con más margen relativo). Resultado
      final validado: 336 operaciones cerradas, **+32.76% neto** en
      34 meses (sube pese a la fricción nueva) — ver ADR 0011.
- [x] **Riesgo por operación subido + sizing sobre equity actual
      (1-nov-2026)**: 1%→2% (Largo/Mediano Plazo), 2%→3% (Riesgo
      Alto); el monto de riesgo ya no usa el capital inicial fijo del
      bucket, usa su equity de hoy. Resultado en 36 meses: **+48.25%**
      neto (antes +37.21%), pero drawdown máximo sube a **18.77%**
      (antes 10.83%) — decisión de apetito de riesgo explícita del
      usuario ("aguantaré el drawdown"), no una mejora gratuita. Se
      probó y DESCARTÓ repartir el cash ocioso en bonos/SGOV para
      bajar el drawdown — empeoró demasiado el retorno (SGOV: -8.37%
      neto). Ver ADR 0012.
- [x] **Corrección de reproducibilidad de backtests (1-nov-2026)**: se
      encontró que `yfinance` revisa precios ajustados en cada
      descarga, haciendo que comparaciones hechas en momentos
      distintos del día no fueran comparables entre sí. Los números de
      ADR 0012 se corrigieron con una descarga única congelada:
      retorno real **+22.07%** (no +48.25%), drawdown máximo real
      **13.63%** (no 18.77%) — la dirección del hallazgo se mantiene,
      la magnitud era menor de lo reportado originalmente. Ver
      corrección en ADR 0012.
- [x] **Semiconductores/Defensa (TSM, SMH, GD, NOC, LHX): probado y
      DESCARTADO (1-nov-2026)** — bajó el retorno sin reducir el
      drawdown, con datos congelados. Ver ADR 0013.
- [ ] **Oro (GLD) como cash holder: pendiente de decisión del
      usuario** — reduce el drawdown (13.63%→12.22%) a cambio de
      retorno (22.07%→17.53%), mejor relación que las alternativas de
      bonos ya descartadas, pero no es gratis. Ver ADR 0013.
- [ ] Mejora de infraestructura pendiente: el pipeline de descarga no
      cachea datos entre corridas exploratorias — automatizar un modo
      "congelado" para sesiones de backtest comparativo evitaría este
      tipo de error de reproducibilidad en el futuro.
- [ ] Investigación en curso: conectar un bróker real vía API. Alpaca
      descartado para cuenta LIVE en México (solo invite-only para
      no-residentes de EE.UU.); Interactive Brokers sí acepta
      residentes de México — cuenta en trámite (No Borrow Margin,
      permisos Stocks/Options habilitados por default del broker,
      Prediction Markets desactivado). Pendiente confirmar con IBKR si
      su Web API con OAuth 1.0a permite automatización headless (sin
      TWS/Gateway corriendo) antes de construir el adaptador.
- [ ] Adaptador de broker real (Alpaca) para PAPER vía su API
- [ ] Order Management, reconciliación contra broker real
- [ ] Modos RESEARCH / BACKTEST / PAPER — LIVE permanece deshabilitado

## Fase 7 — Monitoring
- API (FastAPI)
- Dashboard (el candidato natural: una zona privada de jgonzalez.app
  que consuma esta API — ver ADR 0002)
- Alertas

## Fase 8 — Production readiness
- Seguridad, resiliencia, pruebas de carga
- Evaluación Go/No-Go explícita para habilitar LIVE
- Ningún capital real se arriesga sin esta evaluación
