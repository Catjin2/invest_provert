from data_fetcher import DataFetcher
from backtester import Backtester
from notion_logger import NotionLogger

def main():
    fetcher = DataFetcher()
    backtester = Backtester()
    notion = NotionLogger()

    print("🚀 안티그레비티 포트폴리오 시스템 가동...")
    signals = fetcher.get_insider_signals()
    
    if not signals:
        print("❌ 공시 데이터를 가져오지 못했습니다.")
        return

    processed_tickers = set() # 한 실행에서 중복 종목 방지
    for sig in signals:
        ticker = sig.get('ticker')
        date_raw = sig.get('filedAt')
        
        if ticker in processed_tickers: continue
            
        if ticker and date_raw:
            clean_date = date_raw.split('T')[0]
            res = backtester.calculate_return(ticker, clean_date)
            
            if res:
                if notion.add_row(res):
                    print(f"✅ {ticker} 분석 완료 및 노션 전송 성공! ({res['Return_Pct']}%)")
                processed_tickers.add(ticker)

    print("🎉 모든 분석 결과가 노션에 저장되었습니다.")

if __name__ == "__main__":
    main()