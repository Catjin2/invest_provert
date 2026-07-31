from core.data_provider import CoreDataProvider
from lvmb_momentum.database import AntiGravityDB
from lvmb_momentum.alert import alert_system
from lvmb_momentum.data_auditor import DataAuditor
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class DataProvider(CoreDataProvider):
    def __init__(self, db_path="invest_standalone.db"):
        super().__init__()
        self.db = AntiGravityDB(db_path)
        self.db_path = db_path

    def _fetch_single_ticker(self, ticker, period="1y", start=None, end=None):
        df = None
        
        # --- Tier 1: yfinance single download ---
        try:
            df = yf.download(ticker, period=period, start=start, end=end, progress=False)
            if df is not None and not df.empty and 'Close' in df.columns:
                self.db.save_prices(ticker, df)
                print(f"   [DataProvider] Tier 1 (yfinance) success for {ticker}")
            else:
                df = None
        except Exception as e:
            print(f"   [DataProvider] Tier 1 (yfinance) failed for {ticker}: {e}")
            df = None

        # --- Tier 2: Direct Yahoo Query API ---
        if df is None:
            print(f"   [DataProvider] Tier 2 (Direct Web API) activated for {ticker}")
            df = self._download_from_yahoo_query_direct(ticker, period=period, start=start, end=end)
            if df is not None and not df.empty:
                self.db.save_prices(ticker, df)
                alert_system.send_alert(f"Tier 1 API fail. Tier 2 fallback success for {ticker}.", "WARNING")
            else:
                df = None

        # --- Tier 3: Local SQLite Cache ---
        if df is None:
            print(f"   [DataProvider] Tier 3 (Local SQLite Cache) activated for {ticker}")
            start_date_str = start
            if not start_date_str:
                days_map = {"1d": 1, "5d": 7, "60d": 90, "1y": 365, "2y": 730, "3y": 1095}
                days = days_map.get(period, 365)
                start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            df = self.db.get_cached_prices(ticker, start_date_str, end_date=end)
            if df is not None and not df.empty:
                df = self._forward_fill_to_today(df)
                alert_system.send_alert(f"All external APIs failed. Tier 3 local cache fallback activated for {ticker}.", "WARNING")
            else:
                print(f"   [DataProvider] Critical: No local cached data for {ticker}")
                alert_system.send_alert(f"CRITICAL: Failed to load data for {ticker} from any source (API and Cache empty).", "CRITICAL")
                df = None

        # Run Audit
        if df is not None and not df.empty:
            try:
                auditor = DataAuditor(db_path=self.db.db_path)
                auditor.audit_dataframe(ticker, df)
            except Exception as audit_err:
                print(f"   [DataProvider] Audit failed for {ticker}: {audit_err}")

        return ticker, df

    def get_history(self, tickers, period="1y", start=None, end=None, group_by=None):
        if isinstance(tickers, str):
            ticker_list = [tickers]
            is_single = True
        else:
            ticker_list = list(tickers)
            is_single = False

        ticker_dfs = {}
        
        # 1. Batch download try
        if len(ticker_list) > 1:
            try:
                df_batch = yf.download(ticker_list, period=period, start=start, end=end, progress=False)
                if df_batch is not None and not df_batch.empty:
                    for ticker in ticker_list:
                        try:
                            if isinstance(df_batch.columns, pd.MultiIndex):
                                single_df = pd.DataFrame(index=df_batch.index)
                                has_data = False
                                for col in ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']:
                                    if col in df_batch.columns.levels[0] and ticker in df_batch[col].columns:
                                        single_df[col] = df_batch[col][ticker]
                                        has_data = True
                                if has_data and not single_df.dropna(subset=['Close']).empty:
                                    single_df = single_df.dropna(subset=['Close'])
                                    self.db.save_prices(ticker, single_df)
                                    
                                    try:
                                        auditor = DataAuditor(db_path=self.db.db_path)
                                        auditor.audit_dataframe(ticker, single_df)
                                    except Exception as audit_err:
                                        print(f"   [DataProvider] Audit failed for {ticker}: {audit_err}")
                                        
                                    ticker_dfs[ticker] = single_df
                        except Exception as e:
                            print(f"   [DataProvider] Error unpacking batch data for {ticker}: {e}")
                    
                    if len(ticker_dfs) == len(ticker_list):
                        combined_df = self._reconstruct_multi_df(ticker_dfs)
                        if group_by == 'ticker' and isinstance(combined_df.columns, pd.MultiIndex):
                            combined_df = combined_df.swaplevel(0, 1, axis=1).sort_index(axis=1)
                        return combined_df
            except Exception as e:
                print(f"   [DataProvider] Batch yfinance download failed: {e}")

        # 2. Individual downloads for missing tickers
        from concurrent.futures import ThreadPoolExecutor, as_completed
        missing_tickers = [t for t in ticker_list if t not in ticker_dfs]
        if missing_tickers:
            if len(missing_tickers) == 1:
                t, df = self._fetch_single_ticker(missing_tickers[0], period, start, end)
                if df is not None:
                    ticker_dfs[t] = df
            else:
                with ThreadPoolExecutor(max_workers=min(len(missing_tickers), 15)) as executor:
                    future_to_ticker = {
                        executor.submit(self._fetch_single_ticker, ticker, period, start, end): ticker
                        for ticker in missing_tickers
                    }
                    for future in as_completed(future_to_ticker):
                        ticker = future_to_ticker[future]
                        try:
                            t, df = future.result()
                            if df is not None:
                                ticker_dfs[t] = df
                        except Exception as e:
                            print(f"   [DataProvider] Thread execution failed for {ticker}: {e}")

        if not ticker_dfs:
            return None

        if is_single:
            df_ret = ticker_dfs.get(tickers)
            if df_ret is not None and 'Adj Close' in df_ret.columns:
                df_ret['Adj Close'] = df_ret['Adj Close'].fillna(df_ret['Close'])
            return df_ret
            
        combined_df = self._reconstruct_multi_df(ticker_dfs)
        if group_by == 'ticker' and isinstance(combined_df.columns, pd.MultiIndex):
            combined_df = combined_df.swaplevel(0, 1, axis=1).sort_index(axis=1)
        return combined_df

    def get_current_price(self, ticker):
        df = self.get_history(ticker, period="5d")
        if df is not None and not df.empty:
            close_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            return float(df[close_col].iloc[-1])
            
        cached = self.db.get_last_cached_price(ticker)
        if cached:
            print(f"   [DataProvider] get_current_price fallback to DB last price for {ticker}: {cached['close']}")
            return float(cached['adj_close'] if cached['adj_close'] is not None else cached['close'])

        try:
            pos = self.db.fetchone("SELECT current_price FROM positions WHERE ticker = ?", (ticker,))
            if pos and pos[0]:
                print(f"   [DataProvider] get_current_price fallback to active position price for {ticker}: {pos[0]}")
                return float(pos[0])
        except Exception:
            pass
        return 1.0

    def get_exchange_rate(self):
        ticker = "USDKRW=X"
        df = None
        
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if df is not None and not df.empty and 'Close' in df.columns:
                self.db.save_prices(ticker, df)
            else:
                df = self._download_from_yahoo_query_direct(ticker, period="5d")
                if df is not None and not df.empty:
                    self.db.save_prices(ticker, df)
        except Exception:
            df = None

        if df is not None and not df.empty:
            close_series = df['Close']
            if isinstance(close_series, pd.DataFrame):
                return float(close_series.iloc[-1].iloc[0])
            else:
                return float(close_series.iloc[-1])
                
        cached = self.db.get_last_cached_price(ticker)
        if cached:
            return float(cached['close'])
        return 1350.0
