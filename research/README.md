# research/

Código de investigación exploratoria — nunca se ejecuta en producción,
nunca lo importa `engine.py`/`live_engine.py`/`daily_signals.py`. A
diferencia de la convención anterior (`exploracion_2026_11/`,
gitignored — ver ADR 0033/0040), **esto sí se versiona en git** desde
ADR 0041: el costo de no poder volver a verificar un hallazgo pasado
resultó mayor que el costo de commitear un script de investigación.

Convención: una carpeta por investigación, `research/<AAAA-MM>-<slug-corto>/`,
nombrada por cuándo se hizo y qué investigó (ej.
`research/2026-11-filtros-sizing-adr0033/`). El hallazgo persistente
de cada investigación sigue siendo su ADR correspondiente en
`docs/adr/` — esta carpeta es el código que lo produjo, para que un
hallazgo futuro se pueda verificar contra el mismo código, no solo
contra la prosa del ADR.

Qué SÍ versionar aquí: scripts de análisis, el harness/filtros que se
probaron, resultados pequeños (JSON/CSV de métricas agregadas — no
datos de precio crudos, esos siguen en `data/` gitignored). Qué NO:
nada que el motor de producción importe o ejecute.
