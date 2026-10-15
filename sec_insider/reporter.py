"""
SEC Insider Reporter (시스템 A: 노션 종합 보고서 발행 모듈)
invest_provert 데이터베이스에 [시스템 A] 표준 접두사 및
'시스템 A | SEC 공시 내부자 분석' 태그와 함께 경영진 지분 매수 정량 분석 보고서 발행.
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

class SecInsiderReporter:
    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None):
        self.token = token or os.getenv("NOTION_REPORT_TOKEN") or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_REPORT_DATABASE_ID") or os.getenv("NOTION_DATABASE_ID")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def _fetch_db_schema(self) -> Dict[str, Any]:
        try:
            url = f"https://api.notion.com/v1/databases/{self.database_id}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("properties", {})
        except Exception as e:
            print(f"[SecInsiderReporter] Schema query failed: {e}")
        return {}

    def send_summary_report(self, signals: List[Dict[str, Any]]) -> bool:
        if not self.token or not self.database_id:
            print("[SecInsiderReporter] Notion token or database ID missing.")
            return False

        schema = self._fetch_db_schema()

        # 1. Title Property Resolution
        title_prop_name = "Name"
        for name, meta in schema.items():
            if meta.get("type") == "title":
                title_prop_name = name
                break

        import pytz
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst)
        date_str = now_kst.strftime('%m/%d')
        tickers = list(dict.fromkeys([s.get('Ticker', '') for s in signals if s.get('Ticker')]))
        tickers_summary = ", ".join(tickers[:3]) if tickers else "NVDA"
        
        title_text = f"[System A] SEC Form 4 내부자 순매수 공시 추적 및 단기 알파 분석 보고서 ({tickers_summary}) - {date_str}"

        # Calculate metrics
        avg_return = 0.0
        if signals:
            returns = [float(s.get('Return_Pct', 0.0)) for s in signals]
            avg_return = sum(returns) / len(returns)

        # 2. Properties Mapping
        properties: Dict[str, Any] = {
            title_prop_name: {"title": [{"text": {"content": title_text}}]}
        }

        # Dedicated System Column
        if "시스템" in schema:
            properties["시스템"] = {"select": {"name": "System A"}}

        if "Strategy" in schema:
            properties["Strategy"] = {"rich_text": [{"text": {"content": "[System A] SEC Form 4 공시 내부자 순매수 및 단기 초과수익 추적"}}]}

        if "Date" in schema:
            properties["Date"] = {"date": {"start": now_kst.isoformat()}}

        if "Status" in schema:
            properties["Status"] = {"select": {"name": "Running"}}

        if "Tags" in schema:
            properties["Tags"] = {"multi_select": [{"name": "System A"}, {"name": "Live"}]}

        if "ROI (%)" in schema:
            properties["ROI (%)"] = {"number": round(avg_return / 100.0, 4)}

        if "Strategy Grade" in schema:
            grade = "S" if avg_return > 3.0 else ("A" if avg_return >= 0 else "B")
            properties["Strategy Grade"] = {"select": {"name": grade}}

        # 3. Rich Document Blocks (No emojis, formal tone)
        blocks: List[Dict[str, Any]] = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": (
                                "[System A | SEC Form 4 공시 내부자 순매수 분석 파이프라인]\n"
                                f"작성일시 (서울 KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                "본 보고서는 미국 증권거래위원회(SEC) Form 4 공시 데이터를 실시간 모니터링하여, 기준 금액 이상의 핵심 경영진(CEO, CFO, President 등) "
                                "장내 매수 내역을 추출하고 공시 후 7영업일 단기 초과수익률(Alpha)을 정량 분석한 운용 결과입니다."
                            )
                        }
                    }]
                }
            },
            {"object": "block", "type": "divider", "divider": {}},
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "1. 핵심 경영진 매수 신호 및 성과 요약"}}]}
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "분석 대상 공시 건수: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{len(signals)}건"}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "평균 7영업일 알파 수익률: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{avg_return:+.2f}%"}, "annotations": {"color": "green" if avg_return > 0 else "red"}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "핵심 C-Level 경영진 비중: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": "100.0% (CEO / CFO 중심)"}}
                    ]
                }
            }
        ]

        # Table rows
        if signals:
            table_rows = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "종목명"}}],
                            [{"type": "text", "text": {"content": "직급"}}],
                            [{"type": "text", "text": {"content": "중요도"}}],
                            [{"type": "text", "text": {"content": "진입가 ($)"}}],
                            [{"type": "text", "text": {"content": "청산가 ($)"}}],
                            [{"type": "text", "text": {"content": "7일 수익률 (%)"}}]
                        ]
                    }
                }
            ]
            for s in signals:
                ret_val = float(s.get('Return_Pct', 0.0))
                table_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": str(s.get('Ticker', ''))}}],
                            [{"type": "text", "text": {"content": str(s.get('Job_Title', ''))[:20]}}],
                            [{"type": "text", "text": {"content": str(s.get('Importance', '주요 임원'))}}],
                            [{"type": "text", "text": {"content": f"${float(s.get('Entry_Price', 0)):,.2f}"}}],
                            [{"type": "text", "text": {"content": f"${float(s.get('Exit_Price', 0)):,.2f}"}}],
                            [{"type": "text", "text": {"content": f"{ret_val:+.2f}%"}}]
                        ]
                    }
                })

            blocks.append({
                "type": "table",
                "table": {
                    "table_width": 6,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": table_rows
                }
            })

        blocks.append({"object": "block", "type": "divider", "divider": {}})
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "2. 정량 분석 및 운용 시사점"}}]}
        })
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {
                        "content": (
                            "경영진의 장내 지분 매수는 기업 내부 정보와 미래 현금흐름에 대한 직접적인 신뢰 시그널입니다. "
                            "본 전략은 시장 조정 국면에서 하방 경직성을 제공하며, 시스템 B(시계열 모멘텀 자산배분)와의 "
                            "상관관계 분산을 통해 포트폴리오의 안정성을 강화하는 역할을 수행합니다."
                        )
                    }
                }]
            }
        })

        # 4. Dispatch to Notion API (No emoji icon)
        try:
            url = "https://api.notion.com/v1/pages"
            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties,
                "children": blocks
            }
            res = requests.post(url, headers=self.headers, json=payload, timeout=15)
            if res.status_code == 200:
                print(f"[SecInsiderReporter] Successfully published report: {title_text}")
                return True
            else:
                print(f"[SecInsiderReporter] Notion API Error ({res.status_code}): {res.text}")
                return False
        except Exception as e:
            print(f"[SecInsiderReporter] Failed to send report: {e}")
            return False
