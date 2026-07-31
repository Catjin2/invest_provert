from lvmb_momentum.data_provider_with_audit import DataProvider
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class AntiGravityStrategy:
    def __init__(self):
        self.lookbacks = [21, 63, 126, 252]

    def batch_screen(self, tickers):
        """
        Efficiently screens hundreds of tickers in minimal API calls.
        Returns a list of tickers that pass all filters.
        """
        if not tickers: return []
        
        print(f"   -> Batch downloading {len(tickers)} tickers...")
        # 3 Years of data for MDD and 200MA
        start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
        dp = DataProvider()
        data = dp.get_history(tickers, start=start_date, group_by='ticker')
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
                
                if len(df) <= max(self.lookbacks): continue
                
                close = df['Adj Close'] if 'Adj Close' in df.columns else df['Close']
                
                # Calculate TS Momentum (R1, R3, R6, R12)
                r1 = (close.iloc[-1] / close.iloc[-22]) - 1
                r3 = (close.iloc[-1] / close.iloc[-64]) - 1
                r6 = (close.iloc[-1] / close.iloc[-127]) - 1
                r12 = (close.iloc[-1] / close.iloc[-253]) - 1
                
                # Absolute Filter: 12-month return must be positive
                if pd.isna(r12) or r12 <= 0: continue
                
                # Trend Filter: 최근 1개월(R1) 및 3개월(R3)이 양수일 것 (하강 추세 필터링)
                if r1 <= 0 or r3 <= 0: continue
                
                # Calculate R-squared over the last 126 trading days (6 months) to measure trend quality
                y_val = np.log(close.iloc[-126:].values.astype(float))
                x_val = np.arange(len(y_val))
                slope, intercept = np.polyfit(x_val, y_val, 1)
                y_pred = slope * x_val + intercept
                ss_tot = np.sum((y_val - np.mean(y_val))**2)
                ss_res = np.sum((y_val - y_pred)**2)
                r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0.0 else 0.0
                
                # Score = R12 * R^2 (Momentum weighted by Trend Quality)
                score = r12 * r_squared
                
                passed_tickers.append({
                    "ticker": ticker,
                    "price": float(close.iloc[-1]),
                    "score": float(score),
                    "r12": float(r12),
                    "date": df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])[:10]
                })
            except:
                continue
                
        # Sort and return Top 15
        passed_tickers = sorted(passed_tickers, key=lambda x: x['score'], reverse=True)[:15]
        return passed_tickers

    def check_global_safety(self, prev_state='SAFE', tickers=["QQQ"]):
        """Checks if QQQ R12 triggers regime change using hysteresis buffer (-2% to +2%)."""
        try:
            # Get ~1.5 years of data for 252-day lookback buffer
            start_date = (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d')
            dp = DataProvider()
            data = dp.get_history(tickers, start=start_date)
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
                if r12 <= -0.02:
                    return False, 'CASH', float(r12)
                else:
                    return True, 'SAFE', float(r12)
            else: # 'CASH'
                if r12 >= 0.02:
                    return True, 'SAFE', float(r12)
                else:
                    return False, 'CASH', float(r12)
        except Exception as e:
            return (prev_state == 'SAFE'), prev_state, 0.0

if __name__ == "__main__":
    strategy = AntiGravityStrategy()
    res = strategy.batch_screen(["AAPL", "MSFT", "005930.KS"])
    print(f"Batch Passed: {[r['ticker'] for r in res]}")
