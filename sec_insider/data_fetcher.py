import os
import requests
from datetime import datetime, timedelta
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
            else:
                print(f"❌ SEC API 요청 실패 (상태 코드: {response.status_code}): {response.text}")
            return []
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            return []