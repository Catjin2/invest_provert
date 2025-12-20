import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

class Backtester:
    def __init__(self, investment_amount=100):
        self.investment_amount = investment_amount
        self.fee_rate = 0.001 

    def calculate_return(self, ticker, signal_date_str):
        try:
            clean_date = signal_date_str.split(' ')[0]
            signal_date = datetime.strptime(clean_date, "%Y-%m-%d")
            entry_date = signal_date + timedelta(days=1)
            exit_date = entry_date + timedelta(days=7)

            data = yf.download(
                ticker, 
                start=entry_date.strftime("%Y-%m-%d"), 
                end=(exit_date + timedelta(days=5)).strftime("%Y-%m-%d"), 
                progress=False,
                auto_adjust=True
            )

            if data.empty or len(data) < 2:
                return None

            # .item()을 사용하여 FutureWarning 완전 제거
            raw_entry = float(data['Open'].iloc[0].item())
            raw_exit = float(data['Close'].iloc[min(7, len(data)-1)].item())
            
            # 수수료 포함 수익률 계산
            return_pct = ((raw_exit * (1 - self.fee_rate)) - (raw_entry * (1 + self.fee_rate))) / (raw_entry * (1 + self.fee_rate)) * 100
            
            # 100달러 투자 시 가치 환산 (가독성 핵심)
            entry_valuation = self.investment_amount
            exit_valuation = self.investment_amount * (1 + (return_pct / 100))
            
            return {
                "Date": clean_date,
                "Ticker": ticker,
                "Entry_Price": round(entry_valuation, 2), # 100.00 고정
                "Exit_Price": round(exit_valuation, 2),  # 100 + 수익금
                "Return_Pct": round(return_pct, 2)
            }
        except Exception:
            return None