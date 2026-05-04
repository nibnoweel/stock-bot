"""
supply_scanner.py — 외인/기관 수급
pykrx만 사용 (기존 코드 의존성 동일)
"""

import logging
from datetime import datetime, timedelta
import pandas as pd
from pykrx import stock

logger = logging.getLogger(__name__)


def fetch_investor_data(code: str, days: int = 10) -> dict:
    """
    외인 / 기관 / 개인 10일 순매수 반환
    반환: {
        "foreign_10d": float (만주),
        "institution_10d": float (만주),
        "individual_10d": float (만주),
        "foreign_series": pd.Series,
        "institution_series": pd.Series,
    }
    """
    end   = datetime.now()
    start = end - timedelta(days=days * 2)   # 주말 여유분
    start_str = start.strftime("%Y%m%d")
    end_str   = end.strftime("%Y%m%d")

    empty = {
        "foreign_10d": 0.0, "institution_10d": 0.0, "individual_10d": 0.0,
        "foreign_series": pd.Series(dtype=float),
        "institution_series": pd.Series(dtype=float),
    }

    try:
        df = stock.get_market_trading_volume_by_date(start_str, end_str, code)
        if df is None or df.empty:
            return empty

        # pykrx 컬럼: 기관합계, 외국인합계, 개인
        col_map = {"외국인합계": "foreign", "기관합계": "institution", "개인": "individual"}
        for col in col_map:
            if col not in df.columns:
                return empty

        df = df.tail(days)
        f   = df["외국인합계"].sum() / 10000
        i   = df["기관합계"].sum()   / 10000
        ind = df["개인"].sum()        / 10000

        return {
            "foreign_10d":      round(f,   1),
            "institution_10d":  round(i,   1),
            "individual_10d":   round(ind, 1),
            "foreign_series":     df["외국인합계"],
            "institution_series": df["기관합계"],
        }

    except Exception as e:
        logger.debug("수급 조회 실패 %s: %s", code, e)
        return empty


def supply_arrow(val: float) -> str:
    """수급 만주 → 표시 문자열"""
    sign  = "+" if val >= 0 else ""
    arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
    return f"{sign}{val:.1f}만{arrow}"
