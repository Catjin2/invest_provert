import sqlite3
from datetime import datetime, timedelta
from lvmb_momentum.data_provider_with_audit import DataProvider
import pandas as pd
from lvmb_momentum.database import AntiGravityDB
from lvmb_momentum.alert import alert_system

class AntiGravityTrader:
    def __init__(self, db_path="invest_standalone.db"):
        self.db = AntiGravityDB(db_path)

    def get_exchange_rate(self):
        try:
            return DataProvider(self.db.db_path).get_exchange_rate()
        except Exception as e:
            print(f"Trader failed to fetch exchange rate, using fallback 1350.0: {e}")
        return 1350.0

    def add_pending_order(self, signal_data):
        """Signals from close are stored as pending for next open entry."""
        ticker = signal_data['ticker']
        # Check if already in pending or position
        if self.db.fetchone("SELECT id FROM pending_orders WHERE ticker = ?", (ticker,)): return
        if self.db.fetchone("SELECT id FROM positions WHERE ticker = ?", (ticker,)): return
        
        self.db.execute('''
            INSERT INTO pending_orders (ticker, signal_price, signal_date)
            VALUES (?, ?, ?)
        ''', (ticker, signal_data['price'], signal_data['date']))
        print(f"Pending Order Added: {ticker}")

    def execute_pending_orders(self):
        """Executed at start of cycle. Checks if market open price is available to entry."""
        pending = self.db.fetchall_dict("SELECT * FROM pending_orders")
        if not pending: return
        
        tickers = [p['ticker'] for p in pending]
        # Download today's open data
        dp = DataProvider(self.db.db_path)
        data = dp.get_history(tickers, period="5d", group_by='ticker')
        if data is None:
            print("[ERROR] Failed to fetch market data for pending orders.")
            alert_system.send_alert("Failed to fetch market data for pending orders.", "CRITICAL")
            return
        
        exchange_rate = self.get_exchange_rate()
        balance, equity, max_equity = self.db.get_account_info(exchange_rate=exchange_rate)
        
        # Portfolio Risk Management (MDD)
        portfolio_mdd = ((equity / max_equity) - 1) * 100 if max_equity > 0 else 0
        if portfolio_mdd < -15.0:
            print(f"[PORTFOLIO RISK] MDD {portfolio_mdd:.2f}% is below -15% threshold. Halting new entries.")
            return
 
        # Dynamic Sizing: Volatility-Inverse weight for target 15 portfolio
        active_pos = self.db.fetchall_dict("SELECT * FROM positions")
        active_count = len(active_pos) if active_pos else 0
        target_slots = 15
        
        # Protect against taking more than 15 slots
        available_slots = target_slots - active_count
        
        # Volatility Sizing Calculation: Get historical volatility over last 60 days
        try:
            hist_data = dp.get_history(tickers, period="60d")
        except Exception as e:
            print(f"   -> Failed to download volatility history: {e}")
            hist_data = None
            
        vol_dict = {}
        telemetry_records = []
        
        for ticker in tickers:
            vol_dict[ticker] = 0.18  # Default target/fallback volatility (18% annualized)
            data_downloaded = False
            col_name = 'Adj Close'
            total_days = len(hist_data) if hist_data is not None else 0
            valid_days = 0
            df_ticker = None
            
            if hist_data is not None and not hist_data.empty:
                try:
                    # 1. 'Adj Close' 우선 선점, 결측치 방어
                    if len(tickers) == 1:
                        if 'Adj Close' not in hist_data.columns:
                            col_name = 'Close'
                        df_ticker = hist_data[col_name]
                    else:
                        if isinstance(hist_data.columns, pd.MultiIndex):
                            if 'Adj Close' not in hist_data.columns.get_level_values(0):
                                col_name = 'Close'
                            df_ticker = hist_data[col_name][ticker]
                        else:
                            if 'Adj Close' not in hist_data.columns:
                                col_name = 'Close'
                            df_ticker = hist_data[col_name]
                            
                    df_ticker = df_ticker.dropna()
                    valid_days = len(df_ticker)
                    data_downloaded = True
                except Exception as ex:
                    print(f"   -> Volatility extraction error for {ticker}: {ex}")
                    data_downloaded = False

            if data_downloaded and valid_days >= 30 and df_ticker is not None:
                try:
                    # 2. 일일 수익률 계산 및 변동성 왜곡 방어용 클리핑 (±10% 제한)
                    daily_returns = df_ticker.pct_change().dropna()
                    
                    # clipping 계산 전 outlier 개수 세기
                    clip_mask = (daily_returns > 0.10) | (daily_returns < -0.10)
                    clip_count = int(clip_mask.sum())
                    
                    # 클리핑 전 연율화 변동성
                    raw_daily_vol = daily_returns.std()
                    raw_ann_vol = raw_daily_vol * (252 ** 0.5)
                    
                    # 클리핑 적용
                    daily_returns_clipped = daily_returns.clip(lower=-0.10, upper=0.10)
                    daily_vol = daily_returns_clipped.std()
                    ann_vol = daily_vol * (252 ** 0.5)
                    
                    if pd.isna(ann_vol) or ann_vol <= 0.01:
                        ann_vol = 0.18
                        
                    vol_dict[ticker] = ann_vol
                    
                    # vol_scale 미리 계산
                    vol_scale = 0.18 / ann_vol
                    vol_scale = min(max(vol_scale, 0.2), 2.5)
                    
                    # 텔레메트리 기록 추가 및 DB 적재
                    self.db.execute('''
                        INSERT INTO data_health_logs (ticker, data_source, total_days, valid_days, clip_count, raw_ann_vol, clipped_ann_vol, vol_scale)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (ticker, col_name, total_days, valid_days, clip_count, raw_ann_vol, ann_vol, vol_scale))
                    
                    telemetry_records.append({
                        'Ticker': ticker,
                        'Source': col_name,
                        'Total Days': total_days,
                        'Valid Days': valid_days,
                        'Clips': clip_count,
                        'Raw Vol': raw_ann_vol,
                        'Clipped Vol': ann_vol,
                        'Scale': vol_scale
                    })
                except Exception as ex:
                    print(f"   -> Volatility computation inner error for {ticker}: {ex}")
                    data_downloaded = False
                    
            if not data_downloaded or valid_days < 30:
                reason = "Insufficient data history" if data_downloaded else "Data download completely failed"
                print(f"   [WARNING] {reason} for {ticker} ({valid_days} valid days). Using fallback volatility 18%.")
                alert_system.send_alert(f"{reason} for {ticker} ({valid_days} valid days). Volatility forced to fallback 18%.", "WARNING")
                
                self.db.execute('''
                    INSERT INTO data_health_logs (ticker, data_source, total_days, valid_days, clip_count, raw_ann_vol, clipped_ann_vol, vol_scale)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ticker, col_name, total_days, valid_days, 0, 0.18, 0.18, 1.0))
                
                telemetry_records.append({
                    'Ticker': ticker,
                    'Source': col_name,
                    'Total Days': total_days,
                    'Valid Days': valid_days,
                    'Clips': 0,
                    'Raw Vol': 0.18,
                    'Clipped Vol': 0.18,
                    'Scale': 1.00
                })
                    
        # 콘솔에 텔레메트리 보고서 출력
        if telemetry_records:
            df_telemetry = pd.DataFrame(telemetry_records)
            print("\n" + "="*85)
            print(" DATA HEALTH TELEMETRY & VOLATILITY TUNING REPORT")
            print("="*85)
            print(df_telemetry.to_string(index=False, formatters={
                'Raw Vol': '{:,.2%}'.format,
                'Clipped Vol': '{:,.2%}'.format,
                'Scale': '{:.2f}x'.format,
            }))
            print("="*85 + "\n")
        
        for p in pending:
            ticker = p['ticker']
            try:
                # Handle single ticker vs multi-ticker download structure
                if len(tickers) > 1:
                    if ticker not in data.columns.get_level_values(0):
                        print(f"   -> Skip {ticker}: No data found in download result")
                        continue
                    df = data[ticker]
                else:
                    df = data
                
                if df.empty or 'Open' not in df.columns:
                    print(f"   -> Skip {ticker}: Missing 'Open' price data")
                    continue
                
                open_price = float(df['Open'].iloc[-1])
                # Apply 0.1% FX buy spread penalty
                open_price_krw = open_price * (exchange_rate * 1.001)
                if available_slots <= 0:
                    print(f"   -> Skip {ticker}: Portfolio Full (15 slots max)")
                    continue
                
                # Volatility-Inverse Position Sizing
                asset_vol = vol_dict.get(ticker, 0.18)
                vol_scale = 0.18 / asset_vol
                vol_scale = min(vol_scale, 2.5)
                vol_scale = max(vol_scale, 0.2)
                
                # 3. 주문 집행 시 안전 마진 2% 적용 (잔고 초과 방지)
                allocation = ((equity * 0.98) / target_slots) * vol_scale
                    
                quantity = round(allocation / open_price_krw, 4)
                trade_value_krw = open_price_krw * quantity
                cost_krw = trade_value_krw * 0.001
                
                # 가용 예수금 범위를 초과하는 경우 예수금의 98% 한도 내에서 수량 조절
                if balance < (trade_value_krw + cost_krw):
                    quantity = round((balance * 0.98) / open_price_krw, 4)
                    trade_value_krw = open_price_krw * quantity
                    cost_krw = trade_value_krw * 0.001
                    if quantity <= 0 or balance < (trade_value_krw + cost_krw):
                        print(f"   -> Skip {ticker}: Insufficient Balance")
                        alert_system.send_alert(f"Skipped buying {ticker} due to Insufficient Balance. (Balance: {balance:,.0f} KRW, Required: {trade_value_krw + cost_krw:,.0f} KRW)", "CRITICAL")
                        continue
                
                # Entry Execution (Atomic Transaction)
                with self.db.transaction() as conn:
                    self.db.execute('''
                        INSERT INTO positions (ticker, entry_price, quantity, entry_date, current_price, max_price, current_mdd, signal_date, entry_exchange_rate)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (ticker, open_price, quantity, datetime.now().isoformat(), open_price, open_price, 0.0, p['signal_date'], exchange_rate), conn=conn)
                    
                    # Cleanup pending
                    self.db.execute("DELETE FROM pending_orders WHERE id = ?", (p['id'],), conn=conn)
                    
                    # Deduct balance and fee
                    balance -= (trade_value_krw + cost_krw)
                    self.db.execute("UPDATE account SET balance = ?, last_update = ? WHERE id = 1", (balance, datetime.now().isoformat()), conn=conn)
                
                print(f"[BUY] Executed @ Next Open: {ticker} @ {open_price:,.2f} USD ({open_price_krw:,.2f} KRW) (Fee: {cost_krw:,.2f} KRW, Ann Vol: {asset_vol*100:.1f}%)")
                available_slots -= 1
            except Exception as e:
                print(f"   -> Entry error {ticker}: {e}")

    def monitor_and_exit(self):
        """Batch monitoring of existing positions."""
        positions = self.db.fetchall_dict("SELECT * FROM positions")
        if not positions: return
        
        tickers = [p['ticker'] for p in positions]
        dp = DataProvider(self.db.db_path)
        data = dp.get_history(tickers, period="5d", group_by='ticker')
        if data is None:
            print("[ERROR] Failed to fetch market data for monitoring positions.")
            return
        
        for pos in positions:
            ticker = pos['ticker']
            try:
                # Handle single vs multi structure
                if len(tickers) > 1:
                    if ticker not in data.columns.get_level_values(0): continue
                    df = data[ticker]
                else:
                    df = data
                
                if df.empty or 'Close' not in df.columns: continue
                
                # open_price = float(df['Open'].iloc[-1]) # Not strictly needed for monitoring but here for completeness
                curr_price = float(df['Close'].iloc[-1])
                high_price = max(pos['max_price'], curr_price)
                
                curr_drawdown = ((curr_price / high_price) - 1) * 100
                max_mdd = min(pos['current_mdd'] if pos['current_mdd'] is not None else 0.0, curr_drawdown)
                
                self.db.execute('''
                    UPDATE positions SET current_price = ?, max_price = ?, current_mdd = ? WHERE id = ?
                ''', (curr_price, high_price, max_mdd, pos['id']))
            except: continue

    def close_position(self, pos, exit_price, reason, exchange_rate=None):
        ticker = pos['ticker']
        if exchange_rate is None:
            exchange_rate = self.get_exchange_rate()
            
        entry_exchange_rate = pos.get('entry_exchange_rate')
        if entry_exchange_rate is None or entry_exchange_rate == 0.0:
            entry_exchange_rate = exchange_rate
            
        # Calculate original entry cost including 0.1% FX buy premium and 0.1% commission
        entry_price_krw = pos['entry_price'] * (entry_exchange_rate * 1.001)
        entry_value_krw = entry_price_krw * pos['quantity']
        entry_cost_krw = entry_value_krw * 1.001
        
        # Calculate exit trade value including 0.1% FX sell discount and 0.1% commission
        trade_value_krw = exit_price * pos['quantity'] * (exchange_rate * 0.999)
        cost_krw = trade_value_krw * 0.001
        exit_cash_krw = trade_value_krw - cost_krw
        
        pnl_krw = exit_cash_krw - entry_cost_krw
        roi = (exit_price / pos['entry_price'] - 1) * 100
        
        # Signal Accuracy T+5 Check
        t5_profit = False
        try:
            # We check if 5 days have passed since signal_date
            # Simple check for now
            t5_profit = (exit_price > pos['entry_price']) # Mock for current run
        except: pass

        # Get balance first to avoid DB Lock inside transaction block
        balance, _, _ = self.db.get_account_info(exchange_rate=exchange_rate)
        new_balance = balance + exit_cash_krw

        with self.db.transaction() as conn:
            self.db.execute('''
                INSERT INTO history (ticker, entry_price, exit_price, quantity, entry_date, exit_date, pnl, roi, exit_reason, max_mdd_during_trade, t5_profit_attained)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, pos['entry_price'], exit_price, pos['quantity'], pos['entry_date'], datetime.now().isoformat(), pnl_krw, roi, reason, pos['current_mdd'], t5_profit), conn=conn)
            
            self.db.execute("DELETE FROM positions WHERE id = ?", (pos['id'],), conn=conn)
            self.db.execute("UPDATE account SET balance = ?, last_update = ? WHERE id = 1", (new_balance, datetime.now().isoformat()), conn=conn)
            
        print(f"[SELL] {ticker} @ {exit_price:,.2f} USD (Net Exit: {exit_cash_krw:,.2f} KRW) ({reason}) (Fee: {cost_krw:,.2f} KRW, PnL: {pnl_krw:+,.0f} KRW)")

if __name__ == "__main__":
    trader = AntiGravityTrader()
    trader.execute_pending_orders()
