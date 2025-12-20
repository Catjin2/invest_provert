import os
import requests
from dotenv import load_dotenv

load_dotenv()

class DataFetcher:
    def __init__(self):
        self.api_key = os.getenv("SEC_API_KEY")
        self.url = "https://api.sec-api.io"

    def get_insider_signals(self):
        try:
            # 안정적인 분석을 위해 11월 데이터 타겟팅
            date_query = "filedAt:[2025-11-01 TO 2025-11-30]"
            full_query = f"formType:\"4\" AND {date_query}"
            
            payload = {
                "query": { "query_string": { "query": full_query } },
                "from": "0", 
                "size": "30", # 더 많은 데이터를 분석
                "sort": [{ "filedAt": { "order": "desc" } }]
            }
            
            response = requests.post(f"{self.url}?token={self.api_key}", json=payload)
            if response.status_code == 200:
                return response.json().get('filings', [])
            return []
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            return []