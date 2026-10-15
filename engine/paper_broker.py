"""
Pure Python Paper Trading Engine implementing IBroker.
Simulates real brokerage execution with realistic fees and slippages.
"""

from typing import Dict, List, Optional
from datetime import datetime
import uuid

from core.interfaces import IBroker
from core.dto import (
    OrderDTO,
    ExecutionResultDTO,
    AccountStateDTO,
    OrderType,
    OrderStatus,
)


class PaperBroker(IBroker):
    """
    순수 메모리 기반 가상 브로커(Paper Broker).
    한투 기준 거래 수수료(0.015%) 및 현실적인 슬리피지(0.1%)를 강제 반영하여
    실제 증권사 환경과 오차 없는 체결을 모사합니다.
    """

    def __init__(
        self,
        initial_cash: float = 10_000_000.0,
        fee_rate: float = 0.00015,       # 0.015%
        slippage_rate: float = 0.0010,   # 0.10% (10 bps)
    ):
        self.initial_cash: float = float(initial_cash)
        self.cash: float = float(initial_cash)
        self.fee_rate: float = fee_rate
        self.slippage_rate: float = slippage_rate

        self.holdings: Dict[str, int] = {}
        self.avg_prices: Dict[str, float] = {}
        self.current_prices: Dict[str, float] = {}

        self.orders: List[OrderDTO] = []
        self.executions: List[ExecutionResultDTO] = []

    def update_prices(self, price_map: Dict[str, float]):
        """최신 시세 맵을 주입하여 총 평가액(Equity) 계산에 반영"""
        for ticker, price in price_map.items():
            if price > 0:
                self.current_prices[ticker] = float(price)

    def get_account_state(self) -> AccountStateDTO:
        """현재 계좌 상태(현금, 총 평가액, 보유 종목 및 평균 단가) 반환"""
        holdings_valuation = 0.0
        for ticker, qty in self.holdings.items():
            price = self.current_prices.get(ticker, self.avg_prices.get(ticker, 0.0))
            holdings_valuation += price * qty

        total_equity = self.cash + holdings_valuation
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return AccountStateDTO(
            cash_krw=round(self.cash, 2),
            equity_krw=round(total_equity, 2),
            holdings=dict(self.holdings),
            avg_prices=dict(self.avg_prices),
            updated_at=now_str,
        )

    def get_positions(self) -> Dict[str, int]:
        """보유 종목별 수량 매핑 반환"""
        return {k: v for k, v in self.holdings.items() if v > 0}

    def submit_order(self, order: OrderDTO) -> ExecutionResultDTO:
        """
        주문 접수 및 가상 체결 집행.
        수수료 및 슬리피지를 계산하여 예수금을 차감하고 포지션을 업데이트합니다.
        """
        self.orders.append(order)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exec_id = f"EXEC_{uuid.uuid4().hex[:8].upper()}"

        ticker = order.ticker
        qty = order.quantity
        base_price = float(order.price)

        if qty <= 0 or base_price <= 0:
            result = ExecutionResultDTO(
                execution_id=exec_id,
                order_id=order.order_id,
                ticker=ticker,
                order_type=order.order_type,
                filled_quantity=0,
                filled_price=0.0,
                fee_krw=0.0,
                slippage_krw=0.0,
                executed_at=now_str,
                status=OrderStatus.REJECTED.value,
                message=f"Invalid quantity ({qty}) or price ({base_price}).",
            )
            self.executions.append(result)
            return result

        # 최신 평가 가격 캐시 갱신
        self.current_prices[ticker] = base_price

        # --- 1. BUY ORDER ---
        if order.order_type.upper() == OrderType.BUY.value:
            slippage_unit = base_price * self.slippage_rate
            effective_price = base_price + slippage_unit
            notional = effective_price * qty
            fee = notional * self.fee_rate
            total_required = notional + fee
            total_slippage = slippage_unit * qty

            if self.cash < total_required:
                result = ExecutionResultDTO(
                    execution_id=exec_id,
                    order_id=order.order_id,
                    ticker=ticker,
                    order_type=order.order_type,
                    filled_quantity=0,
                    filled_price=0.0,
                    fee_krw=0.0,
                    slippage_krw=0.0,
                    executed_at=now_str,
                    status=OrderStatus.REJECTED.value,
                    message=f"Insufficient cash: Required {total_required:,.0f} KRW > Available {self.cash:,.0f} KRW",
                )
                self.executions.append(result)
                return result

            # 잔고 차감 및 포지션 반영
            self.cash -= total_required
            prev_qty = self.holdings.get(ticker, 0)
            prev_avg = self.avg_prices.get(ticker, 0.0)

            new_qty = prev_qty + qty
            new_avg = ((prev_avg * prev_qty) + (effective_price * qty)) / new_qty

            self.holdings[ticker] = new_qty
            self.avg_prices[ticker] = new_avg

            result = ExecutionResultDTO(
                execution_id=exec_id,
                order_id=order.order_id,
                ticker=ticker,
                order_type=order.order_type,
                filled_quantity=qty,
                filled_price=round(effective_price, 2),
                fee_krw=round(fee, 2),
                slippage_krw=round(total_slippage, 2),
                executed_at=now_str,
                status=OrderStatus.FILLED.value,
                message="Filled successfully with slippage and fee deduction.",
            )
            self.executions.append(result)
            return result

        # --- 2. SELL ORDER ---
        elif order.order_type.upper() == OrderType.SELL.value:
            current_held = self.holdings.get(ticker, 0)
            if current_held < qty:
                result = ExecutionResultDTO(
                    execution_id=exec_id,
                    order_id=order.order_id,
                    ticker=ticker,
                    order_type=order.order_type,
                    filled_quantity=0,
                    filled_price=0.0,
                    fee_krw=0.0,
                    slippage_krw=0.0,
                    executed_at=now_str,
                    status=OrderStatus.REJECTED.value,
                    message=f"Insufficient holdings: Attempted to sell {qty} shares, but hold {current_held}.",
                )
                self.executions.append(result)
                return result

            slippage_unit = base_price * self.slippage_rate
            effective_price = base_price - slippage_unit
            gross_proceeds = effective_price * qty
            fee = gross_proceeds * self.fee_rate
            net_proceeds = gross_proceeds - fee
            total_slippage = slippage_unit * qty

            self.cash += net_proceeds
            self.holdings[ticker] = current_held - qty
            if self.holdings[ticker] == 0:
                self.holdings.pop(ticker)
                self.avg_prices.pop(ticker, None)

            result = ExecutionResultDTO(
                execution_id=exec_id,
                order_id=order.order_id,
                ticker=ticker,
                order_type=order.order_type,
                filled_quantity=qty,
                filled_price=round(effective_price, 2),
                fee_krw=round(fee, 2),
                slippage_krw=round(total_slippage, 2),
                executed_at=now_str,
                status=OrderStatus.FILLED.value,
                message="Filled successfully with slippage and fee deduction.",
            )
            self.executions.append(result)
            return result

        else:
            result = ExecutionResultDTO(
                execution_id=exec_id,
                order_id=order.order_id,
                ticker=ticker,
                order_type=order.order_type,
                filled_quantity=0,
                filled_price=0.0,
                fee_krw=0.0,
                slippage_krw=0.0,
                executed_at=now_str,
                status=OrderStatus.REJECTED.value,
                message=f"Unsupported order type: {order.order_type}",
            )
            self.executions.append(result)
            return result

    def cancel_order(self, order_id: str) -> bool:
        """페이퍼 브로커는 즉시 체결(Market Order) 처리하므로 미체결 취소는 False"""
        return False
