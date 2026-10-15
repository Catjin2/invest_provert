"""
Core Interfaces and Abstract Base Classes for Dependency Inversion Principle (DIP).
"""

from abc import ABC, abstractmethod
from typing import Optional, Union, List, Dict
import pandas as pd
from core.dto import OrderDTO, ExecutionResultDTO, AccountStateDTO, PositionDTO


class IDataProvider(ABC):
    """
    Abstract contract for financial market data providers (e.g., KIS, FMP, Polygon, yfinance).
    """

    @abstractmethod
    def get_current_price(self, ticker: str) -> float:
        """Fetch latest current market price for a given ticker."""
        pass

    @abstractmethod
    def get_history(
        self,
        tickers: Union[str, List[str]],
        period: str = "1y",
        start: Optional[str] = None,
        end: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data."""
        pass

    @abstractmethod
    def get_exchange_rate(self) -> float:
        """Fetch latest USD/KRW exchange rate."""
        pass


class IBroker(ABC):
    """
    Abstract contract for brokerage order execution and account management
    (e.g., PaperBroker, KisBroker, AlpacaBroker).
    """

    @abstractmethod
    def get_account_state(self) -> AccountStateDTO:
        """Return the current account state including cash, total equity, and holdings."""
        pass

    @abstractmethod
    def submit_order(self, order: OrderDTO) -> ExecutionResultDTO:
        """Submit and execute an order according to broker rules."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order if supported."""
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, int]:
        """Return a mapping of ticker -> current quantity."""
        pass
