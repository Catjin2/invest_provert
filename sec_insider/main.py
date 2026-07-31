from sec_insider.data_fetcher import DataFetcher
from sec_insider.backtester import Backtester
from sec_insider.notion_logger import NotionLogger

import sys

def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore
    fetcher = DataFetcher()
    backtester = Backtester()
    notion = NotionLogger()

    print("🚀 보수적 안티그레비티 전략 가동 (필터: $50K 이상)...")
    signals = fetcher.get_insider_signals()
    
    processed_tickers = set()
    for sig in signals:
        ticker = sig.get('ticker')
        date_raw = sig.get('filedAt')
        
        # 직급 확인: CEO, CFO, President 등 핵심 인물인지 판별
        job_title = sig.get('officerTitle', 'Director/Owner').upper()
        is_clevel = any(role in job_title for role in ['CEO', 'CFO', 'PRESIDENT', 'CHIEF'])
        
        if ticker in processed_tickers: continue
            
        if ticker and date_raw:
            clean_date = date_raw.split('T')[0]
            res = backtester.calculate_return(ticker, clean_date)
            
            if res:
                # 노션에 보낼 데이터에 직급 정보 추가
                res['Job_Title'] = job_title
                res['Importance'] = "🔥 핵심경영진" if is_clevel else "✅ 일반내부자"
                
                if notion.add_row(res):
                    print(f"✅ {res['Importance']} | {ticker} 전송 완료!")
                processed_tickers.add(ticker)

    print("🎉 보수적 분석 완료.")

if __name__ == "__main__":
    main()