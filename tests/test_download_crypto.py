from src.data.download_crypto import KRAKEN_PAIR_MAP, read_universe


def test_all_universe_symbols_have_a_kraken_pair(tmp_path):
    universe_file = tmp_path / "universe_cripto.txt"
    universe_file.write_text("BTC\nETH\n# comentario\nSOL\n")
    symbols = read_universe(str(universe_file))
    assert symbols == ["BTC", "ETH", "SOL"]
    for s in symbols:
        assert s in KRAKEN_PAIR_MAP


def test_default_universe_file_symbols_all_mapped():
    with open("config/universe_cripto.txt") as f:
        symbols = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    faltantes = [s for s in symbols if s not in KRAKEN_PAIR_MAP]
    assert faltantes == [], f"Símbolos sin par de Kraken: {faltantes}"
