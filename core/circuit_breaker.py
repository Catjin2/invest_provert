"""
Defensive Programming & Data Integrity Circuit Breaker for Financial Pipelines.
Guards against 0/negative prices, severe data corruptions, and stale data.
"""

from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


class CircuitBreakerException(Exception):
    """기본 서킷브레이커 예외"""
    pass


class DataCorruptionException(CircuitBreakerException):
    """가격이 0원 이하이거나 비상식적인 왜곡이 발생했을 때 발생하는 예외"""
    pass


class StaleDataException(CircuitBreakerException):
    """데이터가 오늘 또는 직전 거래일 기준 신선하지 않을 때 발생하는 예외"""
    pass


class MarketDataCircuitBreaker:
    """
    시장 데이터 무결성 검증기.
    비정상 데이터가 신호 생성기나 주문 집행 모듈에 유입되는 것을 원천 차단합니다.
    """

    @staticmethod
    def validate_price(
        ticker: str,
        price: float,
        prev_price: Optional[float] = None,
        max_gap_pct: float = 0.30,
    ) -> float:
        """
        단일 가격의 유효성을 검증합니다.
        - price <= 0 또는 NaN / Inf 감지 시 즉시 차단
        - 전일 대비 30% 이상(상하한가 초과) 비상식적 갭 발생 시 차단
        """
        if price is None or np.isnan(price) or np.isinf(price) or price <= 0.0:
            raise DataCorruptionException(
                f"[CIRCUIT BREAKER] Corrupted price detected for {ticker}: {price}. Trading halted."
            )

        if prev_price is not None and prev_price > 0.0:
            gap = abs(price - prev_price) / prev_price
            if gap > max_gap_pct:
                raise DataCorruptionException(
                    f"[CIRCUIT BREAKER] Abnormal price gap ({gap * 100:.1f}% > {max_gap_pct * 100:.0f}%) "
                    f"for {ticker}: {prev_price} -> {price}. Trading halted."
                )

        return float(price)

    @staticmethod
    def validate_freshness(
        latest_date_str: str,
        max_stale_days: int = 4,
        reference_date: Optional[datetime] = None,
    ) -> bool:
        """
        데이터의 최종 일자가 허용 가능한 신선도(주말 감안 기본 4일) 이내인지 검증합니다.
        """
        if not latest_date_str:
            raise StaleDataException("[CIRCUIT BREAKER] Missing date string for freshness check.")

        # 날짜 문자열 파싱 (YYYY-MM-DD)
        clean_date = latest_date_str.split(" ")[0].split("T")[0]
        try:
            data_dt = datetime.strptime(clean_date, "%Y-%m-%d")
        except ValueError as e:
            raise StaleDataException(f"[CIRCUIT BREAKER] Unparseable date '{latest_date_str}': {e}")

        ref_dt = reference_date or datetime.now()
        diff_days = (ref_dt.date() - data_dt.date()).days

        if diff_days > max_stale_days:
            raise StaleDataException(
                f"[CIRCUIT BREAKER] Stale market data detected! Last date: {clean_date} "
                f"({diff_days} days old > max {max_stale_days} days). Trading halted."
            )

        return True

    @staticmethod
    def validate_dataframe(
        df: Optional[pd.DataFrame],
        ticker: str,
        required_columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        데이터프레임의 구조와 결측치 무결성을 검증합니다.
        """
        if df is None or df.empty:
            raise DataCorruptionException(f"[CIRCUIT BREAKER] Empty DataFrame received for {ticker}.")

        req_cols = required_columns or ["Close"]
        for col in req_cols:
            if col not in df.columns:
                raise DataCorruptionException(
                    f"[CIRCUIT BREAKER] Missing required column '{col}' for {ticker} in DataFrame."
                )

        # 종가 컬럼에 최근 데이터가 전부 NaN인지 검사
        close_series = df["Close"]
        if close_series.dropna().empty:
            raise DataCorruptionException(
                f"[CIRCUIT BREAKER] All Close values are NaN for {ticker}."
            )

        latest_close = close_series.dropna().iloc[-1]
        if isinstance(latest_close, pd.Series):
            latest_close = latest_close.iloc[0]

        if latest_close <= 0.0:
            raise DataCorruptionException(
                f"[CIRCUIT BREAKER] Latest close is non-positive ({latest_close}) for {ticker}."
            )

        return df
