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
# 1. Descargar datos históricos
python -m src.data.download --universe config/universe.txt --years 5

# 2. Calcular indicadores
python -m src.indicators.compute

# 3. Calcular fuerza relativa vs. benchmark (requiere SPY en el universo)
python -m src.indicators.relative_strength --benchmark SPY

# 4. Correr backtest de una estrategia
python -m src.backtesting.run --strategy trend_following
python -m src.backtesting.run --strategy momentum_breakout

# 5. Walk-forward: la misma estrategia en N ventanas consecutivas,
#    para ver si el rendimiento es consistente o depende de un período
python -m src.backtesting.walk_forward --strategy trend_following --windows 4

# 6. Registra el capital que vas inyectando (se reparte 40/30/20/10
#    entre los 4 buckets — ver docs/vision.md "Reparto de capital")
python -m src.portfolio.allocation inject 1000

# 7. Screener diario: qué símbolos cumplen HOY las condiciones de
#    entrada, y cuánto comprar según el 1% de riesgo máximo. Requiere
#    haber corrido 1-3 el mismo día para tener datos frescos.
python -m src.screening.daily_signals --bucket mediano_plazo
```

## Reparto de capital (4 buckets)

| Bucket | % | Estado |
|---|---|---|
| Largo plazo | 40% | Sin estrategia todavía (propuesta: buy & hold en ETFs amplios) |
| Mediano plazo | 30% | **Único bucket con estrategia real** — Trend Following + Momentum/Breakout (swing trading) |
| Riesgo alto | 20% | Sin definir (propuesta: mismo tipo de estrategia sobre small/mid caps) |
| Muy alta volatilidad | 10% | Sin definir (propuesta: criptomonedas, requiere su propio motor de datos) |

`src/portfolio/allocation.py` es un libro de **contribuciones** (cuánto
le has inyectado a cada bucket), no un portafolio con valuación en
vivo — eso requiere Postgres y reconciliación real (Fase 1+). El
screener diario (`src/screening/daily_signals.py`) solo opera sobre
el bucket de Mediano Plazo, que es el único con estrategia construida.

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
