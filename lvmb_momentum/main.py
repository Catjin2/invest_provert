import os
import json
import time
from datetime import datetime, timedelta
import pytz
from lvmb_momentum.data_provider_with_audit import DataProvider
from dotenv import load_dotenv
from lvmb_momentum.universe import AssetUniverse
from lvmb_momentum.strategy import LvmbMomentumStrategy
from lvmb_momentum.trader import MomentumPortfolioTrader
from lvmb_momentum.database import PortfolioDB
from lvmb_momentum.reporter import MomentumPortfolioReporter
from lvmb_momentum.alert import alert_system
import config

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
    print(f"[시스템 B] 다중 주기 시계열 모멘텀 및 동적 자산배분 운용 엔진")
    print(f"   실행 일시 (KST): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # Composition Root: Dependency Injection Assembly
    db = PortfolioDB(config.DEFAULT_DB_PATH)
    data_provider = DataProvider(db.db_path)
    trader = MomentumPortfolioTrader(db=db, data_provider=data_provider)
    strategy = LvmbMomentumStrategy(data_provider=data_provider)
    universe_loader = AssetUniverse()
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
    prev_state = trader.get_regime_state()
    
    # Global Safety Check (with hysteresis buffer)
    is_safe, new_state, r12 = strategy.check_global_safety(prev_state)
    
    # Save the new state back to the database
    trader.update_regime_state(new_state)
    
    if not is_safe:
        print(f"[GLOBAL EXIT] Safety Triggered: QQQ (R12 = {r12*100:.2f}%)")
        print(f"          -> SHIFTING TO 100% CASH REGIME (Current State: {new_state})")
        alert_system.send_alert(f"GLOBAL RISK-OFF TRIGGERED: QQQ (R12 = {r12*100:.2f}%). Shifting portfolio to 100% Cash Regime and liquidating all active positions.", "CRITICAL")
        
        # 1. Clear any pending new signals first to prevent accidental fills
        trader.clear_pending_orders()
        
        # 2. Liquidate all active positions immediately
        trader.liquidate_all_positions("MACRO CRASH (QQQ R12 <= -2%)")
        
    else:
        # Normal Regime: Only generate new signals if today is the LAST trading day of the month.
        # Check if tomorrow is a new month using a simple timedelta check.
        tomorrow = now + timedelta(days=1)
        next_week = now + timedelta(days=3)
        # simplistic trading day month-end check (if tomorrow or the day after weekend is new month)
        is_month_end = tomorrow.month != now.month or next_week.month != now.month
        
        if is_month_end:
            current_month_str = now.strftime('%Y-%m')
            # 1. Monthly Seed Money Addition (+500,000 KRW)
            trader.apply_monthly_seed_if_needed(current_month_str)

            # 2. Year-End Tax Settlement (December only)
            if now.month == 12:
                current_year_str = str(now.year)
                trader.settle_year_end_tax_if_needed(current_year_str)

            # 3. Risk-Free Interest (Cash-only regime)
            print("\n[MONTH END] Checking for Risk-Free Interest (Cash-only regime)...")
            trader.apply_cash_interest_if_needed(current_month_str)
        
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
            
        # Select absolute top signals
        all_signals = sorted(all_signals, key=lambda x: x.score if hasattr(x, 'score') else x['score'], reverse=True)[:config.TOP_SIGNALS_LIMIT]

        # Record Pending Signals
        if all_signals:
            print(f"\nSignals Captured (Top {config.TOP_SIGNALS_LIMIT}): {len(all_signals)} items")
            # Clear old pending signals
            trader.clear_pending_orders()
            for sig in all_signals:
                trader.add_pending_order(sig)
        else:
            print("\nNo new signals found in current batch.")

    # --- STAGE 4: Advanced Reporting (Decoupled & Asynchronous) ---
    print("\n4. Queueing Notion Report for Background Processing...")
    payload_data = {
        "all_signals": all_signals,
        "is_safe": is_safe,
        "regime_slots": (config.MAX_PORTFOLIO_SLOTS if is_safe else 0)
    }
    should_launch_worker = trader.enqueue_report_task(payload_data)
    if should_launch_worker:
        print("   -> Task successfully queued.")

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
