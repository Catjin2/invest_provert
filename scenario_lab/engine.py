"""
Scenario Lab Engine (시스템 C: 시뮬레이션 및 가상 체결 엔진)
15개 슬롯 동적 배분, 슬리피지(0.2%), 트레일링 스탑(-10%), 포트폴리오 서킷브레이커(-15%)를 갖춘
0-I/O 순수 RAM 기반 시뮬레이터.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import io
import contextlib
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np
import yfinance as yf
import config
from config import MomentumConfig
from core.dto import SignalDTO
from core.data_provider import BaseDataProvider
from lvmb_momentum.strategy import LvmbMomentumStrategy

def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance MultiIndex columns to simple single-level index."""
    if df is not None and isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df

class HistoricalDataProvider(BaseDataProvider):
    """미래 참조 편향(Look-ahead Bias) 차단 타임머신 슬라이싱 데이터 프로바이더."""
    def __init__(self, historical_data_dict: dict, current_sim_date: str):
        self.history = {t: clean_df(df) for t, df in historical_data_dict.items() if df is not None and not df.empty}
        self.current_sim_date = pd.to_datetime(current_sim_date)

    def set_date(self, new_date: str):
        self.current_sim_date = pd.to_datetime(new_date)

    def get_history(self, tickers, period="1y", start=None, end=None, group_by=None):
        if isinstance(tickers, str):
            df = self.history.get(tickers)
            if df is None or df.empty:
                return pd.DataFrame()
            return df[df.index <= self.current_sim_date].tail(300)
        else:
            sub_dfs = {}
            for t in tickers:
                df = self.history.get(t)
                if df is not None and not df.empty:
                    sliced = df[df.index <= self.current_sim_date].tail(300)
                    if not sliced.empty:
                        sub_dfs[t] = sliced
            if not sub_dfs:
                return None
            return pd.concat(sub_dfs, axis=1)

    def get_current_price(self, ticker: str) -> float:
        df = self.get_history(ticker)
        if df is not None and not df.empty:
            col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            return float(df[col].iloc[-1])
        return 0.0

    def get_exchange_rate(self) -> float:
        return config.FALLBACK_EXCHANGE_RATE

class InMemoryTrader:
    """
    15슬롯 자본 배분, 슬리피지(0.2%), 트레일링 스탑(-10%),
    Z-Score 붕괴(-2.0), 포트폴리오 서킷브레이커(-15%)를 온전히 지원하는 메모리 트레이더.
    """
    def __init__(self, initial_capital: float = 10000.0, slots: int = 15):
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.slots = slots
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.last_prices: Dict[str, float] = {}
        self.equity_curve: List[Dict[str, Any]] = []
        self.slippage_rate = config.SLIPPAGE_RATE
        self.fee_rate = config.DEFAULT_TRANSACTION_FEE_RATE
        self.mdd_halt_threshold = config.PORTFOLIO_MDD_HALT_THRESHOLD
        self.max_equity = initial_capital
        self.is_halted = False
        self.events: List[Dict[str, Any]] = []

    def get_portfolio_equity(self) -> float:
        pos_val = sum(pos['quantity'] * self.last_prices.get(ticker, pos['entry_price']) for ticker, pos in self.positions.items())
        return self.cash + pos_val

    def evaluate_and_exit_positions(self, date_str: str, provider: HistoricalDataProvider):
        equity = self.get_portfolio_equity()
        if equity > self.max_equity:
            self.max_equity = equity

        # 1. 포트폴리오 서킷브레이커 검사 (Hard Cutoff MDD <= -15%)
        portfolio_mdd = ((equity / self.max_equity) - 1.0) * 100.0 if self.max_equity > 0 else 0.0
        if portfolio_mdd <= self.mdd_halt_threshold and not self.is_halted:
            self.is_halted = True
            self.events.append({
                'date': date_str,
                'type': 'CIRCUIT_BREAKER_HALT',
                'description': f"포트폴리오 서킷브레이커 발동 (MDD {portfolio_mdd:.2f}% <= {self.mdd_halt_threshold}%), 전량 현금화 집행"
            })
            # 전량 청산
            for ticker, pos in list(self.positions.items()):
                curr_price = provider.get_current_price(ticker) or pos['entry_price']
                effective_exit_price = curr_price * (1.0 - self.slippage_rate)
                proceeds = effective_exit_price * pos['quantity'] * (1.0 - self.fee_rate)
                self.cash += proceeds
            self.positions.clear()
            return

        # 2. 개별 포지션 동적 청산 평가 (Trailing Stop & Z-Score Breakdown)
        tickers_to_remove = []
        for ticker, pos in list(self.positions.items()):
            df = provider.get_history(ticker)
            if df is None or df.empty:
                continue
            col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            curr_price = float(df[col].iloc[-1])
            pos['max_price'] = max(pos.get('max_price', curr_price), curr_price)
            self.last_prices[ticker] = curr_price

            exit_signal = LvmbMomentumStrategy.evaluate_position_exit(pos, df)
            if exit_signal and exit_signal.action.startswith("SELL"):
                effective_exit_price = exit_signal.price * (1.0 - self.slippage_rate)
                proceeds = effective_exit_price * pos['quantity'] * (1.0 - self.fee_rate)
                self.cash += proceeds
                tickers_to_remove.append(ticker)
                
                self.events.append({
                    'date': date_str,
                    'type': 'POSITION_EXIT',
                    'ticker': ticker,
                    'reason': exit_signal.action,
                    'exit_price': effective_exit_price,
                    'description': f"{ticker} 포지션 청산 ({exit_signal.action})"
                })

        for t in tickers_to_remove:
            del self.positions[t]

    def add_pending_order(self, date_str: str, sig: SignalDTO):
        if self.is_halted:
            return
        if sig.ticker in self.positions:
            return
        if len(self.positions) >= self.slots:
            return

        # 15슬롯 자본 배분 모델: 가용 슬롯 기준으로 균등 분할
        available_slots = max(1, self.slots - len(self.positions))
        target_allocation = (self.cash * 0.98) / available_slots
        
        effective_buy_price = sig.price * (1.0 + self.slippage_rate)
        cost_per_share = effective_buy_price * (1.0 + self.fee_rate)
        
        if cost_per_share <= 0:
            return
            
        quantity = max(1.0, round(target_allocation / cost_per_share, 4))
        total_trade_cost = quantity * cost_per_share
        
        if self.cash >= total_trade_cost:
            self.cash -= total_trade_cost
            self.positions[sig.ticker] = {
                'ticker': sig.ticker,
                'quantity': quantity,
                'entry_price': effective_buy_price,
                'max_price': sig.price,
                'entry_date': date_str
            }
            self.last_prices[sig.ticker] = sig.price
            self.events.append({
                'date': date_str,
                'type': 'BUY_ORDER',
                'ticker': sig.ticker,
                'price': effective_buy_price,
                'quantity': quantity,
                'description': f"{sig.ticker} 신규 매수 체결 ({quantity}주 @ ${effective_buy_price:,.2f})"
            })

    def record_daily_equity(self, date_str: str, current_prices: dict):
        for ticker, price in current_prices.items():
            if price > 0:
                self.last_prices[ticker] = price
        total_equity = self.get_portfolio_equity()
        if total_equity > self.max_equity:
            self.max_equity = total_equity
        drawdown_pct = ((total_equity / self.max_equity) - 1.0) * 100.0 if self.max_equity > 0 else 0.0
        self.equity_curve.append({
            'date': date_str,
            'equity': total_equity,
            'cash': self.cash,
            'drawdown': drawdown_pct,
            'positions_count': len(self.positions)
        })

class ScenarioLabEngine:
    """시스템 C 시뮬레이션 오케스트레이터."""
    
    @staticmethod
    def run_simulation(historical_data: dict, start_date: str, end_date: str, enable_z_filter: bool = True, initial_capital: float = 10000.0) -> Tuple[pd.DataFrame, InMemoryTrader]:
        # Z-Score 버블 필터 임계치 동적 제어
        limit = 2.0 if enable_z_filter else float('inf')
        config.Z_SCORE_UPPER_LIMIT = limit
        MomentumConfig.Z_SCORE_UPPER_LIMIT = limit

        provider = HistoricalDataProvider(historical_data, current_sim_date=start_date)
        strategy = LvmbMomentumStrategy(data_provider=provider)
        trader = InMemoryTrader(initial_capital=initial_capital, slots=config.MAX_PORTFOLIO_SLOTS)

        trading_days = pd.date_range(start=start_date, end=end_date, freq='B')

        for date in trading_days:
            date_str = date.strftime('%Y-%m-%d')
            provider.set_date(date_str)

            # 1. 당일 장 시작: 기존 보유 종목 청산 평가 (Trailing Stop / Z-Score 붕괴 / 서킷브레이커)
            trader.evaluate_and_exit_positions(date_str, provider)

            # 2. 신규 모멘텀 시그널 스크리닝 (버블 필터 적용 여부)
            tickers = list(historical_data.keys())
            with contextlib.redirect_stdout(io.StringIO()):
                signals = strategy.batch_screen(tickers)

            for sig in signals:
                trader.add_pending_order(date_str, sig)

            # 3. 장 종료 시점 일일 자산 가치 기록
            current_prices = {t: provider.get_current_price(t) for t in trader.positions.keys()}
            trader.record_daily_equity(date_str, current_prices)

        df = pd.DataFrame(trader.equity_curve)
        if not df.empty:
            df.set_index('date', inplace=True)
        return df, trader

    @staticmethod
    def calculate_metrics(equity_df: pd.DataFrame) -> Dict[str, float]:
        if equity_df.empty:
            return {'initial': 10000.0, 'final': 10000.0, 'return_pct': 0.0, 'mdd_pct': 0.0}
        initial = float(equity_df['equity'].iloc[0])
        final = float(equity_df['equity'].iloc[-1])
        return_pct = ((final / initial) - 1.0) * 100.0
        mdd_pct = float(equity_df['drawdown'].min())
        return {
            'initial': initial,
            'final': final,
            'return_pct': return_pct,
            'mdd_pct': mdd_pct
        }
