from datetime import datetime

from src.data.download import rango_de_fechas


def test_rango_de_fechas_incluye_el_dia_de_hoy():
    """Regresión del bug real de ADR 0021: yfinance trata `end` como
    EXCLUSIVO. Si `end` se fija exactamente a "hoy", el cierre de HOY
    nunca se descarga — esto dejaba silenciosamente a la corrida
    "después del cierre" tan desactualizada como la de "antes de la
    apertura" desde siempre, sin que ningún error lo delatara."""
    hoy = datetime(2026, 11, 3)
    start, end = rango_de_fechas(hoy, years=2)
    assert end > hoy  # el límite exclusivo debe quedar DESPUÉS de hoy
    assert end.date() == datetime(2026, 11, 4).date()


def test_rango_de_fechas_respeta_los_anios_pedidos():
    hoy = datetime(2026, 11, 3)
    start, end = rango_de_fechas(hoy, years=2)
    dias_de_historia = (end - start).days
    assert 729 <= dias_de_historia <= 731  # ~2 años, tolerando años bisiestos
