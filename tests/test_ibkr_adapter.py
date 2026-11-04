"""Tests del adapter de IBKR usando un IB falso (sin red, sin Gateway
real) — valida la lógica del adapter en CI; la conexión real contra
Gateway se prueba a mano en la VM (ver docs/adr/0022)."""

import pytest

from src.broker import ibkr_adapter


class _OrderStatusFalso:
    def __init__(self, status: str, avg_fill_price: float = 0.0):
        self.status = status
        self.avgFillPrice = avg_fill_price


class _TradeFalso:
    def __init__(self, status: str, avg_fill_price: float = 0.0, done_after_n_updates: int = 0):
        self.orderStatus = _OrderStatusFalso(status, avg_fill_price)
        self._updates_restantes = done_after_n_updates

    def isDone(self) -> bool:
        return self._updates_restantes <= 0

    def tick(self):
        self._updates_restantes -= 1


class _IBFalso:
    """Simula lo mínimo de ib_async.IB que usa el adapter."""

    def __init__(self, trade: _TradeFalso, cuentas=None, resumen=None, posiciones=None, account_values=None):
        self._trade = trade
        self._cuentas = cuentas if cuentas is not None else ["DUR123456"]
        self._resumen = resumen if resumen is not None else []
        self._posiciones = posiciones if posiciones is not None else []
        self._account_values = account_values if account_values is not None else []

    def accountValues(self):
        return self._account_values

    def qualifyContracts(self, contrato):
        pass

    def placeOrder(self, contrato, orden):
        return self._trade

    def waitOnUpdate(self, timeout=None):
        self._trade.tick()

    def managedAccounts(self):
        return self._cuentas

    def accountSummary(self):
        return self._resumen

    def positions(self):
        return self._posiciones


class _ItemResumenFalso:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value


class _AccountValueFalso:
    def __init__(self, tag, value, currency):
        self.tag = tag
        self.value = value
        self.currency = currency


class _ContratoFalso:
    def __init__(self, symbol, sec_type="STK"):
        self.symbol = symbol
        self.secType = sec_type


class _PosicionFalsa:
    def __init__(self, symbol, shares, sec_type="STK"):
        self.contract = _ContratoFalso(symbol, sec_type)
        self.position = shares


def test_ejecutar_orden_mercado_devuelve_fill_cuando_se_llena():
    trade = _TradeFalso("Filled", avg_fill_price=123.45, done_after_n_updates=2)
    ib = _IBFalso(trade)

    fill = ibkr_adapter.ejecutar_orden_mercado(ib, "AAPL", "BUY", 10)

    assert fill.symbol == "AAPL"
    assert fill.accion == "BUY"
    assert fill.shares == 10
    assert fill.precio_promedio == 123.45


def test_ejecutar_orden_mercado_lanza_error_si_no_se_llena():
    trade = _TradeFalso("Cancelled", done_after_n_updates=1)
    ib = _IBFalso(trade)

    with pytest.raises(ibkr_adapter.OrdenNoLlenada):
        ibkr_adapter.ejecutar_orden_mercado(ib, "AAPL", "BUY", 10)


def test_ejecutar_orden_mercado_rechaza_accion_invalida():
    ib = _IBFalso(_TradeFalso("Filled"))
    with pytest.raises(ValueError):
        ibkr_adapter.ejecutar_orden_mercado(ib, "AAPL", "HOLD", 10)


def test_ejecutar_orden_mercado_rechaza_shares_menor_a_uno():
    ib = _IBFalso(_TradeFalso("Filled"))
    with pytest.raises(ValueError):
        ibkr_adapter.ejecutar_orden_mercado(ib, "AAPL", "BUY", 0)


def test_cuenta_activa_devuelve_la_primera_cuenta_administrada():
    ib = _IBFalso(_TradeFalso("Filled"), cuentas=["DUR328470"])
    assert ibkr_adapter.cuenta_activa(ib) == "DUR328470"


def test_cuenta_activa_lanza_error_si_no_hay_cuentas():
    ib = _IBFalso(_TradeFalso("Filled"), cuentas=[])
    with pytest.raises(RuntimeError):
        ibkr_adapter.cuenta_activa(ib)


def test_equity_de_cuenta_lee_net_liquidation():
    resumen = [
        _ItemResumenFalso("TotalCashValue", "1000.00"),
        _ItemResumenFalso("NetLiquidation", "1866.36"),
    ]
    ib = _IBFalso(_TradeFalso("Filled"), resumen=resumen)
    assert ibkr_adapter.equity_de_cuenta(ib) == 1866.36


def test_equity_de_cuenta_lanza_error_si_falta_net_liquidation():
    ib = _IBFalso(_TradeFalso("Filled"), resumen=[])
    with pytest.raises(RuntimeError):
        ibkr_adapter.equity_de_cuenta(ib)


def test_equity_de_cuenta_usd_lee_net_liquidation_by_currency_en_usd():
    account_values = [
        _AccountValueFalso("NetLiquidationByCurrency", "18866.36", "MXN"),
        _AccountValueFalso("NetLiquidationByCurrency", "1023.45", "USD"),
        _AccountValueFalso("NetLiquidationByCurrency", "1050.00", "BASE"),
    ]
    ib = _IBFalso(_TradeFalso("Filled"), account_values=account_values)
    assert ibkr_adapter.equity_de_cuenta_usd(ib) == 1023.45


def test_equity_de_cuenta_usd_lanza_error_si_no_hay_desglose_en_usd():
    account_values = [_AccountValueFalso("NetLiquidationByCurrency", "18866.36", "MXN")]
    ib = _IBFalso(_TradeFalso("Filled"), account_values=account_values)
    with pytest.raises(RuntimeError):
        ibkr_adapter.equity_de_cuenta_usd(ib)


def test_posiciones_reales_agrupa_por_symbol_y_filtra_no_acciones():
    posiciones = [
        _PosicionFalsa("AAPL", 10),
        _PosicionFalsa("AAPL", 5),
        _PosicionFalsa("MSFT", 3),
        _PosicionFalsa("GLD", 2, sec_type="CASH"),  # no es STK, se ignora
    ]
    ib = _IBFalso(_TradeFalso("Filled"), posiciones=posiciones)

    out = ibkr_adapter.posiciones_reales(ib)

    assert out == {"AAPL": 15, "MSFT": 3}
