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
            # 보수적 접근: $50,000 이상 매수만 수집
            date_query = "filedAt:[2025-11-01 TO 2025-11-30]"
            value_query = "transactions.value:[50000 TO 100000000]"
            full_query = f"formType:\"4\" AND {date_query} AND {value_query}"
            
            payload = {
                "query": { "query_string": { "query": full_query } },
                "from": "0", 
                "size": "30",
                "sort": [{ "filedAt": { "order": "desc" } }]
            }
            
            response = requests.post(f"{self.url}?token={self.api_key}", json=payload)
            if response.status_code == 200:
                return response.json().get('filings', [])
            return []
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            return []import os
import requests
from datetime import datetime, timedelta # 날짜 계산용 추가
from dotenv import load_dotenv

load_dotenv()

class DataFetcher:
    def __init__(self):
        self.api_key = os.getenv("SEC_API_KEY")
        self.url = "https://api.sec-api.io"

    def get_insider_signals(self):
        try:
            # 1. 날짜 범위 자동 계산 (오늘부터 7일 전까지)
            today = datetime.now()
            start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

            # 2. 쿼리 구성: 최근 날짜 범위 + 5만 달러 이상 매수
            date_query = f"filedAt:[{start_date} TO {end_date}]"
            value_query = "transactions.value:[50000 TO 100000000]"
            full_query = f"formType:\"4\" AND {date_query} AND {value_query}"
            
            payload = {
                "query": { "query_string": { "query": full_query } },
                "from": "0", 
                "size": "30",
                "sort": [{ "filedAt": { "order": "desc" } }]
            }
            
            response = requests.post(f"{self.url}?token={self.api_key}", json=payload)
            if response.status_code == 200:
                filings = response.json().get('filings', [])
                print(f"📡 {start_date} ~ {end_date} 사이 {len(filings)}개의 신호를 찾았습니다.")
                return filings
            return []
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            return []