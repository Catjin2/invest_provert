"""
Scenario Lab CLI Entrypoint (시스템 C 실행기)
실전 DB(invest_standalone.db) 오염 없는 0-I/O 순수 RAM 기반 시뮬레이션 구동.
Filter ON vs Filter OFF A/B 벤치마크, 차트 생성, 노션 보고서 전송.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import argparse
from typing import Dict, List
import pandas as pd
import yfinance as yf

from scenario_lab.engine import ScenarioLabEngine, clean_df
from scenario_lab.reporter import ScenarioLabReporter

PREDEFINED_SCENARIOS = {
    "covid_crash": {
        "name": "2020 코로나 팬데믹 폭락장",
        "fetch_start": "2019-01-01",
        "sim_start": "2020-02-01",
        "sim_end": "2020-04-30",
        "tickers": ["QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    },
    "covid_cycle": {
        "name": "2020 코로나 급락 및 V자 반등 사이클",
        "fetch_start": "2019-01-01",
        "sim_start": "2019-10-01",
        "sim_end": "2020-06-30",
        "tickers": ["QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    },
    "rate_hike_2022": {
        "name": "2022 연준 고금리 긴축 쇼크",
        "fetch_start": "2021-01-01",
        "sim_start": "2022-01-03",
        "sim_end": "2022-10-31",
        "tickers": ["QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "GOOGL"]
    }
}

def run_single_scenario(scenario_key: str, config_dict: dict, capital: float, no_notion: bool):
    name = config_dict["name"]
    fetch_start = config_dict["fetch_start"]
    sim_start = config_dict["sim_start"]
    sim_end = config_dict["sim_end"]
    tickers = config_dict["tickers"]

    print("\n" + "=" * 70)
    print(f"[시스템 C] 위기 국면 스트레스 테스트 구동: {name} ({scenario_key})")
    print(f"   시뮬레이션 구간: {sim_start} ~ {sim_end} (데이터 준비: {fetch_start}부터)")
    print(f"   검증 유니버스: {', '.join(tickers)} | 초기 자본: ${capital:,.2f}")
    print("=" * 70)

    # 1. Historical Data Download (with lookback buffer)
    print("[데이터 수집] 벤치마크 시계열 데이터 수신 중...")
    hist_data = {}
    for t in tickers:
        try:
            df = yf.download(t, start=fetch_start, end=sim_end, progress=False)
            df_cleaned = clean_df(df)
            if df_cleaned is not None and not df_cleaned.empty:
                hist_data[t] = df_cleaned
        except Exception as e:
            print(f"[경고] {t} 다운로드 실패: {e}")

    if not hist_data:
        print("[오류] 주가 데이터를 확보하지 못하여 시나리오 실행을 중단합니다.")
        return

    # 2. Run A/B Simulations
    print("\n[A] 리스크 관리 모델 (Z-Score 필터 + 트레일링 스탑 + 서킷브레이커) 시뮬레이션...")
    df_on, trader_on = ScenarioLabEngine.run_simulation(
        hist_data,
        start_date=sim_start,
        end_date=sim_end,
        enable_z_filter=True,
        initial_capital=capital
    )
    metrics_on = ScenarioLabEngine.calculate_metrics(df_on)

    print("[B] 벤치마크 기준 모델 (리스크 관리 필터 미적용 기준 모델) 시뮬레이션...")
    df_off, trader_off = ScenarioLabEngine.run_simulation(
        hist_data,
        start_date=sim_start,
        end_date=sim_end,
        enable_z_filter=False,
        initial_capital=capital
    )
    metrics_off = ScenarioLabEngine.calculate_metrics(df_off)

    defense_mdd = metrics_on['mdd_pct'] - metrics_off['mdd_pct']

    # 3. Print Results Summary Table
    print("\n" + "-" * 70)
    print("[스트레스 테스트 정량 분석 결과]")
    print(f"{'구분':<25} | {'최종 자산 ($)':<14} | {'수익률 (%)':<12} | {'최대 낙폭 MDD (%)':<16}")
    print("-" * 70)
    print(f"{'리스크 관리 모델 (시스템 C)':<25} | ${metrics_on['final']:>12,.2f} | {metrics_on['return_pct']:>10.2f}% | {metrics_on['mdd_pct']:>14.2f}%")
    print(f"{'벤치마크 기준 모델':<25} | ${metrics_off['final']:>12,.2f} | {metrics_off['return_pct']:>10.2f}% | {metrics_off['mdd_pct']:>14.2f}%")
    print("-" * 70)
    print(f"최대 낙폭(MDD) 방어 개선도: {defense_mdd:+.2f}%p (위기 국면 손실 축소 효과 검증)")
    print(f"포트폴리오 서킷브레이커: {'발동 (전량 현금화 포지션 방어)' if trader_on.is_halted else '정상 운용 범위 (임계치 미도달)'}")
    print(f"리스크 관리 집행 건수: 리스크 관리 모델 ({len(trader_on.events)}건) vs 기준 모델 ({len(trader_off.events)}건)")
    print("-" * 70)

    # 4. Generate Chart & Notion Reporting
    reporter = ScenarioLabReporter()
    chart_url = reporter.generate_comparison_chart(scenario_key, name, df_on, df_off)

    if no_notion:
        print("[안내] --no-notion 옵션 활성화: 노션 전송을 생략합니다.")
    else:
        print("\n[시스템 C] 노션 운용 보고서 전송 중...")
        success = reporter.send_report(
            scenario_key=scenario_key,
            scenario_name=name,
            start_date=sim_start,
            end_date=sim_end,
            metrics_on=metrics_on,
            metrics_off=metrics_off,
            events_on=trader_on.events,
            chart_url=chart_url
        )
        if success:
            print("[완료] 노션 데이터베이스 보고서 발행 완료")
        else:
            print("[경고] 노션 전송 실패 (토큰 또는 네트워크 상태 확인 필요)")

def main():
    parser = argparse.ArgumentParser(description="Scenario Lab - 시스템 C 위기 검증 랩 시뮬레이터")
    parser.add_argument(
        "--scenario",
        type=str,
        default="covid_crash",
        choices=["covid_crash", "covid_cycle", "rate_hike_2022", "all"],
        help="실행할 위기 시나리오 선택 (기본값: covid_crash)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="가상 초기 자본 (USD, 기본값: 10,000)"
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="노션 보고서 전송 비활성화 (로컬 시뮬레이션 및 차트 생성만 수행)"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="사용자 정의 종목 티커 (쉼표로 구분, 예: 'QQQ,AAPL,NVDA')"
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("[시스템 C] 위기 국면 스트레스 테스트 및 인메모리 시뮬레이션 엔진")
    print("   -> 실전 DB (invest_standalone.db) 무간섭(Zero I/O) 완전 격리 가상 환경")
    print("   -> 15슬롯 동적 자본 배분 및 슬리피지/거래비용 현실 마찰 반영")
    print("   -> 트레일링 스탑(-10%), Z-Score 과열 필터(-2.0), 포트폴리오 서킷브레이커(-15% MDD)")
    print("=" * 70)

    if args.scenario == "all":
        for key, conf in PREDEFINED_SCENARIOS.items():
            if args.tickers:
                conf = dict(conf)
                conf["tickers"] = [t.strip().upper() for t in args.tickers.split(",")]
            run_single_scenario(key, conf, args.capital, args.no_notion)
    else:
        conf = PREDEFINED_SCENARIOS[args.scenario]
        if args.tickers:
            conf = dict(conf)
            conf["tickers"] = [t.strip().upper() for t in args.tickers.split(",")]
        run_single_scenario(args.scenario, conf, args.capital, args.no_notion)

if __name__ == "__main__":
    main()
