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
        
        # 수익률에 따른 색상 이모지 결정
        status_emoji = "🔴" if data['Return_Pct'] > 0 else "🔵"
        
        payload = {
            "parent": { "database_id": self.database_id },
            "properties": {
                "종목명": { "title": [{ "text": { "content": f"{status_emoji} {data['Ticker']}" } }] },
                "분석일": { "date": { "start": str(data['Date']) } },
                "수익률(%)": { "number": float(data['Return_Pct']) },
                "진입가": { "number": float(data['Entry_Price']) },
                "청산가": { "number": float(data['Exit_Price']) },
                # 새롭게 추가된 보수적 투자 지표
                "중요도": { "select": { "name": data['Importance'] } }, 
                "직급": { "rich_text": [{ "text": { "content": data['Job_Title'] } }] }
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ 노션 전송 오류: {e}")
            return False