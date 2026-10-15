from core.data_provider import CoreDataProvider
from sec_insider.data_fetcher import DataFetcher
from sec_insider.backtester import Backtester
from sec_insider.notion_logger import NotionLogger
import config
import sys

def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore
        
    # Composition Root: Dependency Injection Assembly
    data_provider = CoreDataProvider()
    fetcher = DataFetcher()
    backtester = Backtester(data_provider=data_provider)
    notion = NotionLogger()
    from sec_insider.reporter import SecInsiderReporter
    summary_reporter = SecInsiderReporter()

    print(f"[시스템 A] SEC Form 4 내부자 순매수 분석 파이프라인 가동 (필터: 거래 대금 ${config.MIN_INSIDER_BUY_VALUE:,} 달러 이상)...")
    signals = fetcher.get_insider_signals()
    
    processed_tickers = set()
    analyzed_results = []
    for sig in signals:
        ticker = sig.get('ticker')
        date_raw = sig.get('filedAt')
        
        # 직급 확인: CEO, CFO, President 등 핵심 임원 여부 판별
        raw_title = sig.get('officerTitle')
        job_title = str(raw_title if not isinstance(raw_title, list) else (raw_title[0] if raw_title else 'Director/Owner')).upper()
        is_clevel = any(role in job_title for role in ['CEO', 'CFO', 'PRESIDENT', 'CHIEF'])
        
        if ticker in processed_tickers: continue
            
        if ticker and date_raw:
            clean_date = str(date_raw[0] if isinstance(date_raw, list) else date_raw).split('T')[0]
            res = backtester.calculate_return(ticker, clean_date)
            
            if res:
                # 공시 데이터에 직급 정보 및 분류 추가
                res['Job_Title'] = job_title
                res['Importance'] = "핵심 경영진 (C-Level)" if is_clevel else "주요 주주 및 임원 (Officer/Director)"
                analyzed_results.append(res)
                
                if notion.add_row(res):
                    print(f"[기록 완료] {res['Importance']} | {ticker} 데이터베이스 등록 완료")
                processed_tickers.add(ticker)

    # [시스템 A] invest_provert 리포트 데이터베이스에 종합 보고서 발행
    if analyzed_results:
        print("[시스템 A] SEC 공시 내부자 거래 종합 운용 보고서 발행 중...")
        summary_reporter.send_summary_report(analyzed_results)

    print("[시스템 A] SEC 내부자 거래 동향 및 단기 성과 분석 완료.")

if __name__ == "__main__":
    main()