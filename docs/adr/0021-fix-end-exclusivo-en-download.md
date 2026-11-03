# ADR 0021 — `yfinance` trata `end` como exclusivo: el cierre de hoy nunca se descargaba

## Contexto

El mismo día que se corrigió ADR 0020 (blend incremental), la Routine
"después del cierre" volvió a correr sin avanzar el día real: a las
21:31 UTC (3:31 PM CDMX, ya pasado el cierre de mercado) seguía
procesando el 2-nov en vez del 3-nov.

Diagnóstico: `yfinance.download(start=..., end=...)` trata `end` como
**exclusivo** — los datos devueltos van hasta el día ANTERIOR a `end`,
nunca incluyen `end` mismo. `src/data/download.py` fijaba
`end = datetime.today()`, así que el cierre del día de HOY nunca
quedaba incluido en la descarga, sin importar a qué hora se corriera.

## Impacto real

Este bug es **anterior** a todo lo demás documentado en estos ADRs —
probablemente estuvo presente desde el inicio del proyecto. No se
había notado porque:

- La corrida "antes de la apertura" nunca necesitó el cierre de hoy
  (procesa el cierre de AYER, que sí llegaba completo).
- La corrida "después del cierre" **sí** lo necesitaba, pero al
  reusar el mismo día ya presente (ayer), el motor seguía
  funcionando sin error — solo quedaba silenciosamente un día atrás
  de lo que debía, todos los días, indefinidamente.

Es decir: la corrida de la tarde nunca cumplió su propósito real de
usar el cierre confirmado del mismo día — en la práctica se comportó
exactamente igual que la de la mañana, sin que nada lo señalara.

## Decisión

`src/data/download.py` ahora calcula `end = hoy + timedelta(days=1)`
(extraído a una función testeable, `rango_de_fechas()`), para que el
límite exclusivo caiga un día después de hoy y el cierre de hoy sí
quede incluido. Verificado con datos reales: antes del fix, SPY traía
500 filas (hasta 2-nov); después del fix, 501 filas (incluye 3-nov,
confirmado también vía consulta directa a `yfinance` con
`period="5d"`, que sí mostraba el cierre de hoy desde el principio —
el bug estaba en el cálculo de rango de este repo, no en
`yfinance`).

Se agregó `tests/test_download.py` con un test de regresión directo
sobre `rango_de_fechas()`.

## Relación con ADR 0020

Son dos bugs independientes que se manifestaron la misma semana:
ADR 0020 es sobre CÓMO se calcula el precio del benchmark a partir de
los datos ya descargados; este ADR es sobre que los datos descargados
nunca llegaban a incluir el día de hoy en primer lugar. Corregir solo
uno de los dos no habría resuelto el problema completo de "las
Routines no avanzan" — hacía falta ambos.
