import unittest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from core.circuit_breaker import (
    MarketDataCircuitBreaker,
    DataCorruptionException,
    StaleDataException,
)

class TestMarketDataCircuitBreaker(unittest.TestCase):
    def test_validate_valid_price(self):
        valid = MarketDataCircuitBreaker.validate_price("AAPL", 150.0)
        self.assertEqual(valid, 150.0)

    def test_validate_zero_or_negative_price(self):
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_price("AAPL", 0.0)
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_price("AAPL", -10.0)
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_price("AAPL", np.nan)

    def test_validate_abnormal_price_gap(self):
        # 30% 초과 갭 상승 (+50%)
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_price("AAPL", 150.0, prev_price=100.0, max_gap_pct=0.30)

        # 30% 이하 정상 변동 (+10%)
        ok = MarketDataCircuitBreaker.validate_price("AAPL", 110.0, prev_price=100.0, max_gap_pct=0.30)
        self.assertEqual(ok, 110.0)

    def test_validate_freshness(self):
        today = datetime(2026, 10, 13)
        # 2일 전 데이터 (정상 통과)
        recent_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertTrue(MarketDataCircuitBreaker.validate_freshness(recent_date, max_stale_days=4, reference_date=today))

        # 10일 전 지연 데이터 (차단)
        old_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        with self.assertRaises(StaleDataException):
            MarketDataCircuitBreaker.validate_freshness(old_date, max_stale_days=4, reference_date=today)

    def test_validate_dataframe(self):
        # 1. 정상 DataFrame
        df_ok = pd.DataFrame({"Close": [100.0, 105.0, 110.0]}, index=pd.date_range("2026-01-01", periods=3))
        res = MarketDataCircuitBreaker.validate_dataframe(df_ok, "AAPL")
        self.assertEqual(len(res), 3)

        # 2. 빈 DataFrame
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_dataframe(pd.DataFrame(), "AAPL")

        # 3. Close 누락
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_dataframe(pd.DataFrame({"Volume": [100]}), "AAPL")

        # 4. 전부 NaN
        with self.assertRaises(DataCorruptionException):
            MarketDataCircuitBreaker.validate_dataframe(pd.DataFrame({"Close": [np.nan, np.nan]}), "AAPL")

if __name__ == "__main__":
    unittest.main()
