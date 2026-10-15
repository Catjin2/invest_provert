"""
Isolated Unit Tests validating Architectural Principles:
1. Modularity & Dependency Injection (DI)
2. High Cohesion & Rich Domain Models
3. Low Coupling & Demeter-Compliant Interfaces
4. Type Safety & DTO Serialization
"""

import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
import config
from core.data_provider import BaseDataProvider, CoreDataProvider
from core.dto import SignalDTO, PositionDTO, AccountDTO
from lvmb_momentum.strategy import AntiGravityStrategy
from lvmb_momentum.trader import AntiGravityTrader
from lvmb_momentum.database import AntiGravityDB
from sec_insider.backtester import Backtester

class MockDataProvider(BaseDataProvider):
    """Mock DataProvider returning deterministic data in airplane mode (0 network I/O)."""
    def __init__(self, custom_dfs=None, custom_prices=None):
        self.custom_dfs = custom_dfs or {}
        self.custom_prices = custom_prices or {}

    def get_history(self, tickers, period="1y", start=None, end=None, group_by=None):
        dates = pd.date_range(end=datetime.now(), periods=300, freq='B')
        if isinstance(tickers, str):
            if tickers in self.custom_dfs:
                return self.custom_dfs[tickers]
            prices = np.linspace(100.0, 150.0, len(dates))
            return pd.DataFrame({
                "Open": prices,
                "High": prices * 1.01,
                "Low": prices * 0.99,
                "Close": prices,
                "Adj Close": prices,
                "Volume": [1000000] * len(dates)
            }, index=dates)
        else:
            ticker_list = list(tickers)
            sub_dfs = {}
            for ticker in ticker_list:
                if ticker in self.custom_dfs:
                    sub_dfs[ticker] = self.custom_dfs[ticker]
                else:
                    prices = np.linspace(100.0, 150.0, len(dates))
                    sub_dfs[ticker] = pd.DataFrame({
                        "Open": prices,
                        "High": prices * 1.01,
                        "Low": prices * 0.99,
                        "Close": prices,
                        "Adj Close": prices,
                        "Volume": [1000000] * len(dates)
                    }, index=dates)
            combined = pd.concat(sub_dfs, axis=1)
            if group_by != 'ticker':
                combined = combined.swaplevel(0, 1, axis=1)
            return combined

    def get_current_price(self, ticker: str) -> float:
        if ticker in self.custom_prices:
            return self.custom_prices[ticker]
        return 150.0

    def get_exchange_rate(self) -> float:
        return config.FALLBACK_EXCHANGE_RATE


class TestInvestProvertArchitecture(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MockDataProvider()
        self.test_db_path = "test_standalone.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.test_db = AntiGravityDB(self.test_db_path)

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except Exception:
                pass

    def test_stage_1_config_centralization(self):
        """1. Verify Magic Numbers are safely managed via config.py."""
        self.assertEqual(config.CAPITAL_GAINS_TAX_RATE, 0.22)
        self.assertEqual(config.MONTHLY_SEED_AMOUNT, 500_000.0)
        self.assertEqual(config.PORTFOLIO_MDD_HALT_THRESHOLD, -15.0)
        self.assertEqual(config.DEFAULT_TRANSACTION_FEE_RATE, 0.001)

    def test_stage_2_demeter_encapsulation(self):
        """2. Verify Demeter-compliant methods encapsulate database operations."""
        trader = AntiGravityTrader(db=self.test_db, data_provider=self.mock_provider)
        
        # Test regime state encapsulation
        self.assertEqual(trader.get_regime_state(), 'SAFE')
        trader.update_regime_state('CASH')
        self.assertEqual(trader.get_regime_state(), 'CASH')
        
        # Test pending order clear encapsulation
        trader.add_pending_order({"ticker": "AAPL", "price": 150.0, "date": "2026-10-08"})
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM pending_orders")), 1)
        trader.clear_pending_orders()
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM pending_orders")), 0)

    def test_stage_3_dto_contracts_and_json_serialization(self):
        """3. Verify DTO type safety and JSON serialization compatibility."""
        sig = SignalDTO(ticker="NVDA", price=120.5, score=0.88, r12=0.45, date="2026-10-08")
        
        # Attribute dot-access
        self.assertEqual(sig.ticker, "NVDA")
        self.assertEqual(sig.score, 0.88)
        
        # Subscript access for backwards compatibility
        self.assertEqual(sig['ticker'], "NVDA")
        self.assertEqual(sig['price'], 120.5)
        
        # Test trader report queue JSON serialization
        trader = AntiGravityTrader(db=self.test_db, data_provider=self.mock_provider)
        payload = {"all_signals": [sig], "is_safe": True, "regime_slots": 15}
        queued = trader.enqueue_report_task(payload)
        self.assertTrue(queued)
        
        # Verify stored payload in database
        row = self.test_db.fetchone("SELECT payload FROM reporting_queue LIMIT 1")
        self.assertIsNotNone(row)
        self.assertIn('"ticker": "NVDA"', row[0])

    def test_stage_4_dependency_injection_and_mocking(self):
        """4. Verify Mock DataProvider can be injected into Strategy, Trader, and Backtester."""
        # Inject Mock into Strategy
        strategy = AntiGravityStrategy(data_provider=self.mock_provider)
        signals = strategy.batch_screen(["AAPL", "MSFT"])
        self.assertIsInstance(signals, list)
        self.assertTrue(all(isinstance(s, SignalDTO) for s in signals))
        
        # Safety Check with Mock
        is_safe, state, r12 = strategy.check_global_safety(prev_state='SAFE')
        self.assertTrue(is_safe)
        
        # Inject Mock into Backtester
        backtester = Backtester(data_provider=self.mock_provider)
        res = backtester.calculate_return("AAPL", "2026-10-01")
        self.assertIsNotNone(res)
        self.assertIn("Return_Pct", res)

    def test_stage_5_ultra_fast_pure_calculation_under_0_1s(self):
        """5. Verify pure financial mathematical calculation executes in < 0.05 seconds with 0 I/O."""
        import time
        t_start = time.perf_counter()
        
        # Synthesize 300 days of price data in memory
        dates = pd.date_range(end=datetime.now(), periods=300, freq='B')
        prices = np.linspace(100.0, 200.0, len(dates))
        df = pd.DataFrame({
            "Open": prices,
            "High": prices * 1.02,
            "Low": prices * 0.98,
            "Close": prices,
            "Adj Close": prices,
            "Volume": [1000000] * len(dates)
        }, index=dates)
        
        # Execute pure mathematical screening (0 network, 0 DB)
        sig = AntiGravityStrategy.calculate_momentum_score(df, "MOCK_STOCK", config.LOOKBACK_PERIODS)
        
        t_elapsed = time.perf_counter() - t_start
        
        self.assertIsNotNone(sig)
        self.assertEqual(sig.ticker, "MOCK_STOCK")
        self.assertTrue(sig.score > 0)
        self.assertLess(t_elapsed, 0.1, f"Calculation took {t_elapsed:.4f}s, must be under 0.1s")
        print(f"\n   -> Pure calculation execution time: {t_elapsed*1000:.2f} ms (Target < 100 ms)")

    def test_stage_6_z_score_overextension_filter(self):
        """6. Verify Z-Score Overbought / Bubble Filter accepts steady trends and rejects parabolic FOMO peaks."""
        # Check config parameters
        self.assertEqual(config.Z_SCORE_LOOKBACK, 20)
        self.assertEqual(config.Z_SCORE_UPPER_LIMIT, 2.0)
        
        dates = pd.date_range(end=datetime.now(), periods=300, freq='B')
        prices_steady = np.linspace(100.0, 180.0, len(dates))
        df_steady = pd.DataFrame({
            "Open": prices_steady,
            "High": prices_steady * 1.01,
            "Low": prices_steady * 0.99,
            "Close": prices_steady,
            "Adj Close": prices_steady,
            "Volume": [1000000] * len(dates)
        }, index=dates)

        # 1. Steady upward trend: Z-score is within normal bound, must be APPROVED
        sig_steady = AntiGravityStrategy.calculate_momentum_score(df_steady, "STEADY_STOCK", config.LOOKBACK_PERIODS)
        self.assertIsNotNone(sig_steady)
        self.assertLessEqual(sig_steady.z_score, config.Z_SCORE_UPPER_LIMIT)
        self.assertEqual(sig_steady.action, "BUY")

        # 2. Parabolic pump: artificially spike the last price by +40%
        prices_bubble = prices_steady.copy()
        prices_bubble[-1] = prices_bubble[-2] * 1.40  # Massive 40% vertical parabolic spike
        df_bubble = pd.DataFrame({
            "Open": prices_bubble,
            "High": prices_bubble * 1.02,
            "Low": prices_bubble * 0.98,
            "Close": prices_bubble,
            "Adj Close": prices_bubble,
            "Volume": [5000000] * len(dates)
        }, index=dates)

        # Bubble asset Z-score must be > 2.0
        z_bubble = AntiGravityStrategy.calculate_z_score(df_bubble, window=config.Z_SCORE_LOOKBACK)
        self.assertGreater(z_bubble, config.Z_SCORE_UPPER_LIMIT)

        # calculate_momentum_score must REJECT the bubble asset (returns None)
        sig_bubble = AntiGravityStrategy.calculate_momentum_score(df_bubble, "BUBBLE_STOCK", config.LOOKBACK_PERIODS)
        self.assertIsNone(sig_bubble, "Parabolic FOMO bubble asset must be rejected by Z-Score filter!")
        print(f"   -> Z-Score Filter Test: Steady asset approved (Z={sig_steady.z_score:.2f}), Bubble rejected (Z={z_bubble:.2f} > {config.Z_SCORE_UPPER_LIMIT})")

    def test_stage_7_individual_exits_and_mdd_halt(self):
        """7. Verify Trailing Stop (-10%), Z-Score Breakdown (Z < -2.0), and Portfolio MDD Halt (-15%)."""
        dates = pd.date_range(end=datetime.now(), periods=100, freq='B')
        
        # 1. Trailing Stop Exit Test
        # Stock peak was 150, but last price drops to 130 (-13.3% drawdown from peak <= -10%)
        prices_trailing = np.linspace(100.0, 150.0, len(dates))
        prices_trailing[-1] = 130.0  # -13.33% drop from peak (150.0)
        df_trailing = pd.DataFrame({
            "Open": prices_trailing,
            "High": prices_trailing,
            "Low": prices_trailing,
            "Close": prices_trailing,
            "Adj Close": prices_trailing,
            "Volume": [1000000] * len(dates)
        }, index=dates)
        
        # 2. Z-Score Breakdown Exit Test
        # Stock drops -5.2% (does NOT trigger -10% trailing stop), but triggers statistical breakdown Z <= -2.0
        prices_z_break = np.linspace(99.8, 100.2, len(dates))
        prices_z_break[-1] = 95.0  # -5.19% drop from peak, Z-score = -4.25 <= -2.0
        df_z_break = pd.DataFrame({
            "Open": prices_z_break,
            "High": prices_z_break,
            "Low": prices_z_break,
            "Close": prices_z_break,
            "Adj Close": prices_z_break,
            "Volume": [1000000] * len(dates)
        }, index=dates)

        # Direct evaluation test via evaluate_position_exit
        pos_trailing = {"ticker": "TRAIL_TEST", "entry_price": 140.0, "max_price": 150.0, "quantity": 10}
        sig_trail = AntiGravityStrategy.evaluate_position_exit(pos_trailing, df_trailing)
        self.assertIsNotNone(sig_trail)
        self.assertTrue(sig_trail.action.startswith("SELL (TRAILING STOP"))
        
        pos_z = {"ticker": "Z_TEST", "entry_price": 100.0, "max_price": 100.2, "quantity": 10}
        sig_z = AntiGravityStrategy.evaluate_position_exit(pos_z, df_z_break)
        self.assertIsNotNone(sig_z)
        self.assertTrue(sig_z.action.startswith("SELL (Z-SCORE BREAKDOWN"))

        # End-to-End Trader monitor_and_exit execution test
        mock_provider = MockDataProvider(
            custom_dfs={"TRAIL_TEST": df_trailing, "Z_TEST": df_z_break},
            custom_prices={"TRAIL_TEST": 130.0, "Z_TEST": 95.0}
        )
        trader = AntiGravityTrader(db=self.test_db, data_provider=mock_provider)
        
        # Insert test positions into DB
        self.test_db.execute('''
            INSERT INTO positions (ticker, entry_price, quantity, entry_date, current_price, max_price, current_mdd, signal_date, entry_exchange_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("TRAIL_TEST", 140.0, 10, "2026-10-01", 150.0, 150.0, 0.0, "2026-10-01", 1350.0))
        
        self.test_db.execute('''
            INSERT INTO positions (ticker, entry_price, quantity, entry_date, current_price, max_price, current_mdd, signal_date, entry_exchange_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("Z_TEST", 100.0, 10, "2026-10-01", 100.0, 100.2, 0.0, "2026-10-01", 1350.0))

        # Run monitor_and_exit: both positions must be closed and moved to history!
        trader.monitor_and_exit()
        
        remaining_positions = self.test_db.fetchall_dict("SELECT * FROM positions")
        self.assertEqual(len(remaining_positions), 0, "All positions triggering exit signals should be liquidated.")
        
        trade_history = self.test_db.fetchall_dict("SELECT * FROM history")
        self.assertEqual(len(trade_history), 2, "Both liquidated positions must be archived in history.")
        reasons = [h['exit_reason'] for h in trade_history]
        self.assertTrue(any("TRAILING STOP" in r for r in reasons))
        self.assertTrue(any("Z-SCORE BREAKDOWN" in r for r in reasons))
        
        # 3. Portfolio Circuit Breaker (MDD Halt) Test
        # Artificially depress equity so portfolio MDD <= -15%
        # Account initial equity is 10,000,000. Set balance to 6,000,000 so equity = 7,350,000 (MDD = -26.5% <= -15%)
        self.test_db.execute("UPDATE account SET balance = 6000000.0, max_equity = 10000000.0 WHERE id = 1")
        # Add a dummy position and a pending order
        self.test_db.execute('''
            INSERT INTO positions (ticker, entry_price, quantity, entry_date, current_price, max_price, current_mdd, signal_date, entry_exchange_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("HALT_TEST", 100.0, 10, "2026-10-01", 100.0, 100.0, 0.0, "2026-10-01", 1350.0))
        trader.add_pending_order({"ticker": "PENDING_BUY", "price": 100.0, "date": "2026-10-08"})
        
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM positions")), 1)
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM pending_orders")), 1)
        
        # Trigger execute_pending_orders - circuit breaker must halt entries, clear pending, and liquidate all positions
        trader.execute_pending_orders()
        
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM positions")), 0, "Circuit Breaker must liquidate all positions.")
        self.assertEqual(len(self.test_db.fetchall_dict("SELECT * FROM pending_orders")), 0, "Circuit Breaker must clear pending orders.")
        
        halt_history = self.test_db.fetchall_dict("SELECT * FROM history WHERE ticker = 'HALT_TEST'")
        self.assertEqual(len(halt_history), 1)
        self.assertIn("MDD_HALT", halt_history[0]['exit_reason'])
        print(f"   -> Stage 7 verified: Trailing Stop, Z-Score Breakdown, and Portfolio MDD Halt all functional.")

if __name__ == "__main__":
    unittest.main()

