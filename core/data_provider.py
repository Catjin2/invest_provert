import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

class CoreDataProvider:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _download_from_yahoo_query_direct(self, ticker, period="1y", start=None, end=None):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params_dict: dict = {"interval": "1d"}
        
        if start and end:
            try:
                if isinstance(start, str):
                    p1 = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
                else:
                    p1 = int(start.timestamp() if hasattr(start, 'timestamp') else start)
                if isinstance(end, str):
                    p2 = int(datetime.strptime(end, "%Y-%m-%d").timestamp())
                else:
                    p2 = int(end.timestamp() if hasattr(end, 'timestamp') else end)
                params_dict["period1"] = p1
                params_dict["period2"] = p2
            except Exception as e:
                print(f"   [CoreDataProvider] Date parsing error for query direct: {e}")
                params_dict["range"] = period
        else:
            params_dict["range"] = period

        try:
            response = requests.get(url, params=params_dict, headers=self.headers, timeout=10)
            if response.status_code != 200:
                print(f"   [CoreDataProvider] Direct Yahoo Query failed for {ticker} (Status: {response.status_code})")
                return None
            
            js = response.json()
            result = js.get("chart", {}).get("result", [])
            if not result:
                return None
            
            res = result[0]
            timestamp = res.get("timestamp", [])
            indicators = res.get("indicators", {}).get("quote", [{}])[0]
            
            # Extract adjclose list
            adjclose_list = res.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
            
            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])
            
            if not timestamp or not closes:
                return None
            
            if adjclose_list is None:
                adjclose_list = closes
                
            dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamp]
            
            df = pd.DataFrame({
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Adj Close": adjclose_list,
                "Volume": volumes
            }, index=pd.to_datetime(dates))
            
            df = df.ffill().bfill().dropna(subset=["Close"])
            return df
        except Exception as e:
            print(f"   [CoreDataProvider] Direct Yahoo Query exception for {ticker}: {e}")
            return None

    def _forward_fill_to_today(self, df):
        if df is None or df.empty:
            return df
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_dt = pd.to_datetime(today_str)
        
        last_date = df.index[-1]
        last_date_str = last_date.strftime("%Y-%m-%d")
        
        if last_date_str < today_str:
            new_row = df.iloc[-1].copy()
            df.loc[today_dt] = new_row
        return df

    def _fetch_single_ticker(self, ticker, period="1y", start=None, end=None):
        df = None
        
        # --- Tier 1: yfinance single download ---
        try:
            df = yf.download(ticker, period=period, start=start, end=end, progress=False)
            if df is not None and not df.empty and 'Close' in df.columns:
                print(f"   [CoreDataProvider] Tier 1 (yfinance) success for {ticker}")
            else:
                df = None
        except Exception as e:
            print(f"   [CoreDataProvider] Tier 1 (yfinance) failed for {ticker}: {e}")
            df = None

        # --- Tier 2: Direct Yahoo Query API ---
        if df is None:
            print(f"   [CoreDataProvider] Tier 2 (Direct Web API) activated for {ticker}")
            df = self._download_from_yahoo_query_direct(ticker, period=period, start=start, end=end)
            if df is not None and not df.empty:
                print(f"   [CoreDataProvider] Tier 2 success for {ticker}")
            else:
                df = None
        return ticker, df

    def get_history(self, tickers, period="1y", start=None, end=None, group_by=None):
        if isinstance(tickers, str):
            ticker_list = [tickers]
            is_single = True
        else:
            ticker_list = list(tickers)
            is_single = False

        ticker_dfs = {}
        
        # 1. Batch download try - efficient for multiple tickers
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
                                    ticker_dfs[ticker] = single_df
                        except Exception as e:
                            print(f"   [CoreDataProvider] Error unpacking batch data for {ticker}: {e}")
                    
                    if len(ticker_dfs) == len(ticker_list):
                        combined_df = self._reconstruct_multi_df(ticker_dfs)
                        if group_by == 'ticker' and isinstance(combined_df.columns, pd.MultiIndex):
                            combined_df = combined_df.swaplevel(0, 1, axis=1).sort_index(axis=1)
                        return combined_df
            except Exception as e:
                print(f"   [CoreDataProvider] Batch yfinance download failed: {e}")

        # 2. Individual downloads for missing tickers
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
                            print(f"   [CoreDataProvider] Thread execution failed for {ticker}: {e}")

        if not ticker_dfs:
            return None

        # Return single DataFrame for single ticker
        if is_single:
            df_ret = ticker_dfs.get(tickers)
            if df_ret is not None and 'Adj Close' in df_ret.columns:
                df_ret['Adj Close'] = df_ret['Adj Close'].fillna(df_ret['Close'])
            return df_ret
            
        # Reconstruct multi-index DataFrame for multiple tickers
        combined_df = self._reconstruct_multi_df(ticker_dfs)
        if group_by == 'ticker' and isinstance(combined_df.columns, pd.MultiIndex):
            combined_df = combined_df.swaplevel(0, 1, axis=1).sort_index(axis=1)
        return combined_df

    def _reconstruct_multi_df(self, ticker_dfs):
        all_dates = pd.Index([])
        for df in ticker_dfs.values():
            all_dates = all_dates.union(df.index)
        all_dates = all_dates.sort_values()

        metrics = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        columns = pd.MultiIndex.from_product([metrics, list(ticker_dfs.keys())])
        
        combined_df = pd.DataFrame(index=all_dates, columns=columns)
        
        for ticker, df in ticker_dfs.items():
            for col in metrics:
                if col in df.columns:
                    combined_df.loc[df.index, (col, ticker)] = df[col]
            if ('Adj Close', ticker) in combined_df.columns:
                combined_df[('Adj Close', ticker)] = combined_df[('Adj Close', ticker)].fillna(combined_df[('Close', ticker)])
                    
        combined_df = combined_df.ffill().bfill().astype(float)
        return combined_df

    def get_current_price(self, ticker):
        df = self.get_history(ticker, period="5d")
        if df is not None and not df.empty:
            close_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            return float(df[close_col].iloc[-1])
        return 1.0

    def get_exchange_rate(self):
        ticker = "USDKRW=X"
        df = None
        try:
            df = yf.download(ticker, period="5d", progress=False)
            if df is None or df.empty:
                df = self._download_from_yahoo_query_direct(ticker, period="5d")
        except Exception:
            df = None

        if df is not None and not df.empty:
            close_series = df['Close']
            if isinstance(close_series, pd.DataFrame):
                return float(close_series.iloc[-1].iloc[0])
            else:
                return float(close_series.iloc[-1])
        return 1350.0
