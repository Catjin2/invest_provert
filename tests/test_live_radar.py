import unittest
import pandas as pd
import numpy as np
from scenario_lab.live_radar import LiveRiskRadar, RiskReportDTO

class TestLiveRiskRadar(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        self.dates = pd.date_range("2025-01-01", periods=300, freq="B")
        self.bench_prices = pd.Series(
            100.0 * np.exp(np.cumsum(np.random.normal(0.0005, 0.01, 300))),
            index=self.dates
        )
        self.port_returns = pd.Series(
            np.random.normal(0.0006, 0.012, 300),
            index=self.dates
        )

    def test_calculate_macro_regime(self):
        r12, z_score = LiveRiskRadar.calculate_macro_regime(self.bench_prices)
        self.assertIsInstance(r12, float)
        self.assertIsInstance(z_score, float)
        self.assertFalse(np.isnan(r12))
        self.assertFalse(np.isnan(z_score))

    def test_calculate_shock_var(self):
        bench_returns = self.bench_prices.pct_change().dropna()
        beta, var_krw = LiveRiskRadar.calculate_shock_var(
            self.port_returns, bench_returns, total_equity_krw=10_000_000, shock_pct=-0.05
        )
        self.assertIsInstance(beta, float)
        self.assertIsInstance(var_krw, float)
        self.assertFalse(np.isnan(beta))
        self.assertFalse(np.isnan(var_krw))

    def test_regime_states(self):
        # 1. Normal state
        report_normal = LiveRiskRadar.generate_daily_risk_report(
            self.port_returns, self.bench_prices, total_equity_krw=10_000_000
        )
        self.assertIsInstance(report_normal, RiskReportDTO)
        self.assertGreaterEqual(report_normal.recommended_cash_weight, 0.0)
        self.assertLessEqual(report_normal.recommended_cash_weight, 1.0)

        # 2. Crash state simulation (Extreme drop in price for Z-score < -2.0)
        crash_prices = self.bench_prices.copy()
        crash_prices.iloc[-1] = crash_prices.iloc[-2] * 0.85 # -15% one-day drop
        report_crash = LiveRiskRadar.generate_daily_risk_report(
            self.port_returns, crash_prices, total_equity_krw=10_000_000
        )
        self.assertEqual(report_crash.recommended_cash_weight, 1.0)
        self.assertIn("CRASH WARNING", report_crash.regime_status)

if __name__ == "__main__":
    unittest.main()
