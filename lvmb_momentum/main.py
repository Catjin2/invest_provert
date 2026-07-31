import os
import json
import time
from datetime import datetime, timedelta
import pytz
from lvmb_momentum.data_provider_with_audit import DataProvider
from dotenv import load_dotenv
from lvmb_momentum.universe import AntiGravityUniverse
from lvmb_momentum.strategy import AntiGravityStrategy
from lvmb_momentum.trader import AntiGravityTrader
from lvmb_momentum.database import AntiGravityDB
from lvmb_momentum.reporter import AntiGravityReporter
from lvmb_momentum.alert import alert_system

import sys

def run_invest_cycle():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore
    load_dotenv()
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    print(f"\n" + "="*50)
    print(f"LV-MB & CTA Strategy Simulation")
    print(f"   Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    trader = AntiGravityTrader()
    strategy = AntiGravityStrategy()
    universe_loader = AntiGravityUniverse()
    all_signals = []
    
    # --- STAGE 1: Market Open Execution ---
    print("\n1. Processing Pending Orders (Market Open Entry)...")
    trader.execute_pending_orders()
    
    # --- STAGE 2: Position Management ---
    print("\n2. Monitoring Active Portfolio...")
    trader.monitor_and_exit()
    
    # --- STAGE 3: Universe Screening (MONTH END ONLY) ---
    print("\n3. Scanning for NEW Stability & Trend Signals (Monthly Batch)...")
    
    # Fetch current regime_state
    account_row = trader.db.fetchone("SELECT regime_state FROM account WHERE id = 1")
    prev_state = account_row[0] if (account_row and account_row[0]) else 'SAFE'
    
    # Global Safety Check (with hysteresis buffer)
    is_safe, new_state, r12 = strategy.check_global_safety(prev_state)
    
    # Save the new state back to the database
    trader.db.execute("UPDATE account SET regime_state = ?, last_update = ? WHERE id = 1", (new_state, datetime.now(kst).isoformat()))
    
    if not is_safe:
        print(f"[GLOBAL EXIT] Safety Triggered: QQQ (R12 = {r12*100:.2f}%)")
        print(f"          -> SHIFTING TO 100% CASH REGIME (Current State: {new_state})")
        alert_system.send_alert(f"GLOBAL RISK-OFF TRIGGERED: QQQ (R12 = {r12*100:.2f}%). Shifting portfolio to 100% Cash Regime and liquidating all active positions.", "CRITICAL")
        
        # 1. Clear any pending new signals first to prevent accidental fills
        trader.db.execute("DELETE FROM pending_orders")
        
        # 2. Liquidate all active positions immediately
        active_pos = trader.db.fetchall_dict("SELECT * FROM positions")
        if active_pos:
            print(f"          -> Liquidating {len(active_pos)} active positions...")
            for pos in active_pos:
                try:
                    exit_price = DataProvider().get_current_price(pos['ticker'])
                    trader.close_position(pos, exit_price, "MACRO CRASH (QQQ R12 <= -2%)")
                except Exception as e:
                    print(f"Failed to liquidate {pos['ticker']}: {e}")
        else:
            print("          -> No active positions to liquidate.")
        
    else:
        # Normal Regime: Only generate new signals if today is the LAST trading day of the month.
        # Check if tomorrow is a new month using a simple timedelta check.
        tomorrow = now + timedelta(days=1)
        next_week = now + timedelta(days=3)
        # simplistic trading day month-end check (if tomorrow or the day after weekend is new month)
        is_month_end = tomorrow.month != now.month or next_week.month != now.month
        
        if is_month_end:
            # 1. Monthly Seed Money Addition (+500,000 KRW)
            current_month_str = now.strftime('%Y-%m')
            account_row = trader.db.fetchone("SELECT last_seed_addition FROM account WHERE id = 1")
            last_addition_month = account_row[0] if account_row else None
            
            if last_addition_month != current_month_str:
                balance, equity, max_equity = trader.db.get_account_info()
                new_balance = balance + 500000
                trader.db.execute(
                    "UPDATE account SET balance = ?, last_seed_addition = ?, last_update = ? WHERE id = 1",
                    (new_balance, current_month_str, datetime.now(kst).isoformat())
                )
                print(f"   -> Monthly Seed Money Added: +500,000 KRW (New Balance: {new_balance:,.0f} KRW)")

            # 2. Year-End Tax Settlement (December only)
            if now.month == 12:
                current_year_str = str(now.year)
                tax_record = trader.db.fetchone("SELECT id FROM history WHERE ticker = 'TAX_DEDUCTION' AND strftime('%Y', exit_date) = ?", (current_year_str,))
                
                if not tax_record:
                    year_pnl_row = trader.db.fetchone("SELECT SUM(pnl) FROM history WHERE strftime('%Y', exit_date) = ? AND ticker != 'TAX_DEDUCTION'", (current_year_str,))
                    year_pnl = year_pnl_row[0] if year_pnl_row and year_pnl_row[0] is not None else 0.0
                    
                    if year_pnl > 2500000.0:
                        tax_amount = (year_pnl - 2500000.0) * 0.22
                        balance, equity, max_equity = trader.db.get_account_info()
                        new_balance = balance - tax_amount
                        
                        with trader.db.transaction() as conn:
                            trader.db.execute("UPDATE account SET balance = ?, last_update = ? WHERE id = 1", (new_balance, datetime.now(kst).isoformat()), conn=conn)
                            trader.db.execute('''
                                INSERT INTO history (ticker, entry_price, exit_price, quantity, entry_date, exit_date, pnl, roi, exit_reason, max_mdd_during_trade, t5_profit_attained)
                                VALUES ('TAX_DEDUCTION', 0, 0, 0, ?, ?, ?, 0, 'YEAR_END_TAX_22', 0, 0)
                            ''', (datetime.now(kst).isoformat(), datetime.now(kst).isoformat(), -tax_amount), conn=conn)
                            
                        print(f"   -> [TAX DEDUCTOR] Year-End Capital Gains Tax Deducted: -{tax_amount:,.0f} KRW (Yearly Realized PnL: {year_pnl:,.0f} KRW)")
                    else:
                        print(f"   -> [TAX DEDUCTOR] No tax due. Yearly Realized PnL: {year_pnl:,.0f} KRW (under 2.5M limit)")

            # 3. Risk-Free Interest (Cash-only regime)
            print("\n[MONTH END] Checking for Risk-Free Interest (Cash-only regime)...")
            active_pos = trader.db.fetchall_dict("SELECT * FROM positions")
            if not active_pos:
                account_row = trader.db.fetchone("SELECT last_interest_applied FROM account WHERE id = 1")
                last_interest_month = account_row[0] if account_row else None
                
                if last_interest_month != current_month_str:
                    balance, equity, max_equity = trader.db.get_account_info()
                    interest = balance * 0.0033
                    new_balance = balance + interest
                    trader.db.execute(
                        "UPDATE account SET balance = ?, last_interest_applied = ?, last_update = ? WHERE id = 1",
                        (new_balance, current_month_str, datetime.now(kst).isoformat())
                    )
                    print(f"   -> Risk-Free Interest (+0.33%) Applied: +{interest:,.0f} KRW (New Balance: {new_balance:,.0f} KRW)")
                else:
                    print("   -> Risk-Free Interest already applied for this month.")
        
        # For simulation, we will run the screening everyday, but in production we need month-end check.
        
        uni = universe_loader.load_universe()
        all_tickers = uni['nasdaq_100']
        
        chunk_size = 50
        all_signals = []
        for i in range(0, len(all_tickers), chunk_size):
            chunk = all_tickers[i:i+chunk_size]
            signals = strategy.batch_screen(chunk)
            all_signals.extend(signals)
            time.sleep(1) # Gentle behavior
            
        # Select absolute top 15 from all generated signals
        all_signals = sorted(all_signals, key=lambda x: x['score'], reverse=True)[:15]

        # Record Pending Signals
        if all_signals:
            print(f"\nSignals Captured (Top 15): {len(all_signals)} items")
            # Clear old pending signals
            trader.db.execute("DELETE FROM pending_orders")
            for sig in all_signals:
                trader.add_pending_order(sig)
        else:
            print("\nNo new signals found in current batch.")

    # --- STAGE 4: Advanced Reporting (Decoupled & Asynchronous) ---
    print("\n4. Queueing Notion Report for Background Processing...")
    should_launch_worker = False
    try:
        import subprocess
        
        # Serialize report parameters
        payload_data = {
            "all_signals": all_signals,
            "is_safe": is_safe,
            "regime_slots": (15 if is_safe else 0)
        }
        payload_json = json.dumps(payload_data)
        
        # Insert reporting task into SQLite database queue
        trader.db.execute('''
            INSERT INTO reporting_queue (payload, status)
            VALUES (?, 'PENDING')
        ''', (payload_json,))
        print("   -> Task successfully queued.")
        should_launch_worker = True
        
    except Exception as e:
        print(f"   -> Failed to queue report task: {e}")

    print("\n" + "="*50)
    print(f"Cycle Finished: {datetime.now(kst).strftime('%H:%M:%S')}")
    print("="*50 + "\n")
    
    # Spawn background worker after main cycle completes to prevent database lock contention
    if should_launch_worker:
        try:
            import threading
            from lvmb_momentum.reporter_worker import run_worker
            threading.Thread(target=run_worker).start()
            print("Asynchronous background worker thread started after main cycle finished.")
        except Exception as e:
            print(f"Failed to launch background worker: {e}")

if __name__ == "__main__":
    try:
        run_invest_cycle()
    except Exception as e:
        print(f"[CRITICAL ERROR] Main loop cycle crashed: {e}")
        try:
            alert_system.send_alert(f"Main loop cycle crashed with exception: {e}", "CRITICAL")
        except:
            pass
        raise e
