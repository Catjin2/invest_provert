import pandas as pd
import requests
import os
import json
import matplotlib
matplotlib.use('Agg')  # Set non-GUI backend for thread-safe headless execution
import matplotlib.pyplot as plt
from lvmb_momentum.data_provider_with_audit import DataProvider
from datetime import datetime, timedelta
from lvmb_momentum.database import AntiGravityDB
from github_uploader import upload_image_to_github

class AntiGravityReporter:
    def __init__(self, token=None, database_id=None):
        self.token = token or os.getenv("NOTION_REPORT_TOKEN") or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_REPORT_DATABASE_ID") or os.getenv("NOTION_DATABASE_ID")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        self.db = AntiGravityDB()

    def _get_title_property_name(self):
        """Notion schema check for Title property name (Title or Name)"""
        url = f"https://api.notion.com/v1/databases/{self.database_id}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            props = response.json().get("properties", {})
            for name, data in props.items():
                if data["type"] == "title":
                    return name
        return "Name"

    def generate_summary_report(self, category="General", all_signals=None, is_safe=True, regime_slots=15):
        print(f"Generating {category} Summary Report...")
        
        # Fetch USD/KRW exchange rate
        exchange_rate = 1350.0
        try:
            exchange_rate = DataProvider().get_exchange_rate()
        except Exception as e:
            print(f"Reporter failed to fetch exchange rate: {e}")

        # 1. Fetch Data from local DB
        balance, equity, max_equity = self.db.get_account_info(exchange_rate=exchange_rate)
        positions = self.db.fetchall_dict("SELECT * FROM positions")
        
        # 2. Portfolio Metrics Reconstruction
        total_roi_raw = (equity / 10000000.0 - 1) # Assuming original capital 10M
        total_roi_pct = total_roi_raw * 100
        net_profit = equity - 10000000.0
        
        # Multi-ticker MDD (Aggregate)
        portfolio_mdd_raw = (equity / max_equity - 1) if max_equity > 0 else 0.0
        portfolio_mdd_pct = portfolio_mdd_raw * 100
        
        # 3. Enhanced Metrics Calculation (last 120 days)
        sharpe_ratio = 0.0
        beta = 1.0
        relative_mdd_pct = 0.0
        
        try:
            tickers = [p['ticker'] for p in positions]
            if tickers:
                start_date = (datetime.now() - timedelta(days=150)).strftime('%Y-%m-%d')
                hist_data = DataProvider().get_history(tickers + ["QQQ"], start=start_date)
                
                if isinstance(hist_data, pd.DataFrame) and not hist_data.empty:
                    close = hist_data['Adj Close'] if 'Adj Close' in hist_data.columns else hist_data['Close']
                    assert isinstance(close, pd.DataFrame)
                    returns = close.pct_change().dropna()
                    assert isinstance(returns, pd.DataFrame)
                    
                    # Portfolio Returns (Equal Weighted for simplification)
                    port_df = returns[tickers]
                    assert isinstance(port_df, pd.DataFrame)
                    port_returns = port_df.mean(axis=1)
                    
                    # Sharpe Ratio (Annualized, 5% Risk-Free Rate assumption)
                    rf_daily = (1.05 ** (1/252)) - 1
                    excess_returns = port_returns - rf_daily
                    if port_returns.std() > 0:
                        sharpe_ratio = (excess_returns.mean() / port_returns.std()) * (252 ** 0.5)
                    
                    # Beta vs QQQ
                    if "QQQ" in returns.columns:
                        market_returns = returns["QQQ"]
                        covariance = port_returns.cov(market_returns)
                        market_variance = market_returns.var()
                        if market_variance > 0:
                            beta = covariance / market_variance
                        
                        # Relative MDD
                        qqq_cum = (1 + market_returns).cumprod()
                        qqq_max = qqq_cum.cummax()
                        qqq_mdd = ((qqq_cum / qqq_max) - 1).min() * 100
                        relative_mdd_pct = portfolio_mdd_pct - qqq_mdd
        except Exception as e:
            print(f"Metrics calculation failed: {e}")

        # Signal Accuracy from History
        accuracy = 0.0
        history = self.db.fetchall_dict("SELECT * FROM history")
        if history:
            profitable = sum(1 for h in history if h['pnl'] > 0)
            accuracy = (profitable / len(history)) * 100

        # Recovery Factor
        recovery_factor = 0.0
        if abs(portfolio_mdd_pct) > 0:
            recovery_factor = total_roi_pct / abs(portfolio_mdd_pct)

        total_investment_usd = sum([p['current_price'] * p['quantity'] for p in positions])
        total_investment = total_investment_usd * exchange_rate

        # Title Formatting
        date_str = datetime.now().strftime('%m/%d')
        tickers_str = ", ".join([p['ticker'] for p in positions[:3]])
        title = f"[{category}] LV-MB 리포트 ({tickers_str}) - {date_str}"

        # 5. Notion Blocks Reconstruction
        from typing import Any
        blocks: list[dict[str, Any]] = [
            {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"text": {"content": f"{category} Portfolio Intelligence"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": f"Reporting Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"}}]}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "1. Key Performance Summary"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": f"Status: {'Risk-On (Normal)' if is_safe else 'Risk-Off (100% Cash)'}"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": f"Portfolio MDD: {portfolio_mdd_pct:.2f}%"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": f"Relative Drawdown: {relative_mdd_pct:.2f}%"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": f"Recovery Factor: {recovery_factor:.2f}"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": f"Signal Accuracy (T+5): {accuracy:.1f}%"}}]}},
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": f"{category} Portfolio Status"}}]}},
        ]
        
        # 6. Positions Data & Table Block
        table_rows = [
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "Ticker"}}],
                        [{"type": "text", "text": {"content": "ROI (%)"}}],
                        [{"type": "text", "text": {"content": "MDD (%)"}}]
                    ]
                }
            }
        ]
        
        avg_entry_price = 0.0
        if positions:
            avg_entry_price = sum([p['entry_price'] for p in positions]) / len(positions)

        for p in positions:
            p_roi = (p['current_price'] / p['entry_price'] - 1) * 100
            table_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": str(p['ticker'])}}],
                        [{"type": "text", "text": {"content": f"{p_roi:+.2f}%"}}],
                        [{"type": "text", "text": {"content": f"{p['current_mdd']:.2f}%"}}]
                    ]
                }
            })

        blocks.append({
            "type": "table",
            "table": {
                "table_width": 3,
                "has_column_header": True,
                "has_row_header": False,
                "children": table_rows
            }
        })
        # 7. Captured Signals Section
        if all_signals:
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Newly Captured Signals"}}]}})
            
            sig_table_rows = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "Ticker"}}],
                            [{"type": "text", "text": {"content": "Score"}}],
                            [{"type": "text", "text": {"content": "R12 (1Y ROI)"}}]
                        ]
                    }
                }
            ]
            
            for sig in all_signals:
                sig_table_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": sig['ticker']}}],
                            [{"type": "text", "text": {"content": f"{sig['score']:.4f}"}}],
                            [{"type": "text", "text": {"content": f"{sig['r12']*100:+.2f}%"}}]
                        ]
                    }
                })
                
            blocks.append({
                "type": "table",
                "table": {
                    "table_width": 3,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": sig_table_rows
                }
            })
            
        # 3. Data Health Telemetry Section
        health_logs = []
        try:
            # Fetch latest distinct tickers from telemetry logs in the database
            health_logs = self.db.fetchall_dict('''
                SELECT * FROM data_health_logs 
                ORDER BY timestamp DESC, id DESC 
                LIMIT 15
            ''')
            if health_logs:
                # Sort alphabetically by ticker for readability
                health_logs = sorted(health_logs, key=lambda x: x['ticker'])
        except Exception as e:
            print(f"Failed to fetch telemetry logs for Notion report: {e}")

        if health_logs:
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "3. Data Health & Volatility Telemetry"}}]}})
            
            health_table_rows = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "Ticker"}}],
                            [{"type": "text", "text": {"content": "Source"}}],
                            [{"type": "text", "text": {"content": "Days (Val/Tot)"}}],
                            [{"type": "text", "text": {"content": "Clips"}}],
                            [{"type": "text", "text": {"content": "Raw Vol"}}],
                            [{"type": "text", "text": {"content": "Clipped Vol"}}],
                            [{"type": "text", "text": {"content": "Scale"}}]
                        ]
                    }
                }
            ]
            
            for hl in health_logs:
                raw_vol_pct = f"{hl['raw_ann_vol']*100:.1f}%" if hl['raw_ann_vol'] is not None else "N/A"
                clip_vol_pct = f"{hl['clipped_ann_vol']*100:.1f}%" if hl['clipped_ann_vol'] is not None else "N/A"
                scale_str = f"{hl['vol_scale']:.2f}x" if hl['vol_scale'] is not None else "1.00x"
                
                health_table_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": str(hl['ticker'])}}],
                            [{"type": "text", "text": {"content": str(hl['data_source'])}}],
                            [{"type": "text", "text": {"content": f"{hl['valid_days']}/{hl['total_days']}"}}],
                            [{"type": "text", "text": {"content": str(hl['clip_count'])}}],
                            [{"type": "text", "text": {"content": raw_vol_pct}}],
                            [{"type": "text", "text": {"content": clip_vol_pct}}],
                            [{"type": "text", "text": {"content": scale_str}}]
                        ]
                    }
                })
                
            blocks.append({
                "type": "table",
                "table": {
                    "table_width": 7,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": health_table_rows
                }
            })
            
        # 4. Data Quality Audit Section
        audit_logs = []
        try:
            audit_logs = self.db.fetchall_dict('''
                SELECT a.* FROM data_quality_audit a
                INNER JOIN (
                    SELECT ticker, MAX(timestamp) as max_ts
                    FROM data_quality_audit
                    GROUP BY ticker
                ) b ON a.ticker = b.ticker AND a.timestamp = b.max_ts
                ORDER BY a.ticker ASC
            ''')
        except Exception as e:
            print(f"Failed to fetch data quality audit logs for Notion report: {e}")

        if audit_logs:
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "4. Data Quality Audit Statistics"}}]}})
            
            audit_table_rows = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "Ticker"}}],
                            [{"type": "text", "text": {"content": "Status"}}],
                            [{"type": "text", "text": {"content": "Error Rate"}}],
                            [{"type": "text", "text": {"content": "Anomalies/Total"}}],
                            [{"type": "text", "text": {"content": "Details"}}]
                        ]
                    }
                }
            ]
            
            for al in audit_logs:
                err_rate_pct = f"{al['error_rate']*100:.1%}" if al['error_rate'] is not None else "0.0%"
                audit_table_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": str(al['ticker'])}}],
                            [{"type": "text", "text": {"content": str(al['status'])}}],
                            [{"type": "text", "text": {"content": err_rate_pct}}],
                            [{"type": "text", "text": {"content": f"{al['anomaly_days']}/{al['total_days']}"}}],
                            [{"type": "text", "text": {"content": str(al['details'])[:50]}}]
                        ]
                    }
                })
                
            blocks.append({
                "type": "table",
                "table": {
                    "table_width": 5,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": audit_table_rows
                }
            })
            
        blocks.append({"object": "block", "type": "divider", "divider": {}})
            
        # Standard Chart Configuration
        plt.style.use('bmh')
        CHART_SIZE = (10, 5)
        CHART_DPI = 150

        # Visual 1: Performance Comparison
        try:
            all_tickers = [p['ticker'] for p in positions]
            if all_tickers:
                start_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
                v1_data = DataProvider().get_history(all_tickers, start=start_date)
                
                if v1_data is not None and not v1_data.empty:
                    # Robustly find Close/Adj Close
                    if isinstance(v1_data.columns, pd.MultiIndex):
                        if 'Adj Close' in v1_data.columns.get_level_values(0):
                            close = v1_data['Adj Close'].copy()
                        else:
                            close = v1_data['Close'].copy()
                    else:
                        col = 'Adj Close' if 'Adj Close' in v1_data.columns else 'Close'
                        close = v1_data[col].copy() if col in v1_data.columns else None
                    
                    if close is not None and not close.empty:
                        # Normalize to Cumulative Return (%) starting from 0%
                        norm_v1 = (close / close.iloc[0] - 1) * 100
                        
                        fig1, ax1 = plt.subplots(figsize=CHART_SIZE)
                        for t in all_tickers:
                            if t in norm_v1.columns:
                                ax1.plot(norm_v1.index, norm_v1[t], label=t, alpha=0.8, linewidth=1.5)
                        
                        ax1.set_title(f"Performance: Portfolio Assets ({datetime.now().strftime('%Y-%m-%d')})")
                        ax1.legend(loc='upper left', fontsize='small')
                        ax1.set_ylabel("Cumulative Return (%)")
                        plt.grid(True, linestyle='--', alpha=0.6)
                        plt.tight_layout()
                        plt.savefig("reports/performance_comparison.png", dpi=CHART_DPI)
                        plt.close()
                        
                        perf_url = upload_image_to_github("reports/performance_comparison.png")
                        if perf_url:
                            blocks.append({"object": "block", "type": "image", "image": {"type": "external", "external": {"url": perf_url}}})
        except Exception as e:
            print(f"Comparison chart failed: {e}")

        # Visual 2: Risk / MDD Analysis
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "2. Risk / Signal Analysis"}}]}})
        try:
            if positions:
                v2_tickers = [p['ticker'] for p in positions]
                # Use negative drawdown values directly
                v2_mdds = [p['current_mdd'] if p['current_mdd'] is not None else 0.0 for p in positions]
                
                fig2, ax2 = plt.subplots(figsize=CHART_SIZE)
                ax2.bar(v2_tickers, v2_mdds, color='steelblue', alpha=0.8)
                # Lower safety threshold dot line at -15%
                ax2.axhline(-15, color='darkred', linestyle='--', alpha=1.0, label="Safety Threshold (-15%)")
                ax2.set_ylabel("Drawdown (%)")
                ax2.set_title(f"Portfolio Risk: {category} Ticker Drawdowns")
                ax2.legend()
                plt.grid(axis='y', linestyle='--', alpha=0.5)
                plt.tight_layout()
                plt.savefig("reports/risk_analysis.png", dpi=CHART_DPI)
                plt.close()
                
                risk_url = upload_image_to_github("reports/risk_analysis.png")
                if risk_url:
                    blocks.append({"object": "block", "type": "image", "image": {"type": "external", "external": {"url": risk_url}}})
        except Exception as e:
            print(f"Risk chart failed: {e}")

        # Status and Grade
        strategy_grade = "A"
        if total_roi_pct > 20: strategy_grade = "S"
        elif total_roi_pct < 0: strategy_grade = "B"

        title_key = self._get_title_property_name()
        
        properties = {
            title_key: {"title": [{"text": {"content": title}}]},
            "Strategy": {"rich_text": [{"text": {"content": "Time-Series Momentum & CTA"}}]},
            "ROI (%)": {"number": round(float(total_roi_raw), 4)}, # Notion Percent format expects fractions (0.0083 for 0.83%)
            "MDD (%)": {"number": round(float(portfolio_mdd_raw), 4)},
            "Date": {"date": {"start": datetime.now().isoformat()}},
            "Status": {"select": {"name": "Running" if is_safe else "Closed"}},
            "Tags": {"multi_select": [{"name": "Momentum"}, {"name": "Live"}, {"name": category}]},
            "Net Profit": {"number": round(net_profit, 0)},
            "Total Investment": {"number": round(total_investment, 0)},
            "Strategy Grade": {"select": {"name": strategy_grade}},
            "Regime Slots": {"number": int(regime_slots)}
        }

        # Send to Notion
        self._create_page(properties, blocks)

    def _create_page(self, properties, blocks):
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": blocks
        }
        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code == 200:
            print("Notion Report Sent Successfully.")
        else:
            print(f"Notion Error: {response.text}")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    reporter = AntiGravityReporter()
    reporter.generate_summary_report()
