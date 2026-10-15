"""
Core financial data collection, DTO contracts, and infrastructure package.
"""

from core.interfaces import IDataProvider, IBroker
from core.data_provider import BaseDataProvider, CoreDataProvider
from core.circuit_breaker import (
    MarketDataCircuitBreaker,
    CircuitBreakerException,
    DataCorruptionException,
    StaleDataException,
)
from core.dto import (
    SignalDTO,
    PositionDTO,
    AccountDTO,
    InsiderSignalDTO,
    OrderDTO,
    ExecutionResultDTO,
    AccountStateDTO,
    MarketSnapshotDTO,
    OrderType,
    OrderStatus,
)

__all__ = [
    "IDataProvider",
    "IBroker",
    "BaseDataProvider",
    "CoreDataProvider",
    "MarketDataCircuitBreaker",
    "CircuitBreakerException",
    "DataCorruptionException",
    "StaleDataException",
    "SignalDTO",
    "PositionDTO",
    "AccountDTO",
    "InsiderSignalDTO",
    "OrderDTO",
    "ExecutionResultDTO",
    "AccountStateDTO",
    "MarketSnapshotDTO",
    "OrderType",
    "OrderStatus",
]
