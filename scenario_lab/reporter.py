"""
Scenario Lab Reporter (시스템 C: 노션 리포터 및 시각화 도구)
[시스템 C | 위기 검증 랩] 접두사 표준화 리포트 생성,
Filter ON vs Filter OFF 자산 곡선(Equity Curve) 비교 차트 렌더링,
GitHub 자동 업로드 및 노션 데이터베이스 발행 지원.
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from github_uploader import upload_image_to_github
from dotenv import load_dotenv

load_dotenv()

class ScenarioLabReporter:
    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None):
        self.token = token or os.getenv("NOTION_REPORT_TOKEN") or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_REPORT_DATABASE_ID") or os.getenv("NOTION_DATABASE_ID")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def _fetch_db_schema(self) -> Dict[str, Any]:
        """Fetch database schema properties to ensure safe payload mapping."""
        if not self.token or not self.database_id:
            return {}
        try:
            url = f"https://api.notion.com/v1/databases/{self.database_id}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("properties", {})
        except Exception as e:
            print(f"[ScenarioLabReporter] Schema query failed: {e}")
        return {}

    def generate_comparison_chart(
        self,
        scenario_key: str,
        scenario_name: str,
        df_on: pd.DataFrame,
        df_off: pd.DataFrame,
        save_dir: str = "reports"
    ) -> Optional[str]:
        """
        Generate high-resolution comparison chart (Equity Curve & Drawdown)
        and attempt GitHub raw URL upload.
        """
        try:
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, f"scenario_lab_{scenario_key}.png")

            plt.style.use('bmh')
            if sys.platform.startswith('win'):
                plt.rcParams['font.family'] = 'Malgun Gothic'
            plt.rcParams['axes.unicode_minus'] = False
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

            # Subplot 1: Equity Curve
            if not df_on.empty and 'equity' in df_on.columns:
                ax1.plot(df_on.index, df_on['equity'], label='Filter ON (Bubble Filter + Circuit Breaker)', color='#008080', linewidth=2.2)
            if not df_off.empty and 'equity' in df_off.columns:
                ax1.plot(df_off.index, df_off['equity'], label='Filter OFF (No Protection)', color='#D9534F', linewidth=1.8, linestyle='--')

            ax1.set_title(f"[시스템 C] {scenario_name} - 자산 곡선(Equity Curve) 비교", fontsize=13, fontweight='bold', pad=10)
            ax1.set_ylabel("Portfolio Value ($)", fontsize=11)
            ax1.legend(loc='best', framealpha=0.9)
            ax1.grid(True, linestyle=':', alpha=0.6)

            # Subplot 2: Drawdown Curve
            if not df_on.empty and 'drawdown' in df_on.columns:
                ax2.plot(df_on.index, df_on['drawdown'], label='Filter ON MDD', color='#008080', linewidth=1.8)
            if not df_off.empty and 'drawdown' in df_off.columns:
                ax2.plot(df_off.index, df_off['drawdown'], label='Filter OFF MDD', color='#D9534F', linewidth=1.5, linestyle='--')

            ax2.axhline(-15.0, color='#8B0000', linestyle=':', linewidth=1.5, label='Circuit Breaker (-15%)')
            ax2.set_ylabel("Drawdown (%)", fontsize=11)
            ax2.set_xlabel("Date", fontsize=11)
            ax2.legend(loc='lower left', framealpha=0.9)
            ax2.grid(True, linestyle=':', alpha=0.6)

            # Auto-format dates
            fig.autofmt_xdate()
            plt.tight_layout()
            plt.savefig(filepath, dpi=150)
            plt.close()

            print(f"[ScenarioLabReporter] Comparison chart saved to {filepath}")
            
            # GitHub raw upload
            uploaded_url = upload_image_to_github(filepath)
            if uploaded_url:
                print(f"[ScenarioLabReporter] Chart uploaded to GitHub: {uploaded_url}")
            return uploaded_url
        except Exception as e:
            print(f"[ScenarioLabReporter] Chart generation failed: {e}")
            return None

    def send_report(
        self,
        scenario_key: str,
        scenario_name: str,
        start_date: str,
        end_date: str,
        metrics_on: Dict[str, float],
        metrics_off: Dict[str, float],
        events_on: List[Dict[str, Any]],
        chart_url: Optional[str] = None
    ) -> bool:
        """
        Build standardized Notion page with prefix [시스템 C | 위기 검증 랩]
        and publish to the connected Notion database.
        """
        if not self.token or not self.database_id:
            print("[ScenarioLabReporter] NOTION_TOKEN or NOTION_DATABASE_ID missing. Skipping upload.")
            return False

        schema = self._fetch_db_schema()
        
        # 1. Title Property Resolution
        title_prop_name = "Name"
        for name, meta in schema.items():
            if meta.get("type") == "title":
                title_prop_name = name
                break

        # MDD improvement calculation
        # e.g., ON: -10.5%, OFF: -25.2% -> defense_mdd = (-10.5) - (-25.2) = +14.7%p
        defense_mdd = metrics_on.get('mdd_pct', 0.0) - metrics_off.get('mdd_pct', 0.0)
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst)
        date_str = now_kst.strftime('%m/%d')
        
        title_text = f"[System C] {scenario_name} 위기 국면 인메모리 스트레스 테스트 및 집행 시뮬레이션 보고서 - {date_str}"

        # 2. Dynamic Safe Properties Mapping
        properties: Dict[str, Any] = {
            title_prop_name: {"title": [{"text": {"content": title_text}}]}
        }

        if "시스템" in schema:
            properties["시스템"] = {"select": {"name": "System C"}}

        if "Strategy" in schema:
            properties["Strategy"] = {"rich_text": [{"text": {"content": "[System C] 위기 국면 인메모리 스트레스 테스트 및 집행 시뮬레이션"}}]}
        
        if "ROI (%)" in schema:
            properties["ROI (%)"] = {"number": round(metrics_on.get('return_pct', 0.0) / 100.0, 4)}
            
        if "MDD (%)" in schema:
            properties["MDD (%)"] = {"number": round(metrics_on.get('mdd_pct', 0.0) / 100.0, 4)}

        if "Date" in schema:
            properties["Date"] = {"date": {"start": now_kst.isoformat()}}

        if "Status" in schema:
            prop_type = schema["Status"].get("type")
            if prop_type == "select":
                available_options = [opt["name"] for opt in schema["Status"].get("select", {}).get("options", [])]
                status_name = "Closed" if "Closed" in available_options else (available_options[0] if available_options else "Running")
                properties["Status"] = {"select": {"name": status_name}}
            elif prop_type == "status":
                properties["Status"] = {"status": {"name": "Done"}}

        if "Tags" in schema and schema["Tags"].get("type") == "multi_select":
            properties["Tags"] = {"multi_select": [{"name": "System C"}, {"name": "ScenarioLab"}]}

        if "Strategy Grade" in schema and schema["Strategy Grade"].get("type") == "select":
            grade = "S" if defense_mdd >= 10.0 else ("A" if defense_mdd >= 3.0 else "B")
            properties["Strategy Grade"] = {"select": {"name": grade}}

        # 3. Notion Blocks Construction
        blocks: List[Dict[str, Any]] = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": (
                                "[System C | 위기 국면 스트레스 테스트 및 집행 시뮬레이션 파이프라인]\n"
                                f"검증일시 (서울 KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                "본 검증은 실전 운영 DB(invest_standalone.db)와 완전 격리된 순수 인메모리(Zero I/O) 가상 환경에서 수행되었습니다. "
                                f"검증 구간: {start_date} ~ {end_date} | "
                                "15슬롯 동적 배분, 슬리피지(0.2%), 거래 수수료(0.1%), 트레일링 스탑(-10%), 서킷브레이커(-15% MDD) 완벽 적용."
                            )
                        }
                    }]
                }
            },
            {"object": "block", "type": "divider", "divider": {}},
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"text": {"content": f"[System C] {scenario_name} 위기 스트레스 테스트 검증 보고서"}}]}
            },
            {"object": "block", "type": "divider", "divider": {}},
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "1. A/B 벤치마크 성과 비교 (Filter ON vs OFF)"}}]}
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "리스크 관리 모델 (Z-Score 필터 + 서킷브레이커 적용): "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"수익률 {metrics_on.get('return_pct', 0.0):+.2f}%, MDD {metrics_on.get('mdd_pct', 0.0):.2f}%, 최종 자산 ${metrics_on.get('final', 0.0):,.2f}"}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "벤치마크 기준 모델 (필터 미적용): "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"수익률 {metrics_off.get('return_pct', 0.0):+.2f}%, MDD {metrics_off.get('mdd_pct', 0.0):.2f}%, 최종 자산 ${metrics_off.get('final', 0.0):,.2f}"}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "최대 낙폭(MDD) 방어 개선도: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{defense_mdd:+.2f}%p 개선 (손실 위험 억제 효과 검증)"}, "annotations": {"color": "green" if defense_mdd > 0 else "red"}}
                    ]
                }
            },
            # Performance Table
            {
                "type": "table",
                "table": {
                    "table_width": 4,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": [
                        {
                            "type": "table_row",
                            "table_row": {
                                "cells": [
                                    [{"type": "text", "text": {"content": "구분"}}],
                                    [{"type": "text", "text": {"content": "최종 자산 ($)"}}],
                                    [{"type": "text", "text": {"content": "수익률 (%)"}}],
                                    [{"type": "text", "text": {"content": "최대 낙폭 MDD (%)"}}]
                                ]
                            }
                        },
                        {
                            "type": "table_row",
                            "table_row": {
                                "cells": [
                                    [{"type": "text", "text": {"content": "Filter ON (시스템 C)"}}],
                                    [{"type": "text", "text": {"content": f"${metrics_on.get('final', 0.0):,.2f}"}}],
                                    [{"type": "text", "text": {"content": f"{metrics_on.get('return_pct', 0.0):+.2f}%"}}],
                                    [{"type": "text", "text": {"content": f"{metrics_on.get('mdd_pct', 0.0):.2f}%"}}]
                                ]
                            }
                        },
                        {
                            "type": "table_row",
                            "table_row": {
                                "cells": [
                                    [{"type": "text", "text": {"content": "Filter OFF (벤치마크)"}}],
                                    [{"type": "text", "text": {"content": f"${metrics_off.get('final', 0.0):,.2f}"}}],
                                    [{"type": "text", "text": {"content": f"{metrics_off.get('return_pct', 0.0):+.2f}%"}}],
                                    [{"type": "text", "text": {"content": f"{metrics_off.get('mdd_pct', 0.0):.2f}%"}}]
                                ]
                            }
                        }
                    ]
                }
            },
            {"object": "block", "type": "divider", "divider": {}},
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "2. 자산 곡선(Equity Curve) 비교 차트"}}]}
            }
        ]

        if chart_url:
            blocks.append({
                "object": "block",
                "type": "image",
                "image": {"type": "external", "external": {"url": chart_url}}
            })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "로컬 reports/ 디렉토리에 차트 이미지가 보존되어 있습니다. (GitHub 미연동 시 로컬 확인 가능)"}}]}
            })

        # Events Log Section
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "3. 주요 위기 청산 및 리스크 관리 집행 기록 (리스크 관리 모델)"}}]}
        })

        if events_on:
            event_rows = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "일자"}}],
                            [{"type": "text", "text": {"content": "유형"}}],
                            [{"type": "text", "text": {"content": "내용"}}]
                        ]
                    }
                }
            ]
            for ev in events_on[:15]:
                event_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": str(ev.get('date', ''))}}],
                            [{"type": "text", "text": {"content": str(ev.get('type', ''))}}],
                            [{"type": "text", "text": {"content": str(ev.get('description', ''))[:50]}}]
                        ]
                    }
                })

            blocks.append({
                "type": "table",
                "table": {
                    "table_width": 3,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": event_rows
                }
            })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "시뮬레이션 기간 동안 서킷브레이커 발동 없이 안정적인 포지션을 유지했습니다."}}]}
            })

        # 4. Dispatch to Notion API
        try:
            url = "https://api.notion.com/v1/pages"
            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties,
                "children": blocks
            }
            res = requests.post(url, headers=self.headers, json=payload, timeout=15)
            if res.status_code == 200:
                print(f"[ScenarioLabReporter] Successfully published report: {title_text}")
                return True
            else:
                print(f"[ScenarioLabReporter] Notion API Error ({res.status_code}): {res.text}")
                return False
        except Exception as e:
            print(f"[ScenarioLabReporter] Failed to send Notion report: {e}")
            return False
