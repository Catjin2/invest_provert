"""
Global configuration constants for invest_provert trading & analysis systems.
Centralizes all magic numbers, parameters, thresholds, and operational limits.
"""

# =====================================================================
# 1. Global Infrastructure & Network Configuration
# =====================================================================
DEFAULT_DB_PATH = "invest_standalone.db"
DEFAULT_REQUEST_TIMEOUT = 10
DEFAULT_MAX_WORKERS = 15
FALLBACK_EXCHANGE_RATE = 1350.0

# =====================================================================
# 2. LV-MB Momentum Strategy & Risk Management Configuration
# =====================================================================
# Multi-period Momentum Lookback Days & Weights
LOOKBACK_PERIODS = [21, 63, 126, 252]
MOMENTUM_WEIGHTS = [0.35, 0.30, 0.20, 0.15]

# Z-Score Overbought & Bubble Filter Parameters (ABS Braking System)
Z_SCORE_LOOKBACK = 20                 # 20-day moving window for mean & standard deviation
Z_SCORE_UPPER_LIMIT = 2.0             # Reject signals if Z > +2.0 (top ~2.2% statistical outlier / overbought)

class MomentumConfig:
    """Class-level accessor for momentum and z-score configurations."""
    LOOKBACK_PERIODS = LOOKBACK_PERIODS
    MOMENTUM_WEIGHTS = MOMENTUM_WEIGHTS
    MAX_PORTFOLIO_SLOTS = 15
    TOP_SIGNALS_LIMIT = 15
    Z_SCORE_LOOKBACK = Z_SCORE_LOOKBACK
    Z_SCORE_UPPER_LIMIT = Z_SCORE_UPPER_LIMIT

# Portfolio Capacity & Circuit Breakers
MAX_PORTFOLIO_SLOTS = 15
TOP_SIGNALS_LIMIT = 15
PORTFOLIO_MDD_HALT_THRESHOLD = -15.0  # Liquidate all positions and halt if portfolio MDD falls below -15%

# Individual Position Exit & Risk Rules
INDIVIDUAL_TRAILING_STOP_THRESHOLD = -10.0  # -10.0% drawdown from peak triggers trailing stop exit
INDIVIDUAL_Z_SCORE_SELL_THRESHOLD = -2.0    # Z < -2.0 triggers statistical breakdown exit
SLIPPAGE_RATE = 0.002                       # 0.2% slippage & market impact penalty

# Macro Regime (QQQ R12) Hysteresis Thresholds
QQQ_CRASH_THRESHOLD = -0.02           # -2.0% triggers RISK-OFF (100% Cash)
QQQ_RECOVERY_THRESHOLD = 0.02         # +2.0% recovers to SAFE (Hysteresis Buffer)

# Account Capital Management (KRW)
MONTHLY_SEED_AMOUNT = 500_000.0       # Monthly recurring deposit
TAX_DEDUCTIBLE_LIMIT = 2_500_000.0    # Annual capital gains tax exemption (2.5M KRW)
CAPITAL_GAINS_TAX_RATE = 0.22         # 22% Korean capital gains tax for overseas stocks
MONTHLY_CASH_INTEREST_RATE = 0.0033   # +0.33% monthly risk-free interest in 100% Cash regime

# =====================================================================
# 3. SEC Insider Signal Tracking Configuration
# =====================================================================
MIN_INSIDER_BUY_VALUE = 50_000        # Minimum Form 4 transaction value ($50K)
MAX_INSIDER_BUY_VALUE = 100_000_000   # Maximum transaction value ($100M)
DEFAULT_QUERY_DAYS = 7                # Search window for insider filings
BACKTEST_HOLDING_DAYS = 7             # Standard holding period for return calculation
BACKTEST_INVESTMENT_AMOUNT = 100.0    # Standard normalized investment amount ($100)
DEFAULT_TRANSACTION_FEE_RATE = 0.001  # 0.1% transaction fee
