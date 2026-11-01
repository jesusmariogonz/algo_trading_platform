# ADR 0013 — Descarta ampliar a semiconductores/defensa; oro como cash holder queda pendiente de decisión

## Estado
Aceptado (descarte de semis/defensa). Candidato de oro como cash holder
**documentado, no decidido** — queda explícitamente pendiente.

## Contexto
A raíz de preguntas del usuario sobre exposición a semiconductores/IA/
tecnología armamentista, y sobre usar oro como destino del cash ocioso
en vez de (o junto a) SPY, se probaron ambos candidatos con una
descarga de datos única y congelada (ver corrección de reproducibilidad
en ADR 0012), 36 meses, fricción real, riesgo subido + sizing sobre
equity actual (configuración de producción vigente).

## Resultado medido (datos congelados, comparables entre sí)

| Escenario | Retorno neto | Drawdown máximo |
|---|---|---|
| Control (SPY, universo actual de producción) | +22.07% | 13.63% |
| + Semiconductores/Defensa (TSM, SMH, GD, NOC, LHX) | +16.05% | 13.63% |
| Oro (GLD) como cash holder en vez de SPY | +17.53% | **12.22%** |

## Decisión 1 — Semiconductores/Defensa: DESCARTADO
Agregar TSM, SMH (semiconductores) y GD, NOC, LHX (defensa) al universo
bajó el retorno (22.07%→16.05%) sin reducir el drawdown. El sistema ya
tenía exposición razonable a estos sectores vía NVDA/AVGO/AMD/XLK
(semiconductores) y LMT/RTX/PLTR (defensa, parcial) — los símbolos
nuevos no aportaron señales de calidad adicionales en este universo y
período, solo diluyeron el resultado. No se agregan a producción.

## Decisión 2 — Oro (GLD) como cash holder: PENDIENTE, no se decide aquí
Oro sí mostró un trade-off real y mejor que las alternativas probadas
antes (blend SPY/AGG, SGOV — ver ADR 0012): reduce el drawdown de
13.63% a 12.22% a cambio de sacrificar retorno de 22.07% a 17.53%. Es
una compensación más razonable que el blend de bonos, pero sigue
siendo sacrificar ~4.5 puntos de retorno por ~1.4 puntos menos de
drawdown — no es un cambio "gratis".

**Esta decisión se deja explícitamente pendiente** porque depende del
apetito de riesgo del usuario (igual que ADR 0012), no de qué número es
matemáticamente "mejor" — ambas opciones (quedarse en SPY, o mover a
GLD) son defendibles según qué se priorice.

## Qué NO se tocó
- Ningún criterio de entrada de las estrategias.
- `config/universe*.txt` de producción sin cambios (ni semis/defensa ni
  nada más se agregó).
- El cash ocioso se queda 100% en SPY en producción — GLD no se activó.

## Pendiente
- Decisión explícita del usuario sobre oro como cash holder (o una
  mezcla SPY/GLD, no probada todavía, que podría dar un punto
  intermedio entre ambos extremos).
- El pipeline de descarga de datos (`src/data/download.py`) no cachea
  resultados entre corridas — cada análisis exploratorio debe
  recordar descargar una sola vez y no volver a pedir datos a mitad de
  una comparación (ver ADR 0012). Automatizar esto (ej. un modo
  "congelado" explícito para sesiones de backtest comparativo) sería
  una mejora de infraestructura real, no hecha todavía.
