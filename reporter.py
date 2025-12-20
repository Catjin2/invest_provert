import pandas as pd
import os
from datetime import datetime

class Reporter:
    def __init__(self, output_folder="reports"):
        self.output_folder = output_folder
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

    def generate_summary(self, results):
        if not results:
            print("⚠️ 저장할 분석 결과가 없습니다.")
            return

        # 1. 데이터를 데이터프레임으로 변환
        df = pd.DataFrame(results)
        
        # 2. 파일명에 현재 시간 기록 (파일 덮어쓰기 방지)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = os.path.join(self.output_folder, f"insider_report_{timestamp}.csv")
        
        # 3. CSV로 저장 (엑셀에서 바로 열림)
        df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        
        # 4. 요약 통계 계산
        win_rate = (df['Return_Pct'] > 0).mean() * 100
        avg_return = df['Return_Pct'].mean()
        total_profit = df['Profit'].sum()

        print("\n" + "="*30)
        print(f"📊 최종 분석 보고서 요약")
        print(f"📂 저장 경로: {csv_filename}")
        print(f"📈 평균 수익률: {avg_return:.2f}%")
        print(f"💰 총 손익: ${total_profit:.2f}")
        print(f"🎯 승률: {win_rate:.1f}%")
        print("="*30)