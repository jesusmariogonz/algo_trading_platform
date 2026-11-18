# ADR 0041 — El código de investigación exploratoria se versiona (deja de gitignorarse)

## Contexto

ADR 0033 estableció la convención de que el código de investigación
exploratoria (walk-forward de hipótesis que NUNCA tocan producción)
vive en `exploracion_2026_11/`, gitignored, con el ADR correspondiente
como único registro persistente: "el código en sí puede perderse si
el contenedor de una sesión termina". Esa pérdida ya pasó una vez sin
consecuencia real (ADR 0025, barrido de Bollinger %B — el resultado
fue "descartar", y perder el código de algo descartado no cuesta
nada).

ADR 0040 es el caso donde sí costó: al investigar el mecanismo de los
2 candidatos pendientes de ADR 0033 (trend efficiency ratio,
correlation-adjusted sizing), el código original ya no existía y hubo
que reconstruirlo desde la prosa del ADR. La reconstrucción **no pasó
su propia autoverificación** — los Sharpe baseline salieron 2.5-4.5x
más bajos que los publicados, y el signo de 2 de las 6 relaciones
bucket×filtro documentadas (justo las dos rupturas que motivaron la
pregunta) no se logró reproducir. Sin el código original no hay forma
de distinguir "la reconstrucción tiene un detalle distinto" de "el
hallazgo original era frágil" — la pregunta de negocio (¿implementar
alguno de los 2 candidatos?) quedó sin poderse responder con
confianza, por una razón enteramente evitable.

## Decisión

Se deja de gitignorar el código de investigación exploratoria.
Convención nueva: `research/<AAAA-MM>-<slug>/` (ver
`research/README.md`), versionado en git como cualquier otro código
del repo. `exploracion_2026_11/.gitignore` se elimina del
`.gitignore`; el contenido producido para ADR 0040 ya se movió a
`research/2026-11-filtros-sizing-adr0033/` y queda commiteado junto
con esta decisión.

Esto NO cambia nada más: sigue siendo código que nunca se ejecuta en
producción, nunca lo importa `engine.py`/`live_engine.py`/
`daily_signals.py`, y el ADR correspondiente sigue siendo el resumen
que se lee primero — el código versionado es un respaldo para poder
re-verificar, no el documento principal.

ADR 0033/0040 no se reescriben — describen correctamente la
convención que estaba vigente cuando se escribieron.

## Consecuencias

- Costo: algunos KB más en el repo por investigación (en ADR 0040,
  ~14KB de código + resultados). Insignificante frente al costo de no
  poder re-verificar una decisión sobre dinero real.
- Beneficio: cualquier hallazgo futuro de este tipo se puede volver a
  correr, auditar o extender directamente, sin reconstrucción de buena
  fe ni la incertidumbre que eso introduce.
- Pendiente (no se hace en este ADR): no hay plan de rescatar el
  código ya perdido de investigaciones anteriores a ADR 0040
  (incluyendo la de ADR 0033 original) — esta decisión aplica hacia
  adelante.
