import pandas as pd
import numpy as np
from dataclasses import dataclass

@dataclass
class RiskReportDTO:
    """계좌 방어 수준과 권고 현금 비중을 담는 불변 데이터 전송 객체"""
    benchmark_r12: float          # 나스닥 12개월 모멘텀
    benchmark_z_score: float      # 나스닥 20일 Z-Score
    portfolio_beta: float         # 포트폴리오 시장 민감도 (Beta)
    estimated_var_krw: float      # 나스닥 -5% 쇼크 시 원화(KRW) 예상 손실액
    recommended_cash_weight: float# 최종 권고 안전자산(현금) 비중 (0.0 ~ 1.0)
    regime_status: str            # 현재 시장 상태 경고문

class LiveRiskRadar:
    """
    과거 백테스트를 대체하는 실시간 포트폴리오 리스크 레이더.
    결정론적 순수 수학 함수로 시장 레짐과 VaR(Value at Risk)를 진단하여 
    오늘 당장의 방어 전술을 지시합니다.
    """
    
    @staticmethod
    def calculate_macro_regime(benchmark_prices: pd.Series) -> tuple[float, float]:
        """QQQ(벤치마크)의 12개월 모멘텀(R12)과 20일 Z-Score 산출"""
        r12 = float(benchmark_prices.pct_change(periods=252).iloc[-1])
        
        mu = benchmark_prices.rolling(window=20).mean().iloc[-1]
        sigma = benchmark_prices.rolling(window=20).std().iloc[-1]
        
        # Division by zero 방어
        z_score = float((benchmark_prices.iloc[-1] - mu) / sigma) if sigma != 0 else 0.0
        
        return r12, z_score

    @staticmethod
    def calculate_shock_var(port_returns: pd.Series, bench_returns: pd.Series, total_equity_krw: float, shock_pct: float = -0.05) -> tuple[float, float]:
        """포트폴리오 베타 산출 및 나스닥 쇼크 시 원화(KRW) 예상 최대 손실액 계산"""
        # 두 수익률 시리즈의 길이를 가장 짧은 쪽에 맞춰 정렬 (Look-ahead 및 결측치 방지)
        aligned_port, aligned_bench = port_returns.align(bench_returns, join='inner')
        
        if len(aligned_port) < 2:
            return 1.0, float(total_equity_krw * shock_pct)
            
        cov_matrix = np.cov(aligned_port, aligned_bench)
        beta = float(cov_matrix[0, 1] / cov_matrix[1, 1]) if cov_matrix[1, 1] != 0 else 1.0
        
        # VaR (Value at Risk) 산출
        estimated_loss_pct = beta * shock_pct
        var_krw = float(total_equity_krw * estimated_loss_pct)
        
        return beta, var_krw

    @classmethod
    def generate_daily_risk_report(cls, port_returns: pd.Series, bench_prices: pd.Series, total_equity_krw: float, base_safe_weight: float = 0.3) -> RiskReportDTO:
        """
        각종 지표를 종합하여 일일 전술 브리핑을 위한 최종 DTO를 조립합니다.
        기본 안전자산 비중을 30%로 두고, 위기 국면마다 현금 비중을 동적으로 상향합니다.
        """
        r12, z_score = cls.calculate_macro_regime(bench_prices)
        bench_returns = bench_prices.pct_change().dropna()
        
        beta, var_krw = cls.calculate_shock_var(port_returns, bench_returns, total_equity_krw)
        
        # 동적 현금 비중 (Dynamic Cash Weighting) 산출 로직
        cash_weight = base_safe_weight
        regime_status = "NORMAL (평시 추세)"
        
        if r12 < 0:
            cash_weight += 0.4  # 대세 하락장: 코어 자산 방어를 위해 현금 비중 대폭 확대 (70%)
            regime_status = "BEAR MARKET (장기 하락장 진입)"
            
        if z_score < -2.0:
            cash_weight = 1.0   # 시스템 붕괴 임박: MDD Halt 전 선제적 100% 현금화
            regime_status = "CRASH WARNING (통계적 붕괴 포착)"
            
        # 0% ~ 100% 사이로 클리핑
        cash_weight = min(max(cash_weight, 0.0), 1.0)
        
        return RiskReportDTO(
            benchmark_r12=r12,
            benchmark_z_score=z_score,
            portfolio_beta=beta,
            estimated_var_krw=var_krw,
            recommended_cash_weight=cash_weight,
            regime_status=regime_status
        )
