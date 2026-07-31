import pandas as pd
import numpy as np
from datetime import datetime
from lvmb_momentum.database import AntiGravityDB
from lvmb_momentum.alert import alert_system

class DataAuditor:
    def __init__(self, db_path="invest_standalone.db"):
        self.db = AntiGravityDB(db_path)

    def audit_dataframe(self, ticker, df, vol_dict=None) -> dict:
        """
        입력받은 시세 데이터프레임의 모든 영업일에 대한 정밀 감사 수행.
        결과를 DB에 로깅하고 심각한 오류 시 알림 트리거.
        """
        if df is None or df.empty:
            status = "FAIL"
            details = "DataFrame is None or empty"
            self.db.log_quality_audit(ticker, 0, 0, 1.0, status, details)
            alert_system.send_alert(f"[Data Quality Audit] {ticker} data is completely missing/empty.", "CRITICAL")
            return {"ticker": ticker, "total_days": 0, "anomaly_days": 0, "error_rate": 1.0, "status": status, "details": details}

        # 컬럼 명칭 표준화 처리
        cols = {}
        for col in df.columns:
            col_name = col[0] if isinstance(col, tuple) else col
            col_key = col_name.lower().replace(" ", "_")
            cols[col_key] = col
        open_col = cols.get("open")
        high_col = cols.get("high")
        low_col = cols.get("low")
        close_col = cols.get("close")
        adj_close_col = cols.get("adj_close")
        vol_col = cols.get("volume")

        # 필수 컬럼 검사
        if not open_col or not close_col:
            status = "FAIL"
            details = "Missing essential columns (Open, Close)"
            self.db.log_quality_audit(ticker, len(df), len(df), 1.0, status, details)
            alert_system.send_alert(f"[Data Quality Audit] {ticker} lacks Open or Close columns.", "CRITICAL")
            return {"ticker": ticker, "total_days": len(df), "anomaly_days": len(df), "error_rate": 1.0, "status": status, "details": details}

        total_days = len(df)
        anomaly_days = 0
        anomalies_found = []

        # 60일 변동성을 기반으로 한 동적 가격 임계치 계산
        daily_vol = None
        if vol_dict and ticker in vol_dict:
            ann_vol = vol_dict[ticker]
            daily_vol = ann_vol / (252 ** 0.5)

        # 자산별 동적/정적 혼합 임계치 설정 (최소 15% 마진)
        price_jump_threshold = max(3 * daily_vol, 0.15) if daily_vol else 0.15

        # 이전 종가 초기화
        prev_close = None

        # 루프를 통한 행별 정밀 감사
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
            
            # 1. NaN/Null 값 보유 검사
            if pd.isna(row[open_col]) or pd.isna(row[close_col]) or (high_col and pd.isna(row[high_col])) or (low_col and pd.isna(row[low_col])):
                anomaly_days += 1
                anomalies_found.append(f"[{date_str}] NaN value detected")
                prev_close = None
                continue

            open_val = float(row[open_col])
            close_val = float(row[close_col])
            high_val = float(row[high_col]) if high_col else None
            low_val = float(row[low_col]) if low_col else None
            vol_val = int(row[vol_col]) if vol_col else 0

            row_has_anomaly = False

            # 2. 가격 논리적 모순 검증
            # 고가가 저가보다 낮음
            if high_val is not None and low_val is not None and high_val < low_val:
                row_has_anomaly = True
                anomalies_found.append(f"[{date_str}] High ({high_val}) < Low ({low_val})")
            
            # 음수 가격 검출
            if open_val <= 0 or close_val <= 0 or (high_val is not None and high_val <= 0) or (low_val is not None and low_val <= 0):
                row_has_anomaly = True
                anomalies_found.append(f"[{date_str}] Non-positive price detected (Close: {close_val})")

            # 3. 전일 대비 시세 급변동(Outlier/Anomaly) 감지
            if prev_close is not None and prev_close > 0:
                jump_rate = abs(close_val / prev_close - 1)
                if jump_rate > price_jump_threshold:
                    row_has_anomaly = True
                    anomalies_found.append(f"[{date_str}] Extreme price jump: {jump_rate:.1%} vs threshold {price_jump_threshold:.1%}")

            if row_has_anomaly:
                anomaly_days += 1

            prev_close = close_val

        # 최종 에러율 산출 (0.0 ~ 1.0 비율)
        error_rate = (anomaly_days / total_days) if total_days > 0 else 0.0

        if error_rate == 0.0:
            status = "PASS"
            details = "All checks passed successfully."
        elif error_rate < 0.05:
            status = "WARNING"
            details = "; ".join(anomalies_found[:3])  # 최대 3개 요약 표시
        else:
            status = "FAIL"
            details = f"High error rate ({error_rate:.1%}): " + "; ".join(anomalies_found[:3])

        # DB 로그 적재
        self.db.log_quality_audit(ticker, total_days, anomaly_days, error_rate, status, details)

        # 문제 있을 시 텔레메트리/알림 트리거
        if status == "FAIL":
            alert_system.send_alert(
                f"[DATA QUALITY CRITICAL] {ticker} error rate {error_rate:.1%}. Anomaly days: {anomaly_days}/{total_days}. Details: {details}",
                "CRITICAL"
            )
        elif status == "WARNING":
            alert_system.send_alert(
                f"[DATA QUALITY WARNING] {ticker} anomalies detected ({error_rate:.1%}). Details: {details}",
                "WARNING"
            )

        return {
            "ticker": ticker,
            "total_days": total_days,
            "anomaly_days": anomaly_days,
            "error_rate": error_rate,
            "status": status,
            "details": details
        }

if __name__ == "__main__":
    auditor = DataAuditor()
    # Mock data test
    dates = pd.date_range(end="2026-06-05", periods=5)
    test_df = pd.DataFrame({
        "Open": [100.0, 101.0, 50.0, 102.0, 103.0],  # 3번째 날 가격 급락 모사 (50% 폭락)
        "High": [105.0, 106.0, 55.0, 107.0, 108.0],
        "Low": [95.0, 96.0, 45.0, 109.0, 98.0],     # 4번째 날 High < Low (107 < 109) 오류 모사
        "Close": [101.0, 100.0, 48.0, 103.0, 102.0],
        "Volume": [1000] * 5
    }, index=dates)

    print("Auditing mock data...")
    res = auditor.audit_dataframe("TEST_ETF", test_df)
    print("Audit Results:")
    print(res)
