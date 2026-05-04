"""
sector_theme.py — 섹터 분류 + 테마 이슈 분류
Finance-DataReader로 전 종목 섹터 로드 + 뉴스 기반 테마 감지
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
import FinanceDataReader as fdr  # pykrx 대신 fdr 사용

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# 섹터 매핑 — Finance-DataReader 동적 로드
# ────────────────────────────────────────────────

_SECTOR_CACHE: dict[str, str] = {}   # code → sector

def load_sector_map() -> dict[str, str]:
    """Finance-DataReader(FDR)로 KOSPI + KOSDAQ 전 종목 및 섹터 로드"""
    global _SECTOR_CACHE
    if _SECTOR_CACHE:
        return _SECTOR_CACHE

    try:
        # FDR은 StockListing('KRX') 한 번으로 코드, 이름, 산업(섹터)을 모두 가져옵니다.
        df_krx = fdr.StockListing('KRX')

        # 'Code'와 'Sector' 컬럼을 매핑 (결측치는 '기타'로 처리)
        result = {}
        for _, row in df_krx.iterrows():
            code = row['Code']
            sector = row['Sector'] if pd.notna(row['Sector']) else "기타"
            result[code] = sector

        if result:
            _SECTOR_CACHE = result
            logger.info("FDR 섹터 매핑 로드 완료: %d개", len(result))
            return _SECTOR_CACHE
    except Exception as e:
        logger.error("FDR 섹터 로드 중 에러 발생: %s", e)

    return _SECTOR_CACHE

# 수동 보완 섹터 맵 (FDR 섹터명이 너무 세분화되어 있을 때 핵심 키워드로 그룹화하기 위함)
MANUAL_SECTOR: dict[str, str] = {
    "005930": "반도체/소부장",  "000660": "반도체/소부장",
    # ... (기존 수동 매핑 리스트 유지)
}

def get_sector(code: str) -> str:
    """수동 매핑 우선, 없으면 FDR 로드 데이터에서 반환"""
    if code in MANUAL_SECTOR:
        return MANUAL_SECTOR[code]

    # 캐시에 없으면 로드 시도
    sector_map = load_sector_map()
    return sector_map.get(code, "기타")

# (이하 테마 이슈 분류 및 하단 로직은 기존과 동일하므로 유지)
# ... [ThemeIssue 클래스 및 classify_news_to_themes 등 기존 코드] ...