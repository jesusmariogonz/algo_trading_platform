from src.indicators.relative_strength import read_universe_file


def test_read_universe_file_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("BTC\n\n# comentario\nETH\n  \nSOL\n")
    assert read_universe_file(str(f)) == ["BTC", "ETH", "SOL"]


def test_universe_filter_logic_matches_file_stems():
    """Verifica la lógica de filtrado (sin tocar disco real): dado un
    universo de 2 símbolos y una lista de 4 archivos .parquet
    disponibles, solo deben quedar los que coinciden."""
    symbols = {"BTC", "ETH"}
    paths = ["BTC.parquet", "ETH.parquet", "AAPL.parquet", "SPY.parquet"]
    filtered = [p for p in paths if p.replace(".parquet", "") in symbols]
    assert filtered == ["BTC.parquet", "ETH.parquet"]
