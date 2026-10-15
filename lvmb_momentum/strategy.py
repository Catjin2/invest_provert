from typing import Optional, List, Union
from core.data_provider import BaseDataProvider
from lvmb_momentum.data_provider_with_audit import DataProvider
from core.dto import SignalDTO
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config

class LvmbMomentumStrategy:
    def __init__(self, data_provider: Optional[BaseDataProvider] = None):
        self.lookbacks = config.LOOKBACK_PERIODS
        self.data_provider = data_provider or DataProvider()

    def batch_screen(self, tickers):
        """
        Efficiently screens hundreds of tickers in minimal API calls.
        Returns a list of tickers that pass all filters.
        """
        if not tickers: return []
        
        print(f"   -> Batch downloading {len(tickers)} tickers...")
        # 3 Years of data for MDD and 200MA
        start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
        data = self.data_provider.get_history(tickers, start=start_date, group_by='ticker')
        if data is None:
            return []
        
        # Check for US market hours to prevent intraday data pollution (robust to Daylight Saving Time)
        import pytz
        est = pytz.timezone('US/Eastern')
        now_est = datetime.now(est)
        
        is_us_market_hours = False
        # US market is open Mon-Fri, 09:30 AM to 04:00 PM EST/EDT
        if now_est.weekday() < 5:
            time_float = now_est.hour + now_est.minute / 60.0
            if 9.5 <= time_float < 16.0:
                is_us_market_hours = True
                
        today_us_str = now_est.strftime('%Y-%m-%d')
        if is_us_market_hours:
            print(f"   [INTRADAY POLLUTION PROTECTION] Active US Market Hours detected ({now_est.strftime('%H:%M')} EST). Today's ({today_us_str}) data will be excluded from screening.")
        
        passed_tickers = []
        
        for ticker in tickers:
            try:
                # Handle single ticker return vs multiple
                if len(tickers) == 1:
                    df = data
                else:
                    df = data[ticker]
                
                if isinstance(df, pd.DataFrame):
                    df = df.dropna(subset=['Close'])
                else:
                    df = df.dropna()
                
                if is_us_market_hours and not df.empty:
                    last_idx = df.index[-1]
                    last_idx_str = last_idx.strftime('%Y-%m-%d') if hasattr(last_idx, 'strftime') else str(last_idx)[:10]
                    if last_idx_str == today_us_str:
                        df = df.iloc[:-1]
                
                sig = self.calculate_momentum_score(df, ticker, self.lookbacks)
                if sig:
                    passed_tickers.append(sig)
            except:
                continue
                
        # Sort and return Top 15
        passed_tickers = sorted(passed_tickers, key=lambda x: x.score, reverse=True)[:config.TOP_SIGNALS_LIMIT]
        return passed_tickers

    @staticmethod
    def calculate_z_score(df_or_series: Union[pd.DataFrame, pd.Series], window: int = config.Z_SCORE_LOOKBACK) -> float:
        """
        Calculates latest price Z-score relative to rolling mean and standard deviation:
        Z = (P_today - MA_window) / STD_window
        """
        if isinstance(df_or_series, pd.DataFrame):
            col = 'Adj Close' if 'Adj Close' in df_or_series.columns else 'Close'
            series = df_or_series[col]
        else:
            series = df_or_series

        if len(series) < window:
            return 0.0

        rolling_mean = series.rolling(window=window).mean()
        rolling_std = series.rolling(window=window).std()
        latest_std = rolling_std.iloc[-1]
        if pd.isna(latest_std) or latest_std <= 0:
            return 0.0

        z = (series.iloc[-1] - rolling_mean.iloc[-1]) / latest_std
        return 0.0 if pd.isna(z) else float(z)

    @staticmethod
    def calculate_momentum_score(df: pd.DataFrame, ticker: str, lookbacks: list) -> Optional[SignalDTO]:
        """
        Pure business calculation: Computes TS Momentum, Trend Quality (R^2),
        and applies Z-Score Overbought / Bubble Filter.
        Completely isolated from I/O with 0 side-effects.
        """
        if len(df) <= max(lookbacks):
            return None
            
        close = df['Adj Close'] if 'Adj Close' in df.columns else df['Close']
        
        # Calculate TS Momentum (R1, R3, R6, R12)
        r1 = (close.iloc[-1] / close.iloc[-22]) - 1
        r3 = (close.iloc[-1] / close.iloc[-64]) - 1
        r6 = (close.iloc[-1] / close.iloc[-127]) - 1
        r12 = (close.iloc[-1] / close.iloc[-253]) - 1
        
        # Absolute Filter: 12-month return must be positive
        if pd.isna(r12) or r12 <= 0:
            return None
        
        # Trend Filter: Recent 1M & 3M positive
        if r1 <= 0 or r3 <= 0:
            return None
            
        # Z-Score Overbought / Bubble Filter (Statistical Outlier Constraint)
        z_score = LvmbMomentumStrategy.calculate_z_score(close, window=config.Z_SCORE_LOOKBACK)
        if z_score > config.Z_SCORE_UPPER_LIMIT:
            # Overbought / FOMO peak bubble rejection (statistical outlier Z > 2.0)
            return None
        
        # Calculate R-squared over the last 126 trading days (6 months) for trend quality
        y_val = np.log(close.iloc[-126:].values.astype(float))
        x_val = np.arange(len(y_val))
        slope, intercept = np.polyfit(x_val, y_val, 1)
        y_pred = slope * x_val + intercept
        ss_tot = np.sum((y_val - np.mean(y_val))**2)
        ss_res = np.sum((y_val - y_pred)**2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0.0 else 0.0
        
        # Score = R12 * R^2 (Momentum weighted by Trend Quality)
        score = r12 * r_squared
        
        signal_date = df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])[:10]
        return SignalDTO(
            ticker=ticker,
            price=float(close.iloc[-1]),
            score=float(score),
            r12=float(r12),
            date=signal_date,
            z_score=float(z_score),
            action="BUY"
        )

    @staticmethod
    def evaluate_position_exit(pos: dict, df: pd.DataFrame) -> Optional[SignalDTO]:
        """
        Evaluates whether an active holding should be exited.
        Returns a SignalDTO with action='SELL' and specific reason, or None if holding.
        Triggers:
        1. Trailing Stop: Current price dropped <= INDIVIDUAL_TRAILING_STOP_THRESHOLD (-10.0%) from peak.
        2. Statistical Breakdown: Z-Score <= INDIVIDUAL_Z_SCORE_SELL_THRESHOLD (-2.0).
        """
        if df is None or df.empty:
            return None

        col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
        curr_price = float(df[col].iloc[-1])
        high_price = max(pos.get('max_price') or curr_price, curr_price)
        drawdown_pct = ((curr_price / high_price) - 1.0) * 100.0

        # 1. Trailing Stop check
        if drawdown_pct <= config.INDIVIDUAL_TRAILING_STOP_THRESHOLD:
            signal_date = df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])[:10]
            return SignalDTO(
                ticker=pos['ticker'],
                price=curr_price,
                score=float(drawdown_pct),
                r12=0.0,
                date=signal_date,
                z_score=0.0,
                action=f"SELL (TRAILING STOP {drawdown_pct:.1f}%)"
            )

        # 2. Z-Score Statistical Breakdown check
        z_score = LvmbMomentumStrategy.calculate_z_score(df[col], window=config.Z_SCORE_LOOKBACK)
        if z_score <= config.INDIVIDUAL_Z_SCORE_SELL_THRESHOLD:
            signal_date = df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])[:10]
            return SignalDTO(
                ticker=pos['ticker'],
                price=curr_price,
                score=float(z_score),
                r12=0.0,
                date=signal_date,
                z_score=float(z_score),
                action=f"SELL (Z-SCORE BREAKDOWN {z_score:.2f})"
            )

        return None

    def check_global_safety(self, prev_state='SAFE', tickers=["QQQ"]):
        """Checks if QQQ R12 triggers regime change using hysteresis buffer (-2% to +2%)."""
        try:
            # Get ~1.5 years of data for 252-day lookback buffer
            start_date = (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d')
            data = self.data_provider.get_history(tickers, start=start_date)
            if data is None:
                return True, prev_state, 0.0 # Fail safe
            
            if isinstance(data.columns, pd.MultiIndex):
                if 'Adj Close' in data.columns.get_level_values(0):
                    close = data['Adj Close'].copy()
                elif 'Close' in data.columns.get_level_values(0):
                    close = data['Close'].copy()
                else:
                    close = data.xs('Adj Close', axis=1, level=0).copy()
            else:
                col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
                close = data[col].copy()
                
            close = close.dropna()
            
            # Check for US market hours to prevent intraday data pollution (robust to Daylight Saving Time)
            import pytz
            est = pytz.timezone('US/Eastern')
            now_est = datetime.now(est)
            
            is_us_market_hours = False
            # US market is open Mon-Fri, 09:30 AM to 04:00 PM EST/EDT
            if now_est.weekday() < 5:
                time_float = now_est.hour + now_est.minute / 60.0
                if 9.5 <= time_float < 16.0:
                    is_us_market_hours = True
                    
            today_us_str = now_est.strftime('%Y-%m-%d')
            if is_us_market_hours and not close.empty:
                last_idx = close.index[-1]
                last_idx_str = last_idx.strftime('%Y-%m-%d') if hasattr(last_idx, 'strftime') else str(last_idx)[:10]
                if last_idx_str == today_us_str:
                    print(f"   [INTRADAY POLLUTION PROTECTION] Active US Market Hours detected ({now_est.strftime('%H:%M')} EST). Today's ({today_us_str}) data will be excluded from QQQ safety check.")
                    close = close.iloc[:-1]
            
            if len(close) < 253: return True, prev_state, 0.0 # Fail safe
            
            # Since QQQ is a single ticker, close is Series
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
                
            r12 = (close.iloc[-1] / close.iloc[-253]) - 1
            
            # Apply Hysteresis Buffer
            if prev_state == 'SAFE':
                if r12 <= config.QQQ_CRASH_THRESHOLD:
                    return False, 'CASH', float(r12)
                else:
                    return True, 'SAFE', float(r12)
            else: # 'CASH'
                if r12 >= config.QQQ_RECOVERY_THRESHOLD:
                    return True, 'SAFE', float(r12)
                else:
                    return False, 'CASH', float(r12)
        except Exception as e:
            return (prev_state == 'SAFE'), prev_state, 0.0

AntiGravityStrategy = LvmbMomentumStrategy

if __name__ == "__main__":
    strategy = LvmbMomentumStrategy()
    res = strategy.batch_screen(["AAPL", "MSFT", "005930.KS"])
    print(f"Batch Passed: {[r['ticker'] for r in res]}")
