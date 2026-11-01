# ADR 0017 — Red de seguridad para saltos de equity sospechosos

## Contexto

ADR 0014 documentó un bug real de producción: al migrar
`BENCHMARK_SYMBOL` de `"SPY"` a `"BLEND_SPY_GLD"`, el campo persistido
`bench_shares` (antes en unidades de acciones literales de SPY) se
reinterpretó sin migrar como "unidades del nuevo índice sintético",
provocando una caída de equity de -75% en un solo tick en Riesgo Alto.
No fue un movimiento real de mercado — fue un bug de unidades.

Ese bug se detectó por revisión manual antes de llegar a producción,
no por ninguna alarma automática. Como el motor corre de forma
desatendida (Routines programadas, sin sesión humana escuchando en
tiempo real), un bug de la misma clase podría pasar desapercibido por
días si vuelve a ocurrir (ej. al agregar un nuevo benchmark o cambiar
la semántica de otro campo persistido en el futuro).

## Decisión

Se agregan dos capas de defensa, ninguna de las cuales bloquea el
pipeline (un movimiento real extremo de mercado es posible, aunque
raro, y el motor debe seguir corriendo):

1. **Test de regresión** (`tests/test_paper_trading_engine.py`):
   `test_bench_shares_round_trip_preserves_dollar_value` — verifica
   que, al inicializar un bucket, el valor en dólares de
   `bench_shares` (marcado a mercado con el precio de HOY del mismo
   benchmark) coincida con el capital invertido. Si en el futuro se
   cambia `BENCHMARK_SYMBOL` o la semántica de `bench_shares` sin una
   migración explícita, esta prueba debe fallar antes de llegar a
   producción.

2. **Red de seguridad en tiempo de ejecución** (`engine.py`,
   `run_daily_tick`): compara el equity de cada bucket antes/después
   de cada tick. Si el cambio en un solo día supera 25% (umbral
   elegido porque ningún escenario de mercado real documentado en este
   proyecto — incluyendo el crash real de abril 2025 medido en ADR
   anteriores, -12% en SPY en un día — se acerca a ese nivel para una
   cartera diversificada en 3 buckets), imprime y registra una alerta
   explícita en `snapshot["alertas"]`, sin bloquear el guardado de
   estado ni el resto del pipeline. `run_daily_tick.py` (CLI) imprime
   esas alertas de forma visible al final de la ejecución.

## Por qué no bloquear

Los circuit breakers de ADR 0008 ya cubren el caso de "drawdown real
que amerita pausar nuevas entradas" — ese mecanismo es independiente
y sigue intacto. Esta red de seguridad es para un caso distinto: un
bug de software que produce un número de equity que no corresponde a
ningún movimiento real de mercado. Bloquear el pipeline ante esa
alerta tendría el mismo costo que el bug mismo (el sistema deja de
correr desatendido); el objetivo aquí es solo que el bug sea visible
de inmediato — en la salida del día en que ocurre, no días después —
en vez de depender de que alguien lo note revisando `state.json` a mano.

## Estado

Verificado: `python -m pytest -q` → 60 passed. Tick real corrido sin
alertas (equity sano, consistente con el estado committeado
anteriormente). Sin cambios de comportamiento para el caso normal —
solo instrumentación adicional.
