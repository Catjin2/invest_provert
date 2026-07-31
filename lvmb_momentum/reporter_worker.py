import os
import json
import traceback
import sys
from dotenv import load_dotenv

from lvmb_momentum.database import AntiGravityDB
from lvmb_momentum.reporter import AntiGravityReporter

def run_worker():
    load_dotenv()
    db = AntiGravityDB()
    
    # 1. Fetch pending tasks (PENDING or FAILED with attempts < 3)
    tasks = db.fetchall_dict('''
        SELECT id, payload, attempts 
        FROM reporting_queue 
        WHERE status = 'PENDING' OR (status = 'FAILED' AND attempts < 3)
        ORDER BY created_at ASC
    ''')
    
    if not tasks:
        print("No pending reporting tasks found in queue.")
        return

    print(f"Found {len(tasks)} reporting task(s) to process.")
    
    # Setup Notion tokens
    token = os.getenv("NOTION_REPORT_TOKEN") or os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_REPORT_DATABASE_ID") or os.getenv("NOTION_DATABASE_ID")
    
    if not token or not db_id:
        print("[ERROR] Notion credentials missing from environment. Cannot process reporting queue.")
        return

    for task in tasks:
        task_id = task['id']
        attempts = task['attempts']
        
        # Mark as PROCESSING to avoid concurrent processing
        db.execute("UPDATE reporting_queue SET status = 'PROCESSING' WHERE id = ?", (task_id,))
        
        try:
            print(f"\n--- Processing Task ID {task_id} (Attempt {attempts + 1}) ---")
            payload = json.loads(task['payload'])
            
            reporter = AntiGravityReporter(token, db_id)
            reporter.generate_summary_report(
                category="General",
                all_signals=payload.get("all_signals"),
                is_safe=payload.get("is_safe", True),
                regime_slots=payload.get("regime_slots", 15)
            )
            
            # Mark as COMPLETED on success
            db.execute(
                "UPDATE reporting_queue SET status = 'COMPLETED', attempts = ?, last_error = NULL WHERE id = ?",
                (attempts + 1, task_id)
            )
            print(f"Task ID {task_id} successfully processed and marked COMPLETED.")
            
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"[ERROR] Task ID {task_id} failed: {e}")
            # Mark as FAILED, increment attempts and store the error trace
            db.execute('''
                UPDATE reporting_queue 
                SET status = 'FAILED', attempts = ?, last_error = ? 
                WHERE id = ?
            ''', (attempts + 1, err_msg, task_id))

if __name__ == "__main__":
    # Redirect stdout/stderr to log file ONLY when run as a standalone process
    log_dir = "reports"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "worker_output.log")
    sys.stdout = open(log_path, "a", encoding="utf-8")
    sys.stderr = sys.stdout
    
    # Set UTF-8 encoding for standard outputs
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
        except:
            pass
            
    run_worker()
