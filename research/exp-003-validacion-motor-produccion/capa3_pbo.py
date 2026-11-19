"""EXP-003 — Capa 3, parte 2: PBO (Combinatorially Symmetric
Cross-Validation) sobre el conjunto de variantes re-simulables.

Fuente de datos: research/2026-11-filtros-sizing-adr0033/results/
baseline_y_filtros.json — 3 configuraciones (baseline, trend_efficiency,
correlation_adjusted) × 3 buckets × 5 ventanas con Sharpe por ventana,
ya producidas y auto-verificadas en ADR 0040 (no se re-corre el
backtest, se reusa ese resultado tal cual).

Método CSCV (Bailey, Borwein, López de Prado, Zhu 2016): para cada
partición de las 5 ventanas en un subconjunto "in-sample" (IS) y su
complemento "out-of-sample" (OOS), se elige la configuración con mejor
Sharpe promedio IS, y se registra si esa misma configuración queda en
la mitad INFERIOR por Sharpe promedio OOS (c < 0, "underperformance").
PBO = fracción de particiones donde el ganador IS cae en la mitad
inferior OOS — cuanto más alto, más probable que el resultado sea
producto de sobreajuste (elegir la config correcta en papel) en vez de
una ventaja real que se sostenga fuera de muestra.

Con 5 ventanas, se usan todas las C(5,2)=10 formas de elegir un
subconjunto de 2 ventanas como IS (y las 3 restantes como OOS) — y
también las 10 formas de elegir 3 como IS (y 2 como OOS) — 20
particiones evaluadas en total, cada combinación de tamaño contada
por separado para no favorecer IS chico ni grande."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

RESULT_DIR = Path(__file__).resolve().parent
FUENTE = RESULT_DIR.parent / "2026-11-filtros-sizing-adr0033" / "results" / "baseline_y_filtros.json"


def pbo_de_bucket(variantes: dict[str, list[dict]]) -> dict:
    nombres = list(variantes.keys())
    n_ventanas = len(next(iter(variantes.values())))
    sharpe_por_variante_y_ventana = {
        nombre: [w["sharpe"] for w in sorted(filas, key=lambda w: w["window"])]
        for nombre, filas in variantes.items()
    }

    particiones_evaluadas = 0
    underperformance = 0
    detalle = []

    for tam_is in range(2, n_ventanas - 1):  # deja al menos 1 ventana OOS, al menos 2 IS
        for is_idx in itertools.combinations(range(n_ventanas), tam_is):
            oos_idx = [i for i in range(n_ventanas) if i not in is_idx]
            if not oos_idx:
                continue
            media_is = {
                nombre: sum(sharpe_por_variante_y_ventana[nombre][i] for i in is_idx) / len(is_idx)
                for nombre in nombres
            }
            media_oos = {
                nombre: sum(sharpe_por_variante_y_ventana[nombre][i] for i in oos_idx) / len(oos_idx)
                for nombre in nombres
            }
            ganador_is = max(media_is, key=media_is.get)

            ranking_oos = sorted(nombres, key=lambda n: media_oos[n], reverse=True)
            rank_ganador_oos = ranking_oos.index(ganador_is)  # 0 = mejor
            mitad_inferior = rank_ganador_oos >= len(nombres) / 2

            particiones_evaluadas += 1
            if mitad_inferior:
                underperformance += 1

            detalle.append({
                "ventanas_is": [i + 1 for i in is_idx],
                "ventanas_oos": [i + 1 for i in oos_idx],
                "ganador_is": ganador_is,
                "rank_ganador_en_oos": rank_ganador_oos + 1,
                "de": len(nombres),
                "cuenta_como_overfitting": mitad_inferior,
            })

    pbo = underperformance / particiones_evaluadas if particiones_evaluadas else None
    return {
        "variantes_comparadas": nombres,
        "particiones_evaluadas": particiones_evaluadas,
        "veces_ganador_is_cae_en_mitad_inferior_oos": underperformance,
        "pbo": round(pbo, 4) if pbo is not None else None,
        "detalle": detalle,
    }


def main() -> dict:
    data = json.loads(FUENTE.read_text())
    salida = {}
    for bucket, variantes in data.items():
        resultado = pbo_de_bucket(variantes)
        salida[bucket] = resultado
        print(f"\n--- {bucket} ---")
        print(f"Variantes comparadas: {resultado['variantes_comparadas']}")
        print(f"Particiones evaluadas: {resultado['particiones_evaluadas']}")
        print(f"PBO = {resultado['pbo']}")

    out_path = RESULT_DIR / "resultados_capa3_pbo.json"
    out_path.write_text(json.dumps(salida, indent=2, ensure_ascii=False))
    print(f"\nGuardado en {out_path}")
    return salida


if __name__ == "__main__":
    main()
