from typing import Optional
from core.data_provider import BaseDataProvider
import sqlite3
from datetime import datetime, timedelta
from lvmb_momentum.data_provider_with_audit import DataProvider
import pandas as pd
from lvmb_momentum.database import PortfolioDB, AntiGravityDB
from lvmb_momentum.alert import alert_system
import config

class MomentumPortfolioTrader:
    def __init__(self, db: Optional[PortfolioDB] = None, data_provider: Optional[BaseDataProvider] = None):
        self.db = db or PortfolioDB()
        self.data_provider = data_provider or DataProvider(self.db.db_path)

    def get_exchange_rate(self):
        try:
            return self.data_provider.get_exchange_rate()
        except Exception as e:
            print(f"Trader failed to fetch exchange rate, using fallback {config.FALLBACK_EXCHANGE_RATE}: {e}")
        return config.FALLBACK_EXCHANGE_RATE

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
        data = self.data_provider.get_history(tickers, period="5d", group_by='ticker')
        if data is None:
            print("[ERROR] Failed to fetch market data for pending orders.")
            alert_system.send_alert("Failed to fetch market data for pending orders.", "CRITICAL")
            return
        
        exchange_rate = self.get_exchange_rate()
        balance, equity, max_equity = self.db.get_account_info(exchange_rate=exchange_rate)
        
        # Portfolio Risk Management (MDD Circuit Breaker)
        portfolio_mdd = ((equity / max_equity) - 1) * 100 if max_equity > 0 else 0
        if portfolio_mdd <= config.PORTFOLIO_MDD_HALT_THRESHOLD:
            print(f"[PORTFOLIO RISK HALT] MDD {portfolio_mdd:.2f}% breached threshold {config.PORTFOLIO_MDD_HALT_THRESHOLD}%. Liquidating all positions and clearing orders.")
            alert_system.send_alert(f"PORTFOLIO RISK HALT: MDD {portfolio_mdd:.2f}% <= {config.PORTFOLIO_MDD_HALT_THRESHOLD}%. Liquidating all positions.", "CRITICAL")
            self.clear_pending_orders()
            self.liquidate_all_positions(reason=f"MDD_HALT ({portfolio_mdd:.2f}%)")
            return
 
        # Dynamic Sizing: Volatility-Inverse weight for target 15 portfolio
        active_pos = self.db.fetchall_dict("SELECT * FROM positions")
        active_count = len(active_pos) if active_pos else 0
        target_slots = config.MAX_PORTFOLIO_SLOTS
        
        # Protect against taking more than 15 slots
        available_slots = target_slots - active_count
        
        # Volatility Sizing Calculation: Get historical volatility over last 60 days
        try:
            hist_data = self.data_provider.get_history(tickers, period="60d")
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
                    if isinstance(hist_data.columns, pd.MultiIndex):
                        if ticker in hist_data.columns.get_level_values(0):
                            df_sub = hist_data[ticker]
                            col_name = 'Adj Close' if 'Adj Close' in df_sub.columns else 'Close'
                            df_ticker = df_sub[col_name]
                        elif ticker in hist_data.columns.get_level_values(1):
                            col_name = 'Adj Close' if 'Adj Close' in hist_data.columns.get_level_values(0) else 'Close'
                            df_ticker = hist_data[(col_name, ticker)]
                        else:
                            df_ticker = None
                    else:
                        col_name = 'Adj Close' if 'Adj Close' in hist_data.columns else 'Close'
                        df_ticker = hist_data[col_name]
                            
                    if df_ticker is not None:
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
                    clip_sum = clip_mask.sum()
                    clip_count = int(clip_sum.item()) if hasattr(clip_sum, 'item') else int(clip_sum)
                    
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
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker in data.columns.get_level_values(0):
                        df = data[ticker]
                    elif ticker in data.columns.get_level_values(1):
                        df = data.xs(ticker, axis=1, level=1)
                    else:
                        print(f"   -> Skip {ticker}: No data found in download result")
                        continue
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
        """Batch monitoring of existing positions and automated exits."""
        positions = self.db.fetchall_dict("SELECT * FROM positions")
        if not positions: return
        
        exchange_rate = self.get_exchange_rate()
        balance, equity, max_equity = self.db.get_account_info(exchange_rate=exchange_rate)
        portfolio_mdd = ((equity / max_equity) - 1) * 100 if max_equity > 0 else 0
        
        # 1. Portfolio Circuit Breaker Check
        if portfolio_mdd <= config.PORTFOLIO_MDD_HALT_THRESHOLD:
            print(f"[PORTFOLIO RISK HALT] MDD {portfolio_mdd:.2f}% breached threshold {config.PORTFOLIO_MDD_HALT_THRESHOLD}%. Liquidating all positions.")
            alert_system.send_alert(f"PORTFOLIO RISK HALT: MDD {portfolio_mdd:.2f}% <= {config.PORTFOLIO_MDD_HALT_THRESHOLD}%. Liquidating all positions.", "CRITICAL")
            self.clear_pending_orders()
            self.liquidate_all_positions(reason=f"MDD_HALT ({portfolio_mdd:.2f}%)")
            return
        
        tickers = [p['ticker'] for p in positions]
        # Download at least 60 days to compute 20-day rolling Z-score
        data = self.data_provider.get_history(tickers, period="60d", group_by='ticker')
        if data is None:
            print("[ERROR] Failed to fetch market data for monitoring positions.")
            return
        
        from lvmb_momentum.strategy import AntiGravityStrategy

        for pos in positions:
            ticker = pos['ticker']
            try:
                # Handle single vs multi structure
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker in data.columns.get_level_values(0):
                        df = data[ticker]
                    elif ticker in data.columns.get_level_values(1):
                        df = data.xs(ticker, axis=1, level=1)
                    else:
                        continue
                else:
                    df = data
                
                if not isinstance(df, pd.DataFrame) or df.empty or ('Close' not in df.columns and 'Adj Close' not in df.columns):
                    continue
                
                col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
                curr_price = float(df[col].iloc[-1])
                high_price = max(pos['max_price'] if pos['max_price'] is not None else curr_price, curr_price)
                
                curr_drawdown = ((curr_price / high_price) - 1) * 100
                max_mdd = min(pos['current_mdd'] if pos['current_mdd'] is not None else 0.0, curr_drawdown)
                
                self.db.execute('''
                    UPDATE positions SET current_price = ?, max_price = ?, current_mdd = ? WHERE id = ?
                ''', (curr_price, high_price, max_mdd, pos['id']))
                pos['current_price'] = curr_price
                pos['max_price'] = high_price
                pos['current_mdd'] = max_mdd

                # Evaluate individual exit triggers (Trailing Stop & Z-Score Breakdown)
                exit_signal = AntiGravityStrategy.evaluate_position_exit(pos, df)
                if exit_signal and exit_signal.action.startswith("SELL"):
                    self.close_position(pos, exit_price=exit_signal.price, reason=exit_signal.action, exchange_rate=exchange_rate)
            except Exception as e:
                print(f"   -> Monitor/Exit error for {ticker}: {e}")
                continue

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
        
        # Calculate exit trade value factoring in slippage penalty, 0.1% FX sell discount, and 0.1% commission
        slippage_rate = getattr(config, 'SLIPPAGE_RATE', 0.002)
        effective_exit_price = exit_price * (1.0 - slippage_rate)
        trade_value_krw = effective_exit_price * pos['quantity'] * (exchange_rate * 0.999)
        fee_rate = getattr(config, 'DEFAULT_TRANSACTION_FEE_RATE', 0.001)
        cost_krw = trade_value_krw * fee_rate
        exit_cash_krw = trade_value_krw - cost_krw
        
        pnl_krw = exit_cash_krw - entry_cost_krw
        roi = (effective_exit_price / pos['entry_price'] - 1) * 100
        
        # Signal Accuracy T+5 Check
        t5_profit = False
        try:
            t5_profit = (effective_exit_price > pos['entry_price'])
        except: pass

        # Get balance first to avoid DB Lock inside transaction block
        balance, _, _ = self.db.get_account_info(exchange_rate=exchange_rate)
        new_balance = balance + exit_cash_krw

        with self.db.transaction() as conn:
            self.db.execute('''
                INSERT INTO history (ticker, entry_price, exit_price, quantity, entry_date, exit_date, pnl, roi, exit_reason, max_mdd_during_trade, t5_profit_attained)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, pos['entry_price'], effective_exit_price, pos['quantity'], pos['entry_date'], datetime.now().isoformat(), pnl_krw, roi, reason, pos['current_mdd'], t5_profit), conn=conn)
            
            self.db.execute("DELETE FROM positions WHERE id = ?", (pos['id'],), conn=conn)
            self.db.execute("UPDATE account SET balance = ?, last_update = ? WHERE id = 1", (new_balance, datetime.now().isoformat()), conn=conn)
            
        print(f"[SELL] {ticker} @ {effective_exit_price:,.2f} USD (Net Exit: {exit_cash_krw:,.2f} KRW) ({reason}) (Fee: {cost_krw:,.2f} KRW, PnL: {pnl_krw:+,.0f} KRW)")

    # =========================================================================
    # Domain Encapsulation Methods (Law of Demeter / Demeter-compliant APIs)
    # =========================================================================
    def get_regime_state(self) -> str:
        """Fetch current macro regime state from database."""
        account_row = self.db.fetchone("SELECT regime_state FROM account WHERE id = 1")
        return account_row[0] if (account_row and account_row[0]) else 'SAFE'

    def update_regime_state(self, new_state: str):
        """Update macro regime state with current timestamp."""
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        self.db.execute("UPDATE account SET regime_state = ?, last_update = ? WHERE id = 1", (new_state, datetime.now(kst).isoformat()))

    def clear_pending_orders(self):
        """Purge all pending buy orders."""
        self.db.execute("DELETE FROM pending_orders")

    def get_active_positions(self) -> list:
        """Fetch all currently open positions."""
        return self.db.fetchall_dict("SELECT * FROM positions")

    def liquidate_all_positions(self, reason: str = "MACRO CRASH"):
        """Liquidate all open positions in a crash/risk-off event."""
        active_pos = self.get_active_positions()
        if not active_pos:
            print("          -> No active positions to liquidate.")
            return
        print(f"          -> Liquidating {len(active_pos)} active positions...")
        for pos in active_pos:
            try:
                exit_price = self.data_provider.get_current_price(pos['ticker'])
                self.close_position(pos, exit_price, reason)
            except Exception as e:
                print(f"Failed to liquidate {pos['ticker']}: {e}")

    def apply_monthly_seed_if_needed(self, current_month_str: str):
        """Applies monthly seed money deposit (+500,000 KRW) once per month."""
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        account_row = self.db.fetchone("SELECT last_seed_addition FROM account WHERE id = 1")
        last_addition_month = account_row[0] if account_row else None
        
        if last_addition_month != current_month_str:
            balance, equity, max_equity = self.db.get_account_info()
            new_balance = balance + config.MONTHLY_SEED_AMOUNT
            self.db.execute(
                "UPDATE account SET balance = ?, last_seed_addition = ?, last_update = ? WHERE id = 1",
                (new_balance, current_month_str, datetime.now(kst).isoformat())
            )
            print(f"   -> Monthly Seed Money Added: +{config.MONTHLY_SEED_AMOUNT:,.0f} KRW (New Balance: {new_balance:,.0f} KRW)")

    def settle_year_end_tax_if_needed(self, current_year_str: str):
        """Settles annual 22% overseas capital gains tax in December on net profits above 2.5M KRW."""
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        tax_record = self.db.fetchone("SELECT id FROM history WHERE ticker = 'TAX_DEDUCTION' AND strftime('%Y', exit_date) = ?", (current_year_str,))
        
        if not tax_record:
            year_pnl_row = self.db.fetchone("SELECT SUM(pnl) FROM history WHERE strftime('%Y', exit_date) = ? AND ticker != 'TAX_DEDUCTION'", (current_year_str,))
            year_pnl = year_pnl_row[0] if year_pnl_row and year_pnl_row[0] is not None else 0.0
            
            if year_pnl > config.TAX_DEDUCTIBLE_LIMIT:
                tax_amount = (year_pnl - config.TAX_DEDUCTIBLE_LIMIT) * config.CAPITAL_GAINS_TAX_RATE
                balance, equity, max_equity = self.db.get_account_info()
                new_balance = balance - tax_amount
                
                with self.db.transaction() as conn:
                    self.db.execute("UPDATE account SET balance = ?, last_update = ? WHERE id = 1", (new_balance, datetime.now(kst).isoformat()), conn=conn)
                    self.db.execute('''
                        INSERT INTO history (ticker, entry_price, exit_price, quantity, entry_date, exit_date, pnl, roi, exit_reason, max_mdd_during_trade, t5_profit_attained)
                        VALUES ('TAX_DEDUCTION', 0, 0, 0, ?, ?, ?, 0, 'YEAR_END_TAX_22', 0, 0)
                    ''', (datetime.now(kst).isoformat(), datetime.now(kst).isoformat(), -tax_amount), conn=conn)
                    
                print(f"   -> [TAX DEDUCTOR] Year-End Capital Gains Tax Deducted: -{tax_amount:,.0f} KRW (Yearly Realized PnL: {year_pnl:,.0f} KRW)")
            else:
                print(f"   -> [TAX DEDUCTOR] No tax due. Yearly Realized PnL: {year_pnl:,.0f} KRW (under {config.TAX_DEDUCTIBLE_LIMIT/1000000:.1f}M limit)")

    def apply_cash_interest_if_needed(self, current_month_str: str):
        """Applies monthly risk-free interest on cash when 100% in cash regime."""
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        active_pos = self.get_active_positions()
        if not active_pos:
            account_row = self.db.fetchone("SELECT last_interest_applied FROM account WHERE id = 1")
            last_interest_month = account_row[0] if account_row else None
            
            if last_interest_month != current_month_str:
                balance, equity, max_equity = self.db.get_account_info()
                interest = balance * config.MONTHLY_CASH_INTEREST_RATE
                new_balance = balance + interest
                self.db.execute(
                    "UPDATE account SET balance = ?, last_interest_applied = ?, last_update = ? WHERE id = 1",
                    (new_balance, current_month_str, datetime.now(kst).isoformat())
                )
                print(f"   -> Risk-Free Interest (+{config.MONTHLY_CASH_INTEREST_RATE*100:.2f}%) Applied: +{interest:,.0f} KRW (New Balance: {new_balance:,.0f} KRW)")
            else:
                print("   -> Risk-Free Interest already applied for this month.")

    def enqueue_report_task(self, payload_dict: dict) -> bool:
        """Serializes and queues a reporting job for background processing."""
        import json
        from dataclasses import is_dataclass, asdict
        try:
            def serialize_helper(obj):
                if hasattr(obj, 'to_dict') and callable(obj.to_dict):
                    return obj.to_dict()
                if is_dataclass(obj):
                    return asdict(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            payload_json = json.dumps(payload_dict, default=serialize_helper)
            self.db.enqueue_report_task(payload_json)
            return True
        except Exception as e:
            print(f"   -> Failed to queue report task: {e}")
            return False

AntiGravityTrader = MomentumPortfolioTrader

if __name__ == "__main__":
    trader = MomentumPortfolioTrader()
    trader.execute_pending_orders()
