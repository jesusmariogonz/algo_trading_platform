# ADR 0015 — Validación oficial de la configuración actual de producción

## Estado
Aceptado. **Este documento reemplaza todas las cifras de retorno
mencionadas en ADR 0011, 0012 y 0013 como la referencia del proyecto**
— esas cifras quedan como registro histórico de versiones anteriores
del sistema o de corridas con el bug de reproducibilidad ya corregido
(ver corrección en ADR 0012), no como el número vigente.

## Contexto
A lo largo de ADR 0011-0014 se reportaron varios números de retorno
(+32.76%, +37.21%, +48.25%, +22.07%, +17.53%), cada uno correspondiente
a una combinación distinta de configuración y/o momento de descarga de
datos — lo cual generó confusión real sobre cuál era "el" número del
sistema. Se corrió una validación única, oficial, con:

- La configuración EXACTA que está en producción hoy (sin variantes,
  sin candidatos descartados): 146 símbolos, riesgo 2%/2%/3%, sizing
  sobre equity actual, cash ocioso en blend 50% SPY / 50% GLD, fricción
  real.
- Una descarga de datos única y congelada (sin volver a pedir datos
  entre pasos), eliminando el problema de reproducibilidad de ADR 0012.

## Resultado oficial (36 meses, nov 2023 - oct 2026)

| Métrica | Valor |
|---|---|
| Operaciones cerradas | 216 |
| Retorno neto acumulado | **+31.07%** |
| **Retorno anualizado compuesto** | **≈9.44% anual** |
| Drawdown máximo | 13.83% (8-abr-2025) |

Por bucket:

| Bucket | Retorno | Operaciones |
|---|---|---|
| Largo Plazo | +8.40% | 40 |
| Mediano Plazo | +45.91% | 86 |
| Riesgo Alto | +51.96% | 90 |

## Por qué esta cifra es la que se usa de ahora en adelante
Es la única corrida que combina las tres condiciones necesarias para
ser confiable: (1) la configuración real de producción, sin mezclar
candidatos descartados ni versiones intermedias; (2) datos de una sola
descarga, sin el problema de revisión de precios de yfinance entre
pasos; (3) metodología idéntica a la usada en el resto del proyecto
(misma fricción, mismo universo, mismo split de capital).

## Contexto de comparación — para evitar expectativas infladas
Es común ver en plataformas de "copy trading" (ej. eToro) usuarios con
retornos reportados de 40-50% en ventanas cortas. La explicación, sin
excepción en los casos revisados, nunca es una estrategia
estructuralmente superior — es alguna combinación de: sesgo de
supervivencia (solo se muestran los que no se quemaron), apalancamiento
alto (que amplifica tanto ganancias como pérdidas, y las pérdidas
grandes simplemente cierran la cuenta y desaparecen del ranking),
ventanas de tiempo cortas sin walk-forward, y ausencia de reporte de
drawdown junto al retorno. ~9.44% anual compuesto, con drawdown máximo
medido y documentado, es la cifra honesta de este sistema — no se
ajusta para parecerse a esos números.

## Pendiente
- Reconfirmar este número periódicamente según se acumule más historial
  real de paper trading, no solo backtest.
- El pipeline de descarga sigue sin cachear datos entre corridas
  exploratorias (ver pendiente de ADR 0012/0013) — cualquier
  comparación futura de variantes debe repetir este mismo cuidado de
  descarga única congelada.
