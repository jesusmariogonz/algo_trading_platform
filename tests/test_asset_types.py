from src.portfolio.asset_types import asset_type_de


def test_asset_type_de_commodity():
    assert asset_type_de("GLD") == "Commodity"
    assert asset_type_de("USO") == "Commodity"


def test_asset_type_de_bond_etf():
    assert asset_type_de("TLT") == "Bond ETF"


def test_asset_type_de_equity_etf():
    assert asset_type_de("SPY") == "Equity ETF"
    assert asset_type_de("XLK") == "Equity ETF"


def test_asset_type_de_default_es_stock():
    assert asset_type_de("AAPL") == "Stock"
    assert asset_type_de("SIMBOLO_INVENTADO") == "Stock"
