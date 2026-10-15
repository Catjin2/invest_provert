import os
import requests
from dotenv import load_dotenv

load_dotenv()

class NotionLogger:
    def __init__(self):
        # 환경 변수에서 토큰과 ID를 가져옵니다
        self.token = os.getenv("NOTION_TOKEN", "").strip()
        self.database_id = os.getenv("NOTION_DATABASE_ID", "").strip()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def add_row(self, data):
        url = "https://api.notion.com/v1/pages"
        
        # 성과에 따른 상태 구분
        status_name = "수익" if data['Return_Pct'] > 0 else "손실"
        pnl = float(data.get('Exit_Price', 0)) - float(data.get('Entry_Price', 0))
        exit_date = data.get('Exit_Date', data['Date'])
        importance_str = f"[{data.get('Importance', '주요 임원')}] {data.get('Job_Title', '')}"
        
        payload = {
            "parent": { "database_id": self.database_id },
            "properties": {
                "종목명": { "title": [{ "text": { "content": f"[시스템 A] {data['Ticker']} 내부자 거래 ({data.get('Job_Title', '')})" } }] },
                "진입일": { "date": { "start": str(data['Date']) } },
                "진입가": { "number": float(data['Entry_Price']) },
                "청산가": { "number": float(data['Exit_Price']) },
                "수익률(%)": { "number": float(data['Return_Pct']) },
                "상태": { "select": { "name": status_name } },
                "시세차익": { "number": round(pnl, 2) },
                "청산일": { "date": { "start": str(exit_date) } },
                "투자금 변동": { "rich_text": [{ "text": { "content": f"진입: ${data['Entry_Price']:,.2f} -> 청산: ${data['Exit_Price']:,.2f} | {importance_str}" } }] }
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                return True
            else:
                print(f"[오류] 노션 API 응답 실패 ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            print(f"[오류] 노션 전송 예외 발생: {e}")
            return False