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
- Implementa la Estrategia A (Trend Following) como reglas de
  señal, configurables.
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

# 3. Correr backtest de la Estrategia A
python -m src.backtesting.run --strategy trend_following
```

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
