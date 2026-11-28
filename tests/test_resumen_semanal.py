import pandas as pd

from src.reports import resumen_semanal as rs


def _cierres():
    idx = pd.to_datetime(["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27"])
    return {"AAA": pd.Series([10.0, 11.0, 12.0, 9.0], index=idx), "BBB": pd.Series([20.0, 20.0, 22.0, 22.0], index=idx)}, idx


def test_dias_de_la_semana_toma_lunes_a_viernes_de_la_semana_del_fin():
    _, idx = _cierres()
    assert [d.strftime("%m-%d") for d in rs.dias_de_la_semana(idx, "2026-11-27")] == ["11-23", "11-24", "11-25", "11-27"]


def test_pnl_diario_compra_mantenida_y_venta():
    cierres, idx = _cierres()
    dias = list(idx[1:])  # 24, 25, 27
    posiciones = [
        {"bucket": "largo_plazo", "symbol": "AAA", "shares": 2, "entry_date": "2026-11-24", "entry_price": 10.5,
         "exit_date": "2026-11-27", "exit_price": 9.5},
        {"bucket": "largo_plazo", "symbol": "BBB", "shares": 1, "entry_date": "2026-11-20", "entry_price": 19.0,
         "exit_date": None, "exit_price": None},
    ]
    por_dia = rs.filas_por_dia(posiciones, cierres, dias, idx)

    compra = next(f for f in por_dia["2026-11-24"] if f["symbol"] == "AAA")
    assert compra["accion"] == "comprada"
    assert compra["pnl_usd"] == 1.0  # 2 * (11.0 - 10.5): referencia = precio de entrada

    mantenida = next(f for f in por_dia["2026-11-25"] if f["symbol"] == "BBB")
    assert mantenida["accion"] == "mantenida"
    assert mantenida["pnl_usd"] == 2.0  # 22 - 20 (cierre previo)

    venta = next(f for f in por_dia["2026-11-27"] if f["symbol"] == "AAA")
    assert venta["accion"] == "vendida"
    assert venta["pnl_usd"] == -5.0  # 2 * (9.5 - 12.0): usa el precio de salida real, no el cierre


def test_activos_de_la_semana_pnl_total_desde_la_entrada():
    cierres, idx = _cierres()
    dias = list(idx)
    posiciones = [{"bucket": "riesgo_alto", "symbol": "BBB", "shares": 1, "entry_date": "2026-11-20",
                   "entry_price": 19.0, "exit_date": None, "exit_price": None}]
    por_dia = rs.filas_por_dia(posiciones, cierres, dias, idx)
    filas = rs.activos_de_la_semana(posiciones, cierres, dias, por_dia)
    assert filas[0]["pnl_total_usd"] == 3.0  # 22 - 19
    assert filas[0]["estado"] == "abierta"


def test_activos_de_la_semana_cambio_ultimo_dia_y_semana():
    cierres, idx = _cierres()
    dias = list(idx[1:])  # 24, 25, 27; el día previo a la semana es el 23 (cierre 20.0 para BBB)
    posiciones = [
        {"bucket": "riesgo_alto", "symbol": "BBB", "shares": 1, "entry_date": "2026-11-20", "entry_price": 19.0,
         "exit_date": None, "exit_price": None},
        {"bucket": "riesgo_alto", "symbol": "AAA", "shares": 1, "entry_date": "2026-11-25", "entry_price": 12.0,
         "exit_date": None, "exit_price": None},
    ]
    por_dia = rs.filas_por_dia(posiciones, cierres, dias, idx)
    filas = {f["symbol"]: f for f in rs.activos_de_la_semana(posiciones, cierres, dias, por_dia, idx)}
    assert filas["BBB"]["cambio_ultimo_dia_pct"] == 0.0           # 22 -> 22 el último día
    assert filas["BBB"]["cambio_semana_pct"] == 10.0              # 22 contra el cierre previo a la semana (20)
    assert filas["AAA"]["cambio_semana_pct"] == -25.0             # comprada en la semana: 9 contra su precio de compra 12


def test_borrar_semanas_anteriores_conserva_solo_la_ultima(tmp_path):
    for nombre in ("2026-11-20.json", "2026-11-27.json", "otro.json"):
        (tmp_path / nombre).write_text("{}")
    borradas = rs.borrar_semanas_anteriores(tmp_path / "2026-11-27.json")
    assert [b.name for b in borradas] == ["2026-11-20.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-11-27.json", "otro.json"]
