# LOG — EXP-003

Registro cronológico. Se agrega una entrada por sesión de trabajo,
incluyendo lo que no funcionó — mismo estándar que el LOG.md de
pulso-research-lab.

## 2026-11-18 — Pre-registro

Se escribió `PREREGISTRATION.md`: alcance (configuración de producción
exacta de los 3 buckets, ADR 0027), 7 capas con criterio
VALIDATED/REJECTED/INCONCLUSIVE fijado antes de correr nada, orden de
ejecución (Capa 1 y 7 primero por reutilizar infraestructura ya
existente; Capa 2 al final por incertidumbre de datos point-in-time).

Sin ejecutar todavía ninguna capa. Siguiente paso: Capa 1
(walk-forward rolling baseline, sin filtros) sobre las 3
estrategias/buckets de producción.

## 2026-11-18 — Capa 1 y Capa 7

**Bug encontrado y corregido antes de poder correr nada**: al mover
`exploracion_2026_11/` a `research/2026-11-filtros-sizing-adr0033/`
(ADR 0041), el `ROOT` de `harness.py` quedó apuntando un nivel arriba
de lo correcto (`parents[1]` en vez de `parents[2]`, porque el archivo
ahora vive un nivel más anidado) — corregido en el mismo commit de
esta entrada.

**Capa 1** (`capa1_walkforward.py`): walk-forward rolling SIN filtro
sobre las 3 estrategias de producción. Resultado: **los 3 buckets
INCONCLUSIVE** — largo_plazo y riesgo_alto por ventanas con <10
operaciones, mediano_plazo por quedar exactamente en 3/5 ventanas
positivas. Ver `CAPA-1-walk-forward.md` para el detalle y la nota de
comparabilidad con ADR 0015/0016 (métricas y ventanas de tiempo
distintas, no se fuerza una reconciliación numérica).

**Capa 7** (`capa7_ejecucion.py`): fill al open del día siguiente +
2x fricción, sobre todo el período disponible (2021-2026). Resultado:
**largo_plazo REJECTED** (Sharpe 0.78→-0.09, retorno +45.96%→-9.28%,
inspeccionado a mano, no es bug — sensibilidad real del stop-loss a
slippage de ejecución en una ventana de alta volatilidad real de abril
2025); **mediano_plazo y riesgo_alto VALIDATED** (ambos se degradan a
más de la mitad del Sharpe pero se mantienen netos positivos). Ver
`CAPA-7-ejecucion.md`.

Suite completa: 249/249 (sin cambios de producción). Pendiente:
Capa 6 (perturbación de parámetros), después Capa 4 (placebo).
