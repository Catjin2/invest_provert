import sqlite3
import os
from contextlib import contextmanager

class AntiGravityDB:
    def __init__(self, db_path="invest_standalone.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Account table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY,
                balance REAL,
                equity REAL,
                max_equity REAL DEFAULT 10000000.0,
                last_seed_addition TEXT,
                regime_state TEXT DEFAULT 'SAFE',
                last_update DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        try:
            cursor.execute("ALTER TABLE account ADD COLUMN max_equity REAL DEFAULT 10000000.0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE account ADD COLUMN last_seed_addition TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE account ADD COLUMN regime_state TEXT DEFAULT 'SAFE'")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE account ADD COLUMN last_interest_applied TEXT")
        except sqlite3.OperationalError:
            pass
        
        # Positions table
        # entry_mdd: historical mdd at time of entry (should be < 10%)
        # current_mdd: max drawdown since entry
        # max_price: max price observed since entry (for recovery tracking)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE,
                entry_price REAL,
                quantity INTEGER,
                entry_date DATETIME,
                current_price REAL,
                max_price REAL,
                current_mdd REAL,
                entry_mdd REAL, 
                signal_date DATETIME,
                entry_exchange_rate REAL
            )
        ''')
        
        try:
            cursor.execute("ALTER TABLE positions ADD COLUMN entry_exchange_rate REAL")
        except sqlite3.OperationalError:
            pass
        
        # Historical trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity INTEGER,
                entry_date DATETIME,
                exit_date DATETIME,
                pnl REAL,
                roi REAL,
                exit_reason TEXT,
                max_mdd_during_trade REAL,
                recovery_days INTEGER,
                t5_profit_attained BOOLEAN
            )
        ''')
        
        # Pending Orders (Captured at Close, executed at next Open)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE,
                signal_price REAL,
                signal_date DATETIME,
                order_type TEXT DEFAULT 'BUY'
            )
        ''')
        
        # Marketplace Index Baseline (for Relative MDD)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_baseline (
                date TEXT PRIMARY KEY,
                ndx_close REAL,
                k100_close REAL,
                ndx_mdd REAL,
                k100_mdd REAL
            )
        ''')

        # Reporting Queue Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reporting_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                last_error TEXT
            )
        ''')

        # Data Health Logs Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_health_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                ticker TEXT,
                data_source TEXT,
                total_days INTEGER,
                valid_days INTEGER,
                clip_count INTEGER,
                raw_ann_vol REAL,
                clipped_ann_vol REAL,
                vol_scale REAL
            )
        ''')

        # Price Cache Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_cache (
                ticker TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume INTEGER,
                PRIMARY KEY (ticker, date)
            )
        ''')

        # Data Quality Audit Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_quality_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                ticker TEXT,
                total_days INTEGER,
                anomaly_days INTEGER,
                error_rate REAL,
                status TEXT,
                details TEXT
            )
        ''')
        
        # Initialize account
        cursor.execute("SELECT COUNT(*) FROM account")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO account (id, balance, equity, max_equity) VALUES (1, 10000000.0, 10000000.0, 10000000.0)")
        
        conn.commit()
        conn.close()

    def get_account_info(self, exchange_rate=None):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT balance, max_equity FROM account WHERE id = 1")
            res = cursor.fetchone()
            balance = res[0] if res else 0.0
            max_equity = res[1] if res else 10000000.0
        except sqlite3.OperationalError:
            cursor.execute("SELECT balance FROM account WHERE id = 1")
            res = cursor.fetchone()
            balance = res[0] if res else 0.0
            max_equity = 10000000.0
            
        cursor.execute("SELECT SUM(current_price * quantity) FROM positions")
        pos_val_usd = cursor.fetchone()[0]
        pos_val_usd = pos_val_usd if pos_val_usd else 0.0
        
        if exchange_rate is None:
            try:
                cursor.execute("SELECT close FROM price_cache WHERE ticker = 'USDKRW=X' ORDER BY date DESC LIMIT 1")
                res = cursor.fetchone()
                if res and res[0]:
                    exchange_rate = float(res[0])
                else:
                    exchange_rate = 1350.0
            except Exception:
                exchange_rate = 1350.0
                
        pos_val_krw = pos_val_usd * exchange_rate
        equity = balance + pos_val_krw
        
        if equity > max_equity:
            max_equity = equity
            try:
                cursor.execute("UPDATE account SET max_equity = ?, equity = ? WHERE id = 1", (max_equity, equity))
                conn.commit()
            except sqlite3.OperationalError:
                pass
                
        conn.close()
        return balance, equity, max_equity

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute(self, query, params=(), conn=None):
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute(query, params)
        else:
            conn_local = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn_local.cursor()
            cursor.execute(query, params)
            conn_local.commit()
            conn_local.close()

    def fetchone(self, query, params=(), conn=None):
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
        else:
            conn_local = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn_local.cursor()
            cursor.execute(query, params)
            res = cursor.fetchone()
            conn_local.close()
            return res

    def fetchall_dict(self, query, params=(), conn=None):
        if conn is not None:
            old_row_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
            conn.row_factory = old_row_factory
            return rows
        else:
            conn_local = sqlite3.connect(self.db_path, timeout=30.0)
            conn_local.row_factory = sqlite3.Row
            cursor = conn_local.cursor()
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
            conn_local.close()
            return rows

    def save_prices(self, ticker, df):
        if df is None or df.empty:
            return
        
        import pandas as pd
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Ensure we have standard DataFrame columns, handling both strings and MultiIndex tuples
        cols = {}
        for col in df.columns:
            col_name = col[0] if isinstance(col, tuple) else col
            col_key = col_name.lower().replace(" ", "_")
            cols[col_key] = col
            
        open_col = cols.get("open")
        high_col = cols.get("high")
        low_col = cols.get("low")
        close_col = cols.get("close")
        adj_close_col = cols.get("adj_close") or cols.get("adj_close")
        vol_col = cols.get("volume")
        
        for idx, row in df.iterrows():
            if isinstance(idx, (datetime, pd.Timestamp)):
                date_str = idx.strftime("%Y-%m-%d")
            else:
                date_str = str(idx)[:10]
                
            open_val = float(row[open_col]) if open_col is not None and pd.notna(row[open_col]) else None
            high_val = float(row[high_col]) if high_col is not None and pd.notna(row[high_col]) else None
            low_val = float(row[low_col]) if low_col is not None and pd.notna(row[low_col]) else None
            close_val = float(row[close_col]) if close_col is not None and pd.notna(row[close_col]) else None
            adj_close_val = float(row[adj_close_col]) if adj_close_col is not None and pd.notna(row[adj_close_col]) else close_val
            vol_val = int(row[vol_col]) if vol_col is not None and pd.notna(row[vol_col]) else 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, adj_close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, date_str, open_val, high_val, low_val, close_val, adj_close_val, vol_val))
            
        conn.commit()
        conn.close()

    def get_cached_prices(self, ticker, start_date, end_date=None):
        import pandas as pd
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        
        query = "SELECT date, open, high, low, close, adj_close, volume FROM price_cache WHERE ticker = ? AND date >= ?"
        params = [ticker, start_date]
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
            
        query += " ORDER BY date ASC"
        
        df = pd.read_sql_query(query, conn, index_col="date", params=params)
        conn.close()
        
        if df.empty:
            return None
            
        df.columns = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        df.index = pd.to_datetime(df.index)
        return df

    def get_last_cached_price(self, ticker):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("SELECT close, adj_close, date FROM price_cache WHERE ticker = ? ORDER BY date DESC LIMIT 1", (ticker,))
        res = cursor.fetchone()
        conn.close()
        if res:
            return {"close": res[0], "adj_close": res[1], "date": res[2]}
        return None

    def log_quality_audit(self, ticker, total_days, anomaly_days, error_rate, status, details):
        self.execute('''
            INSERT INTO data_quality_audit (ticker, total_days, anomaly_days, error_rate, status, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticker, total_days, anomaly_days, error_rate, status, details))

    def reset_database(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM positions")
        cursor.execute("DELETE FROM history")
        cursor.execute("DELETE FROM pending_orders")
        cursor.execute("DELETE FROM account")
        cursor.execute("INSERT INTO account (id, balance, equity, max_equity) VALUES (1, 10000000.0, 10000000.0, 10000000.0)")
        conn.commit()
        conn.close()
        print("Database has been reset to 10,000,000 KRW seed money and empty positions.")

if __name__ == "__main__":
    db = AntiGravityDB()
    print("Anti-Gravity Standalone DB Initialized.")
