"""Definición de los 3 "Quant Portfolios" — productos con identidad
propia (Conservative Alpha / Balanced Growth / Aggressive Momentum),
propuestos por el usuario como alternativa al modelo de 4 buckets por
horizonte (src/portfolio/allocation.py, src/paper_trading/engine.py).

AMBOS MODELOS COEXISTEN A PROPÓSITO — decisión explícita del usuario,
no una migración. Este módulo es independiente del de buckets: su
propio universo, su propio motor (src/quant_portfolios/engine.py), su
propio estado (data/quant_portfolios/), sin compartir código de
ejecución con src/paper_trading/engine.py (sí reutiliza indicadores
y utilidades de carga de datos).

Pesos y parámetros son una PROPUESTA DE DISEÑO del usuario, no
resultado de optimización por backtesting — se preservan tal cual los
dio, documentados como hipótesis a validar, no como óptimos.
"""

from dataclasses import dataclass, field


@dataclass
class PortfolioDefinition:
    id: str
    name: str
    tagline: str
    weights: dict[str, float]  # símbolo -> peso objetivo (deben sumar 1.0)
    trend_filter: str  # qué función de filtro de tendencia/momentum usa (ver engine.py)
    rebalance_frequency: str  # "monthly" | "daily" (revisión diaria de la condición de tendencia)
    defensive_scale: float  # peso efectivo = weight * defensive_scale cuando el filtro de tendencia NO pasa
    risk_per_trade_pct: float
    daily_loss_limit_pct: float
    drawdown_review_pct: float
    benchmark: str
    design_volatility_target_pct: tuple[float, float] = field(default=(0.0, 0.0))

    def __post_init__(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Los pesos de {self.id} suman {total}, deben sumar 1.0")


PORTFOLIOS: dict[str, PortfolioDefinition] = {
    "conservative_alpha": PortfolioDefinition(
        id="conservative_alpha",
        name="Conservative Alpha",
        tagline="Preservar capital, crecimiento moderado y menor volatilidad.",
        weights={"SGOV": 0.30, "VOO": 0.25, "BND": 0.20, "VXUS": 0.15, "GLDM": 0.10},
        trend_filter="sma200_momentum6m",
        rebalance_frequency="monthly",
        defensive_scale=0.5,  # pierde tendencia -> se queda con la mitad del peso, no con cero
        risk_per_trade_pct=0.0025,
        daily_loss_limit_pct=0.01,
        drawdown_review_pct=0.06,
        benchmark="VOO",
        design_volatility_target_pct=(6.0, 9.0),
    ),
    "balanced_growth": PortfolioDefinition(
        id="balanced_growth",
        name="Balanced Growth",
        tagline="Crecimiento diversificado con exposición a tendencias.",
        weights={
            "VOO": 0.30, "QQQM": 0.15, "VXUS": 0.15, "BND": 0.15,
            "SGOV": 0.10, "GLDM": 0.10, "IWM": 0.05,
        },
        trend_filter="ma_cross_multi_momentum",
        rebalance_frequency="monthly",
        defensive_scale=0.4,
        risk_per_trade_pct=0.004,
        daily_loss_limit_pct=0.015,
        drawdown_review_pct=0.10,
        benchmark="VOO",
        design_volatility_target_pct=(10.0, 13.0),
    ),
    "aggressive_momentum": PortfolioDefinition(
        id="aggressive_momentum",
        name="Aggressive Momentum",
        tagline="Maximizar participación en tendencias de crecimiento, tecnología, small-caps y cripto.",
        weights={
            "VOO": 0.25, "QQQM": 0.25, "IWM": 0.15, "SMH": 0.10,
            "VXUS": 0.10, "BTC": 0.10, "SGOV": 0.05,
        },
        trend_filter="breakout_ema_confirm",
        rebalance_frequency="daily",
        defensive_scale=0.2,
        risk_per_trade_pct=0.006,
        daily_loss_limit_pct=0.02,
        drawdown_review_pct=0.15,
        benchmark="QQQM",
        design_volatility_target_pct=(16.0, 22.0),
    ),
}
