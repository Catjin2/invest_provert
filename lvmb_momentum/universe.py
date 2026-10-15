from enum import Enum
from dataclasses import dataclass
from typing import List
import os
import json
from datetime import datetime

class AssetRole(Enum):
    CORE_GROWTH = "핵심 성장 (나스닥/S&P500)"
    CORE_DIVIDEND = "핵심 배당 (SCHD 한국판)"
    SAFE_ASSET = "안전 자산 (단기채/파킹형)"

@dataclass
class ISATicker:
    symbol: str         # 야후 파이낸스 크롤링을 위한 .KS 확장자 포함 티커
    name: str           # 리포트 출력용 직관적 종목명
    role: AssetRole     # 자산배분 역할

class ISAUniverse:
    """
    청년 ISA 계좌 비과세 매매를 위한 국내 상장 해외 ETF 유니버스.
    야후 파이낸스(yfinance) 연동을 위해 모든 한국 종목 코드는 '.KS'로 끝납니다.
    """
    
    # 실전 운용을 위한 엄선된 ETF 풀 (질문자님의 기존 관심 종목 반영)
    TICKERS = [
        # 1. 공격수 (추세 추종 및 자본 차익)
        ISATicker("133690.KS", "TIGER 미국나스닥100", AssetRole.CORE_GROWTH),
        ISATicker("360750.KS", "TIGER 미국S&P500", AssetRole.CORE_GROWTH),
        
        # 2. 미드필더 (배당 재투자 및 하방 방어)
        ISATicker("446720.KS", "SOL 미국배당다우존스", AssetRole.CORE_DIVIDEND),
        ISATicker("402970.KS", "ACE 미국배당다우존스", AssetRole.CORE_DIVIDEND),
        
        # 3. 수비수 (현금성 자산 및 레이더 경고 발령 시 대피처)
        # KOFR(한국 무위험지표금리) 추종 ETF로 사실상 예금/현금과 동일한 역할
        ISATicker("329650.KS", "TIGER KOFR금리액티브(합성)", AssetRole.SAFE_ASSET) 
    ]
    
    @classmethod
    def get_all_symbols(cls) -> List[str]:
        """데이터 프로바이더가 다운로드할 전체 티커 리스트 반환"""
        return [t.symbol for t in cls.TICKERS]
        
    @classmethod
    def get_symbols_by_role(cls, role: AssetRole) -> List[str]:
        """특정 역할(성장, 배당, 안전)에 해당하는 티커만 필터링"""
        return [t.symbol for t in cls.TICKERS if t.role == role]
        
    @classmethod
    def get_name(cls, symbol: str) -> str:
        """티커 코드를 사람이 읽기 쉬운 한글 이름으로 변환"""
        for t in cls.TICKERS:
            if t.symbol == symbol:
                return t.name
        return symbol


class AssetUniverse:
    """글로벌 멀티에셋 ETF 유니버스 (하위 호환성 유지)"""
    def __init__(self):
        self.config_path = "invest_universe.json"

    def get_nasdaq100(self):
        """Returns the global multi-asset ETF universe."""
        return [
            "SPY", "QQQ", "IWM", "VGK", "EWJ", 
            "XLK", "XLF", "XLE", "XLV", 
            "GLD", "USO", "TLT", "IEF", "SHY", "LQD"
        ]

    def load_base_universe(self):
        """Loads the current base universe from disk, or fetches it if not present."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "nasdaq_100" in data:
                        return data["nasdaq_100"]
            except Exception:
                pass
            return self.get_nasdaq100()

    def get_universe_for_year(self, year):
        """Reconstructs the universe for a specific year (disabled for ETF universe)."""
        base = self.load_base_universe() or self.get_nasdaq100()
        return list(base)

    def update_universe(self):
        ndx = self.get_nasdaq100()
        universe = {
            "nasdaq_100": ndx,
            "last_updated": datetime.now().isoformat()
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(universe, f, indent=4)
        return universe

    def load_universe(self, year=None):
        if year is not None:
            tickers = self.get_universe_for_year(year)
            return {
                "nasdaq_100": tickers,
                "year": year,
                "last_updated": datetime.now().isoformat()
            }
        if not os.path.exists(self.config_path):
            return self.update_universe()
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

AntiGravityUniverse = AssetUniverse
