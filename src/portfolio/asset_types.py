"""Clasificación simple de símbolo -> tipo de activo, para mostrar en
el dashboard (ver ADR 0037). No hay ninguna fuente de datos que ya
traiga esto en el proyecto — es un mapeo manual mantenido a mano,
cubriendo los símbolos reales de los 3 universos (config/universe*.txt).
Un símbolo nuevo que no esté aquí cae en "Stock" por default (la
mayoría de los universos son acciones individuales o ETFs de renta
variable, así que es el default más razonable, no un placeholder
vacío)."""

from __future__ import annotations

ETF_RENTA_VARIABLE = {
    "SPY", "QQQ", "VTI", "DIA", "IWM", "EFA", "VWO", "IJH", "IJR",
    "EEM", "EWJ", "FXI", "SCZ", "VNQ", "VNQI", "XLK", "XLF", "XLE",
    "XLV", "XLY", "XLP", "XLI",
}
ETF_BONOS = {"AGG", "TLT", "SHY", "LQD", "HYG", "MUB", "EMB"}
COMMODITY = {"GLD", "SLV", "USO", "DBC"}
CRIPTO = {"BTC", "ETH", "XRP"}


def asset_type_de(symbol: str) -> str:
    if symbol in COMMODITY:
        return "Commodity"
    if symbol in ETF_BONOS:
        return "Bond ETF"
    if symbol in ETF_RENTA_VARIABLE:
        return "Equity ETF"
    if symbol in CRIPTO:
        return "Crypto"
    return "Stock"
