# 🗂️ invest_provert Codebase Index & Architecture Map

This document provides an automatically generated index of the codebase, describing the file structure, classes, methods, and functions.

## 🌳 Directory Tree

```text
├── .env
├── .github
│   └── workflows
│       └── daily_run.yml
├── .gitignore
├── PROJECT_INDEX.md
├── README.md
├── core
│   ├── __init__.py
│   └── data_provider.py
├── github_uploader.py
├── interview_prep_notes.md
├── invest_standalone.db
├── invest_universe.json
├── lvmb_momentum
│   ├── __init__.py
│   ├── alert.py
│   ├── data_auditor.py
│   ├── data_provider_with_audit.py
│   ├── database.py
│   ├── main.py
│   ├── reporter.py
│   ├── reporter_worker.py
│   ├── strategy.py
│   ├── trader.py
│   └── universe.py
├── requirements.txt
├── run_insider_alert.bat
├── run_lvmb_simulation.bat
└── sec_insider
    ├── __init__.py
    ├── backtester.py
    ├── data_fetcher.py
    ├── main.py
    └── notion_logger.py
```

## 📄 File Details

### 📄 [.env](file:///c:/Users/catji/Projects/invest_provert/.env)

- **Relative Path**: `.env`
- **Description**: Environment variables configuration file

---

### 📄 [.gitignore](file:///c:/Users/catji/Projects/invest_provert/.gitignore)

- **Relative Path**: `.gitignore`
- **Description**: Git ignore patterns file

---

### 📄 [PROJECT_INDEX.md](file:///c:/Users/catji/Projects/invest_provert/PROJECT_INDEX.md)

- **Relative Path**: `PROJECT_INDEX.md`
- **Description**: Markdown document: 🗂️ invest_provert Codebase Index & Architecture Map

---

### 📄 [README.md](file:///c:/Users/catji/Projects/invest_provert/README.md)

- **Relative Path**: `README.md`
- **Description**: Markdown document: invest_provert

---

### 📄 [core/data_provider.py](file:///c:/Users/catji/Projects/invest_provert/core/data_provider.py)

- **Relative Path**: `core/data_provider.py`
  - **Class**: `CoreDataProvider`
    - *Methods*:
      - `__init__(self)`
      - `_download_from_yahoo_query_direct(self, ticker, period, start, end)`
      - `_forward_fill_to_today(self, df)`
      - `_fetch_single_ticker(self, ticker, period, start, end)`
      - `get_history(self, tickers, period, start, end, group_by)`
      - `_reconstruct_multi_df(self, ticker_dfs)`
      - `get_current_price(self, ticker)`
      - `get_exchange_rate(self)`

---

### 📄 [github_uploader.py](file:///c:/Users/catji/Projects/invest_provert/github_uploader.py)

- **Relative Path**: `github_uploader.py`
  - **Function**: `upload_image_to_github(filepath)`

---

### 📄 [interview_prep_notes.md](file:///c:/Users/catji/Projects/invest_provert/interview_prep_notes.md)

- **Relative Path**: `interview_prep_notes.md`
- **Description**: Markdown document: 🎓 대학원 및 기술 면접 대비 프로젝트 심층 분석 가이드 (Deep Dive & Study)

---

### 📄 [invest_standalone.db](file:///c:/Users/catji/Projects/invest_provert/invest_standalone.db)

- **Relative Path**: `invest_standalone.db`
- **Description**: SQLite database file

---

### 📄 [invest_universe.json](file:///c:/Users/catji/Projects/invest_provert/invest_universe.json)

- **Relative Path**: `invest_universe.json`
- **Description**: JSON Configuration / Data file

---

### 📄 [lvmb_momentum/alert.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/alert.py)

- **Relative Path**: `lvmb_momentum/alert.py`
  - **Class**: `AntiGravityAlert`
    - *Methods*:
      - `__new__(cls, *args, **kwargs)`
      - `_init_alert(self)`
      - `_send_telegram(self, message)`
      - `_send_slack(self, message)`
      - `_dispatch(self, message, level)`
      - `send_alert(self, message, level)`

---

### 📄 [lvmb_momentum/data_auditor.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/data_auditor.py)

- **Relative Path**: `lvmb_momentum/data_auditor.py`
  - **Class**: `DataAuditor`
    - *Methods*:
      - `__init__(self, db_path)`
      - `audit_dataframe(self, ticker, df, vol_dict)`

---

### 📄 [lvmb_momentum/data_provider_with_audit.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/data_provider_with_audit.py)

- **Relative Path**: `lvmb_momentum/data_provider_with_audit.py`
  - **Class**: `DataProvider`
    - *Methods*:
      - `__init__(self, db_path)`
      - `_fetch_single_ticker(self, ticker, period, start, end)`
      - `get_history(self, tickers, period, start, end, group_by)`
      - `get_current_price(self, ticker)`
      - `get_exchange_rate(self)`

---

### 📄 [lvmb_momentum/database.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/database.py)

- **Relative Path**: `lvmb_momentum/database.py`
  - **Class**: `AntiGravityDB`
    - *Methods*:
      - `__init__(self, db_path)`
      - `_init_db(self)`
      - `get_account_info(self, exchange_rate)`
      - `transaction(self)`
      - `execute(self, query, params, conn)`
      - `fetchone(self, query, params, conn)`
      - `fetchall_dict(self, query, params, conn)`
      - `save_prices(self, ticker, df)`
      - `get_cached_prices(self, ticker, start_date, end_date)`
      - `get_last_cached_price(self, ticker)`
      - `log_quality_audit(self, ticker, total_days, anomaly_days, error_rate, status, details)`
      - `reset_database(self)`

---

### 📄 [lvmb_momentum/main.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/main.py)

- **Relative Path**: `lvmb_momentum/main.py`
  - **Function**: `run_invest_cycle()`

---

### 📄 [lvmb_momentum/reporter.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/reporter.py)

- **Relative Path**: `lvmb_momentum/reporter.py`
  - **Class**: `AntiGravityReporter`
    - *Methods*:
      - `__init__(self, token, database_id)`
      - `_get_title_property_name(self)`
      - `generate_summary_report(self, category, all_signals, is_safe, regime_slots)`
      - `_create_page(self, properties, blocks)`

---

### 📄 [lvmb_momentum/reporter_worker.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/reporter_worker.py)

- **Relative Path**: `lvmb_momentum/reporter_worker.py`
  - **Function**: `run_worker()`

---

### 📄 [lvmb_momentum/strategy.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/strategy.py)

- **Relative Path**: `lvmb_momentum/strategy.py`
  - **Class**: `AntiGravityStrategy`
    - *Methods*:
      - `__init__(self)`
      - `batch_screen(self, tickers)`
      - `check_global_safety(self, prev_state, tickers)`

---

### 📄 [lvmb_momentum/trader.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/trader.py)

- **Relative Path**: `lvmb_momentum/trader.py`
  - **Class**: `AntiGravityTrader`
    - *Methods*:
      - `__init__(self, db_path)`
      - `get_exchange_rate(self)`
      - `add_pending_order(self, signal_data)`
      - `execute_pending_orders(self)`
      - `monitor_and_exit(self)`
      - `close_position(self, pos, exit_price, reason, exchange_rate)`

---

### 📄 [lvmb_momentum/universe.py](file:///c:/Users/catji/Projects/invest_provert/lvmb_momentum/universe.py)

- **Relative Path**: `lvmb_momentum/universe.py`
  - **Class**: `AntiGravityUniverse`
    - *Methods*:
      - `__init__(self)`
      - `get_nasdaq100(self)`
      - `load_base_universe(self)`
      - `get_universe_for_year(self, year)`
      - `update_universe(self)`
      - `load_universe(self, year)`

---

### 📄 [requirements.txt](file:///c:/Users/catji/Projects/invest_provert/requirements.txt)

- **Relative Path**: `requirements.txt`
- **Description**: Python project dependencies file

---

### 📄 [run_insider_alert.bat](file:///c:/Users/catji/Projects/invest_provert/run_insider_alert.bat)

- **Relative Path**: `run_insider_alert.bat`
- **Description**: Windows Batch Script

---

### 📄 [run_lvmb_simulation.bat](file:///c:/Users/catji/Projects/invest_provert/run_lvmb_simulation.bat)

- **Relative Path**: `run_lvmb_simulation.bat`
- **Description**: Windows Batch Script

---

### 📄 [sec_insider/backtester.py](file:///c:/Users/catji/Projects/invest_provert/sec_insider/backtester.py)

- **Relative Path**: `sec_insider/backtester.py`
  - **Class**: `Backtester`
    - *Methods*:
      - `__init__(self, investment_amount)`
      - `calculate_return(self, ticker, signal_date_str)`

---

### 📄 [sec_insider/data_fetcher.py](file:///c:/Users/catji/Projects/invest_provert/sec_insider/data_fetcher.py)

- **Relative Path**: `sec_insider/data_fetcher.py`
  - **Class**: `DataFetcher`
    - *Methods*:
      - `__init__(self)`
      - `get_insider_signals(self)`

---

### 📄 [sec_insider/main.py](file:///c:/Users/catji/Projects/invest_provert/sec_insider/main.py)

- **Relative Path**: `sec_insider/main.py`
  - **Function**: `main()`

---

### 📄 [sec_insider/notion_logger.py](file:///c:/Users/catji/Projects/invest_provert/sec_insider/notion_logger.py)

- **Relative Path**: `sec_insider/notion_logger.py`
  - **Class**: `NotionLogger`
    - *Methods*:
      - `__init__(self)`
      - `add_row(self, data)`

---