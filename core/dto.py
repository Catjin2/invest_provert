"""
Data Transfer Objects (DTO) for cross-module type safety and structured data contracts.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
from enum import Enum


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class OrderDTO:
    """불변 주문 요청 객체"""
    order_id: str
    ticker: str
    order_type: str  # "BUY" or "SELL"
    quantity: int
    price: float
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)


@dataclass(frozen=True)
class ExecutionResultDTO:
    """불변 체결 결과 객체"""
    execution_id: str
    order_id: str
    ticker: str
    order_type: str
    filled_quantity: int
    filled_price: float
    fee_krw: float
    slippage_krw: float
    executed_at: str
    status: str  # "FILLED" or "REJECTED"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)


@dataclass
class AccountStateDTO:
    """실시간 계좌 상태 스냅샷 (원화 기준)"""
    cash_krw: float
    equity_krw: float
    holdings: Dict[str, int] = field(default_factory=dict)  # ticker -> quantity
    avg_prices: Dict[str, float] = field(default_factory=dict)  # ticker -> avg_buy_price
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)


@dataclass(frozen=True)
class MarketSnapshotDTO:
    """시장 지표 및 시세 스냅샷"""
    ticker: str
    latest_price: float
    r12: float = 0.0
    z_score: float = 0.0
    as_of_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)


@dataclass
class SignalDTO:
    ticker: str
    price: float
    score: float
    r12: float
    date: str
    z_score: float = 0.0
    action: str = "BUY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # Support dictionary-like subscript access for backwards compatibility
    def __getitem__(self, item):
        return getattr(self, item)


@dataclass
class PositionDTO:
    ticker: str
    entry_price: float
    quantity: int
    entry_date: str
    id: Optional[int] = None
    current_price: float = 0.0
    peak_price: float = 0.0
    current_mdd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item):
        return getattr(self, item)


@dataclass
class AccountDTO:
    balance: float
    equity: float
    max_equity: float
    regime_state: str = "SAFE"
    id: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InsiderSignalDTO:
    ticker: str
    filed_at: str
    officer_title: str
    transaction_value: float = 0.0
    importance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
