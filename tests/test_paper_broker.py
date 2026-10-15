import unittest
from engine.paper_broker import PaperBroker
from core.dto import OrderDTO, OrderType, OrderStatus

class TestPaperBroker(unittest.TestCase):
    def setUp(self):
        self.initial_cash = 10_000_000.0
        self.fee_rate = 0.00015     # 0.015%
        self.slippage_rate = 0.0010 # 0.10%
        self.broker = PaperBroker(
            initial_cash=self.initial_cash,
            fee_rate=self.fee_rate,
            slippage_rate=self.slippage_rate,
        )

    def test_initial_state(self):
        state = self.broker.get_account_state()
        self.assertEqual(state.cash_krw, self.initial_cash)
        self.assertEqual(state.equity_krw, self.initial_cash)
        self.assertEqual(len(state.holdings), 0)

    def test_buy_execution_with_fee_and_slippage(self):
        # 182,000 KRW 종목 10주 매수
        base_price = 182_000.0
        qty = 10
        order = OrderDTO(
            order_id="ORD_001",
            ticker="133690.KS",
            order_type=OrderType.BUY.value,
            quantity=qty,
            price=base_price,
            created_at="2026-10-13 09:00:00",
        )

        res = self.broker.submit_order(order)
        self.assertEqual(res.status, OrderStatus.FILLED.value)
        self.assertEqual(res.filled_quantity, qty)

        expected_effective_price = base_price * (1 + self.slippage_rate) # 182,182.0
        expected_notional = expected_effective_price * qty               # 1,821,820.0
        expected_fee = expected_notional * self.fee_rate                 # 273.273
        expected_total = expected_notional + expected_fee

        self.assertAlmostEqual(res.filled_price, expected_effective_price, places=2)
        self.assertAlmostEqual(res.fee_krw, expected_fee, places=2)
        self.assertAlmostEqual(self.broker.cash, self.initial_cash - expected_total, places=2)
        self.assertEqual(self.broker.holdings["133690.KS"], qty)

    def test_insufficient_cash_rejected(self):
        # 자본금 초과 대량 매수
        order = OrderDTO(
            order_id="ORD_BIG",
            ticker="133690.KS",
            order_type=OrderType.BUY.value,
            quantity=1000,
            price=182_000.0,
            created_at="2026-10-13 09:00:00",
        )
        res = self.broker.submit_order(order)
        self.assertEqual(res.status, OrderStatus.REJECTED.value)
        self.assertIn("Insufficient cash", res.message)
        self.assertEqual(self.broker.cash, self.initial_cash)

    def test_sell_execution(self):
        # 먼저 매수
        buy_order = OrderDTO(
            order_id="ORD_BUY",
            ticker="446720.KS",
            order_type=OrderType.BUY.value,
            quantity=100,
            price=12_000.0,
            created_at="2026-10-13 09:00:00",
        )
        self.broker.submit_order(buy_order)
        self.assertEqual(self.broker.holdings["446720.KS"], 100)

        # 50주 매도
        sell_order = OrderDTO(
            order_id="ORD_SELL",
            ticker="446720.KS",
            order_type=OrderType.SELL.value,
            quantity=50,
            price=13_000.0,
            created_at="2026-10-13 14:00:00",
        )
        res_sell = self.broker.submit_order(sell_order)
        self.assertEqual(res_sell.status, OrderStatus.FILLED.value)
        self.assertEqual(self.broker.holdings["446720.KS"], 50)

    def test_sell_more_than_held_rejected(self):
        order = OrderDTO(
            order_id="ORD_ILLEGAL_SELL",
            ticker="446720.KS",
            order_type=OrderType.SELL.value,
            quantity=10,
            price=12_000.0,
            created_at="2026-10-13 09:00:00",
        )
        res = self.broker.submit_order(order)
        self.assertEqual(res.status, OrderStatus.REJECTED.value)
        self.assertIn("Insufficient holdings", res.message)

if __name__ == "__main__":
    unittest.main()
