# ADR 0002 — Dónde vive el dashboard privado

## Estado
Propuesto (decisión real pendiente hasta Fase 7).

## Contexto
El usuario quiere ver este sistema desde una zona privada de
`jgonzalez.app` (Next.js en Vercel), con acceso solo para él.

## Decisión propuesta
`jgonzalez.app` y este motor de trading son **dos sistemas separados
que se comunican por API**, no un monolito:

- **Este repo** (`algo_trading_platform`): backend Python, Postgres,
  jobs programados, lógica de estrategia/riesgo/ejecución. Necesita
  cómputo persistente (no serverless) — candidatos: Railway, Fly.io,
  un VPS pequeño (Hetzner/DigitalOcean), o la propia máquina del
  usuario mientras es solo investigación.
- **jgonzalez.app**: agrega una ruta protegida (ej. `/trading`) que
  es **solo lectura** — consume una API expuesta por este backend
  (o lee directo de una vista/tabla de Postgres vía una función
  serverless) y renderiza el dashboard. No ejecuta lógica de trading.
- **Autenticación de la ruta privada:** lo más simple que resuelve el
  caso de un único usuario — middleware de Next.js con verificación
  de una cookie firmada tras login por contraseña, o HTTP Basic Auth
  a nivel de Vercel Edge Middleware. No se necesita un sistema de
  usuarios completo para una sola persona.

## Por qué no un monolito
Vercel serverless no sostiene procesos de larga duración, cron
confiable para jobs pesados, ni una conexión persistente a Postgres
del volumen que este sistema necesitará. Forzarlo ahí generaría
fricción constante. Separar los sistemas es el patrón estándar
incluso en shops de trading pequeños.

## Pendiente
Esta decisión se formaliza en Fase 7 (Monitoring), cuando exista algo
real que mostrar. No bloquea el trabajo de Fase 0-6.
