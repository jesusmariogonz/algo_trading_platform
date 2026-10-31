# Algo Trading Platform — MVP de investigación

Sistema personal de inversión cuantitativa. Este repo arranca en su
**fase de investigación**: descarga de datos, indicadores, una
estrategia (Trend Following) y backtesting. Sin broker, sin Postgres,
sin Docker todavía — eso llega después de validar que la estrategia
tiene algún mérito.

Ver [`docs/vision.md`](docs/vision.md) para la arquitectura completa a
la que este proyecto apunta eventualmente, y [`docs/roadmap.md`](docs/roadmap.md)
para las fases.

## Alcance actual (Fase 0 — Research MVP)

- Descarga histórico diario (OHLCV) de un universo pequeño de
  acciones/ETFs de EE.UU. vía `yfinance`.
- Calcula indicadores técnicos (SMA 20/50/150/200, RSI 14, ATR 14,
  volumen promedio 20 sesiones).
- Implementa la Estrategia A (Trend Following) y la Estrategia B
  (Momentum/Breakout con proxy VCP simplificado) como reglas de
  señal, configurables.
- Fuerza relativa contra un benchmark (SPY por defecto).
- Backtest con `vectorbt`, incluyendo comisiones y slippage básicos.
- Resultados reproducibles: cada corrida guarda sus parámetros.

**No** incluye todavía: Postgres, FastAPI, Docker, Risk Engine
formal, Execution Engine, broker real. Eso es la Fase 1 en adelante
(ver roadmap).

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Uso

```bash
# 1. Descargar datos históricos (acciones/ETFs vía yfinance, cripto vía Kraken)
python -m src.data.download --universe config/universe.txt --years 5
python -m src.data.download_crypto  # BTC, ETH, SOL... ~2 años (límite de Kraken)

# 2. Calcular indicadores
python -m src.indicators.compute

# 3. Calcular fuerza relativa vs. benchmark (requiere SPY en el universo).
#    IMPORTANTE: el benchmark de cripto es BTC, no SPY — usa --universe
#    para no sobrescribir la fuerza relativa de las acciones.
python -m src.indicators.relative_strength --benchmark SPY
python -m src.indicators.relative_strength --benchmark BTC --universe config/universe_cripto.txt

# 4. Correr backtest de una estrategia
python -m src.backtesting.run --strategy trend_following
python -m src.backtesting.run --strategy momentum_breakout

# 5. Walk-forward: la misma estrategia en N ventanas consecutivas,
#    para ver si el rendimiento es consistente o depende de un período
python -m src.backtesting.walk_forward --strategy trend_following --windows 4

# 6. Registra el capital que vas inyectando (se reparte 40/30/20/10
#    entre los 4 buckets — ver docs/vision.md "Reparto de capital")
python -m src.portfolio.allocation inject 1000       # ya en USD
python -m src.portfolio.allocation inject-mxn 3000    # convierte MXN->USD al tipo de cambio del día (open.er-api.com), guarda el tipo de cambio usado
python -m src.portfolio.allocation balances

# 7. Screener diario: qué símbolos cumplen HOY las condiciones de
#    entrada, y cuánto comprar según el 1% de riesgo máximo. Requiere
#    haber corrido 1-3 el mismo día para tener datos frescos.
python -m src.screening.daily_signals --bucket mediano_plazo

# 8. Cross-Sectional Momentum: ranking + rebalanceo mensual de una
#    canasta (no es una estrategia con señal por símbolo como las demás)
python -m src.backtesting.cross_sectional_backtest

# 9. Monte Carlo: ¿qué tan sensible es el resultado al orden de las
#    operaciones? Y stress test: costos elevados + peor caída real de SPY
python -m src.backtesting.monte_carlo --strategy trend_following --simulations 2000
python -m src.backtesting.stress_test --strategy trend_following
```

## Reparto de capital (4 buckets)

| Bucket | % | Estado |
|---|---|---|
| Largo plazo | 40% | Time-Series Momentum (12m/6m) · universo `config/universe_largo_plazo.txt` (ETFs amplios) · 1% riesgo/operación |
| Mediano plazo | 30% | Trend Following + Momentum/Breakout · universo `config/universe.txt` · 1% riesgo/operación |
| Riesgo alto | 20% | Mismas estrategias, universo más volátil `config/universe_riesgo_alto.txt` (small/mid-cap, sin cripto) · 2% riesgo/operación |
| Muy alta volatilidad | 10% | Trend Following + Momentum/Breakout · universo `config/universe_cripto.txt` (datos de Kraken) · 2% riesgo/operación · **backtest negativo, ver ADR 0004** |

## Estrategias (4 implementadas, 1 método de selección)

| Estrategia | Investigación base | Bucket | Estado |
|---|---|---|---|
| Trend Following (SMA) | — | Mediano/Riesgo Alto | Walk-forward 3/4 ventanas consistente |
| Momentum/Breakout (VCP simplificado) | — | Mediano/Riesgo Alto | Walk-forward 2/4 — inconsistente, en revisión |
| Time-Series Momentum | Moskowitz, Ooi & Pedersen (2012) | Largo Plazo | Walk-forward 3/4 ventanas consistente |
| Cross-Sectional Momentum | Jegadeesh & Titman (1993) | Selección entre buckets | **Resultado del backtest inflado por sesgo de supervivencia en el universo — ver advertencia abajo** |

**⚠ Sesgo de supervivencia**: nuestro universo (`config/universe*.txt`)
son símbolos elegidos a mano porque HOY sabemos que les fue bien
(NVDA, SMCI, AVGO, PLTR...). Cualquier backtest sobre este universo
—especialmente Cross-Sectional Momentum, que selecciona "ganadores"— está
inflado frente a lo que habría pasado operando con información
disponible en tiempo real sobre un universo neutral (ej. todo el S&P
500 de hace 5 años). Pendiente: correr sobre un universo histórico sin
sesgo antes de confiar en estos números — ver `docs/roadmap.md`.

## Paper Trading (en curso — 3-4 semanas antes de evaluar dinero real)

```bash
# Corre esto cada día de mercado (lo normal es vía la Routine diaria):
python -m src.data.download --universe config/universe.txt --years 2
python -m src.data.download --universe config/universe_riesgo_alto.txt --years 2
python -m src.data.download --universe config/universe_largo_plazo.txt --years 2
python -m src.indicators.compute
python -m src.indicators.relative_strength --benchmark SPY
python -m src.paper_trading.run_daily_tick
python -m src.paper_trading.export ../jesus-site/lib/paper-trading-snapshot.json
```

`src/paper_trading/engine.py` simula, día tras día, abrir y cerrar
posiciones con las MISMAS reglas que `daily_signals.py` — pero lo
hace solo (no es dinero real, no hace falta que decidas cada vez).
Estado en `data/paper_trading/state.json` (posiciones abiertas) y
`data/paper_trading/history.json` (snapshot diario, histórico
completo, nunca se sobrescribe). El dashboard en jgonzalez.app/trading
lo lee desde el JSON exportado.

El capital inicial de cada bucket se congela la primera vez que corre
el motor (snapshot de `allocation.py` en ese momento) — inyecciones
posteriores durante la ventana de prueba se ignoran a propósito, para
que el % de retorno mida la estrategia, no "metí más dinero".

## Quant Portfolios (3 productos con identidad propia — coexiste con buckets)

Modelo alternativo al de 4 buckets por horizonte, propuesto por el
usuario: 3 portafolios con motor, reglas de rebalanceo y límites de
riesgo propios — ver `docs/adr/0005-quant-portfolios.md`.

```bash
python -m src.data.download --universe config/universe_quant_portfolios.txt --years 2
python -m src.indicators.compute   # agrega EMA 20/50 también
python -m src.quant_portfolios.run_daily_tick
python -m src.quant_portfolios.export ../jesus-site/lib/quant-portfolios-snapshot.json

# Si un portafolio se suspendió por drawdown, reautorizar manualmente:
python -m src.quant_portfolios.reauthorize conservative_alpha
```

| Portafolio | Riesgo | Rebalanceo | Vol. objetivo (diseño) | Capital |
|---|---|---|---|---|
| Conservative Alpha | Bajo | Mensual | 6–9% | 45% |
| Balanced Growth | Medio | Mensual | 10–13% | 35% |
| Aggressive Momentum | Alto | Diario | 16–22% | 20% |

Dashboard: jgonzalez.app/trading/portafolios (separado del dashboard
de buckets en /trading).

## Robustez (Monte Carlo + stress testing)

- `src/backtesting/monte_carlo.py`: remuestrea las operaciones del
  backtest para ver qué tan sensible es el resultado al ORDEN en que
  cayeron. Asume ~10 posiciones concurrentes (configurable con
  `--position-size-pct`) — sin esto, componer el retorno completo de
  cada operación como si fuera el 100% de la cuenta da números sin
  sentido (lo verificamos: literalmente millones de %, bug real que
  corregimos).
- `src/backtesting/stress_test.py`: 2 pruebas — comisión/slippage 3x-5x
  más altos, y la peor caída real de SPY DENTRO de los datos
  descargados (calculada, no asumida). Con ~5 años de historia no
  cubre crisis mayores (2008, COVID 2020) — se documenta, no se finge
  cobertura que no existe.

Ver `docs/adr/0003-buckets-y-escalamiento.md` para la definición
completa y la regla de cuándo se le inyecta más capital al bucket de
Riesgo Alto (cuando el rendimiento total anualizado llegue a ≥10% —
condición documentada pero que todavía no se puede evaluar
automáticamente, porque requiere valuación de portafolio en vivo que
no existe hasta Fase 6).

`src/portfolio/allocation.py` es un libro de **contribuciones** (cuánto
le has inyectado a cada bucket), no un portafolio con valuación en
vivo — eso requiere Postgres y reconciliación real (Fase 1+). El
screener diario (`src/screening/daily_signals.py`) opera sobre
Mediano Plazo y Riesgo Alto (`--bucket`), cada uno con su propio
universo y nivel de riesgo.

**No ejecuta nada.** Te dice qué símbolos cumplen la regla hoy y
cuánto comprar respetando el 1% de riesgo máximo por operación — tú
decides y ejecutas manualmente en tu broker.

## Estructura

```
src/
  data/          # descarga y normalización de OHLCV
  indicators/    # SMA, RSI, ATR, volumen
  strategies/    # reglas de señal (trend_following.py)
  backtesting/   # motor de backtest sobre vectorbt
data/
  raw/           # parquet crudo descargado (no se versiona)
  processed/     # parquet con indicadores (no se versiona)
tests/           # pytest
docs/            # vision.md (arquitectura objetivo) y roadmap.md
```

## Por qué no empezamos con la arquitectura completa

El documento de visión (`docs/vision.md`) describe una plataforma de
nivel profesional: Clean Architecture, 7+ módulos, Postgres con 15
tablas, 4 modos de ejecución, integración a broker real. Construir
eso antes de saber si la estrategia funciona es invertir semanas en
infraestructura para una idea no validada. Este MVP prueba el
concepto primero; la arquitectura completa se construye incrementalmente
a partir de la Fase 1 del roadmap, una vez que haya evidencia de que
vale la pena.

## Advertencia

Este es un proyecto de investigación personal. Ninguna estrategia
aquí se presenta como rentable sin evidencia de backtest. No hay
ejecución de dinero real habilitada en esta fase.
