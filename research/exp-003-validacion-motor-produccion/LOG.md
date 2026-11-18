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
