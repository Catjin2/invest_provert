# tests/stress_test_backtest.py
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import io
import contextlib
import pandas as pd
import yfinance as yf
import config
from config import MomentumConfig
from core.dto import SignalDTO
from lvmb_momentum.strategy import AntiGravityStrategy
from core.data_provider import BaseDataProvider

def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance MultiIndex columns to simple single-level index."""
    if df is not None and isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df

class HistoricalDataProvider(BaseDataProvider):
    def __init__(self, historical_data_dict: dict, current_sim_date: str):
        self.history = {t: clean_df(df) for t, df in historical_data_dict.items()}
        self.current_sim_date = pd.to_datetime(current_sim_date)

    def get_history(self, tickers, period="1y", start=None, end=None, group_by=None):
        if isinstance(tickers, str):
            df = self.history.get(tickers)
            if df is None or df.empty:
                return pd.DataFrame()
            sliced_df = df[df.index <= self.current_sim_date]
            return sliced_df.tail(300)
        else:
            # Multi-ticker: concatenate with ticker level 0 so data[ticker] works in strategy
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
        return 1350.0

    def set_date(self, new_date: str):
        self.current_sim_date = pd.to_datetime(new_date)

class InMemoryTrader:
    def __init__(self, initial_capital=10000.0, slippage_rate=0.002, fee_rate=0.001):
        self.cash = initial_capital
        self.positions = {}  # ticker -> {'quantity': int, 'entry_price': float, 'max_price': float}
        self.last_prices = {}
        self.equity_curve = []
        self.slippage_rate = slippage_rate
        self.fee_rate = fee_rate

    def add_pending_order(self, sig: SignalDTO):
        if sig.ticker in self.positions:
            return
        effective_buy_price = sig.price * (1.0 + self.slippage_rate)
        cost = effective_buy_price * (1.0 + self.fee_rate)
        if self.cash >= cost:
            self.cash -= cost
            self.positions[sig.ticker] = {
                'ticker': sig.ticker,
                'quantity': 1,
                'entry_price': effective_buy_price,
                'max_price': sig.price
            }
            self.last_prices[sig.ticker] = sig.price

    def evaluate_and_exit_positions(self, provider: HistoricalDataProvider):
        tickers_to_remove = []
        for ticker, pos in list(self.positions.items()):
            df = provider.get_history(ticker)
            if df is None or df.empty:
                continue
            col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            curr_price = float(df[col].iloc[-1])
            pos['max_price'] = max(pos['max_price'], curr_price)
            self.last_prices[ticker] = curr_price
            
            exit_signal = AntiGravityStrategy.evaluate_position_exit(pos, df)
            if exit_signal and exit_signal.action.startswith("SELL"):
                # Liquidate position factoring in slippage & fee
                effective_exit_price = exit_signal.price * (1.0 - self.slippage_rate)
                proceeds = effective_exit_price * pos['quantity'] * (1.0 - self.fee_rate)
                self.cash += proceeds
                tickers_to_remove.append(ticker)
                
        for t in tickers_to_remove:
            del self.positions[t]

    def record_daily_equity(self, date_str, current_prices: dict):
        for ticker, price in current_prices.items():
            if price > 0:
                self.last_prices[ticker] = price
        portfolio_value = sum(pos['quantity'] * self.last_prices.get(ticker, 0.0) for ticker, pos in self.positions.items())
        total_equity = self.cash + portfolio_value
        self.equity_curve.append({'date': date_str, 'equity': total_equity})

def run_stress_test(historical_data, start_date, end_date, enable_z_filter=True):
    # Z-Score 필터 제어 (config 모듈 변수와 MomentumConfig 클래스 속성 동시 갱신)
    limit = 2.0 if enable_z_filter else float('inf')
    config.Z_SCORE_UPPER_LIMIT = limit
    MomentumConfig.Z_SCORE_UPPER_LIMIT = limit

    provider = HistoricalDataProvider(historical_data, current_sim_date=start_date)
    strategy = AntiGravityStrategy(data_provider=provider)
    trader = InMemoryTrader(initial_capital=10000.0, slippage_rate=config.SLIPPAGE_RATE)

    trading_days = pd.date_range(start=start_date, end=end_date, freq='B')
    
    for date in trading_days:
        date_str = date.strftime('%Y-%m-%d')
        provider.set_date(date_str)
        
        # 1. 보유 종목 동적 청산 평가 (Trailing Stop & Z-Score Breakdown)
        trader.evaluate_and_exit_positions(provider)
        
        # 2. 신규 모멘텀 시그널 스크리닝
        tickers = list(historical_data.keys())
        with contextlib.redirect_stdout(io.StringIO()):
            signals = strategy.batch_screen(tickers)
        
        for sig in signals:
            trader.add_pending_order(sig)
            
        current_prices = {t: provider.get_current_price(t) for t in trader.positions.keys()}
        trader.record_daily_equity(date_str, current_prices)

    df = pd.DataFrame(trader.equity_curve)
    df.set_index('date', inplace=True)
    return df

def calculate_metrics(equity_df):
    initial = equity_df['equity'].iloc[0]
    final = equity_df['equity'].iloc[-1]
    return_pct = (final / initial - 1.0) * 100
    
    roll_max = equity_df['equity'].cummax()
    drawdown = (equity_df['equity'] / roll_max) - 1.0
    mdd_pct = drawdown.min() * 100
    
    return return_pct, mdd_pct

if __name__ == "__main__":
    print("다운로드 중... (2019-01-01 ~ 2020-06-30 데이터)")
    tickers = ['QQQ', 'AAPL', 'MSFT', 'TSLA']
    # 이동평균 계산을 위해 시작일을 여유 있게 2019년 1월로 잡습니다.
    data = {t: clean_df(yf.download(t, start='2019-01-01', end='2020-06-30', progress=False)) for t in tickers}
    
    # 1. 핵심 폭락장 집중 테스트 구간 (2020년 2월 버블 정점 진입 직후 3월 폭락 방어력)
    crash_start = '2020-02-01'
    crash_end = '2020-04-30'
    print(f"\n[1] 코로나 버블 정점 및 폭락장 집중 구간 ({crash_start} ~ {crash_end}) 시뮬레이션...")
    df_crash_off = run_stress_test(data, crash_start, crash_end, enable_z_filter=False)
    ret_c_off, mdd_c_off = calculate_metrics(df_crash_off)

    df_crash_on = run_stress_test(data, crash_start, crash_end, enable_z_filter=True)
    ret_c_on, mdd_c_on = calculate_metrics(df_crash_on)

    print("\n========= [1] 폭락장 집중 구간 (Crash Window) =========")
    print(f"[필터 OFF (기존 모멘텀)] 수익률: {ret_c_off:>6.2f}% | MDD: {mdd_c_off:>7.2f}%")
    print(f"[필터 ON  (Z-Score 2.0)] 수익률: {ret_c_on:>6.2f}% | MDD: {mdd_c_on:>7.2f}%  (MDD {abs(mdd_c_off - mdd_c_on):.2f}%p 방어)")
    print("==========================================================")

    # 2. 전체 회복 사이클 구간 (2019-10-01 ~ 2020-06-30)
    full_start = '2019-10-01'
    full_end = '2020-06-30'
    print(f"\n[2] 전체 사이클 구간 ({full_start} ~ {full_end}) 시뮬레이션...")
    df_full_off = run_stress_test(data, full_start, full_end, enable_z_filter=False)
    ret_f_off, mdd_f_off = calculate_metrics(df_full_off)

    df_full_on = run_stress_test(data, full_start, full_end, enable_z_filter=True)
    ret_f_on, mdd_f_on = calculate_metrics(df_full_on)

    print("\n========= [2] 전체 회복 사이클 (Full Cycle) =========")
    print(f"[필터 OFF (기존 모멘텀)] 수익률: {ret_f_off:>6.2f}% | MDD: {mdd_f_off:>7.2f}%")
    print(f"[필터 ON  (Z-Score 2.0)] 수익률: {ret_f_on:>6.2f}% | MDD: {mdd_f_on:>7.2f}%")
    print("========================================================")
