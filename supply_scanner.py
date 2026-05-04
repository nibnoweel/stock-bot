"""
supply_scanner.py
외인 / 기관 수급 데이터 수집
- FinanceDataReader investor 데이터 사용
- pykrx fallback 지원
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────
# 수급 데이터 수집
# ────────────────────────────────────────────────

def fetch_investor_data(
    code: str,
    days: int = 10,
) -> dict[str, pd.Series]:
    """
    외인 / 기관 / 개인 일별 순매수 반환
    반환: {"foreign": Series, "institution": Series, "individual": Series}
    각 Series index = 날짜, value = 순매수 주식수 (주)
    """
    end   = datetime.today()
    start = end - timedelta(days=days * 2)   # 주말 여유분 포함
    start_str = start.strftime("%Y%m%d")
    end_str   = end.strftime("%Y%m%d")

    result = {"foreign": pd.Series(dtype=float),
              "institution": pd.Series(dtype=float),
              "individual": pd.Series(dtype=float)}

    # ── 1차: pykrx ────────────────────────────────
    try:
        from pykrx import stock as krx
        df = krx.get_market_trading_volume_by_date(start_str, end_str, code)
        if df is not None and not df.empty:
            # pykrx 컬럼: 기관합계, 외국인합계, 개인
            col_map = {
                "외국인합계": "foreign",
                "기관합계": "institution",
                "개인": "individual",
            }
            for krx_col, key in col_map.items():
                if krx_col in df.columns:
                    result[key] = df[krx_col].iloc[-days:]
            logger.debug(f"[pykrx] {code} 수급 로드 완료")
            return result
    except Exception as e:
        logger.debug(f"[pykrx] {code} 실패: {e}")

    # ── 2차: FinanceDataReader ─────────────────────
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code, start_str, end_str)
        # FDR은 투자자별 순매수 컬럼을 직접 제공하지 않아 0 반환
        logger.debug(f"[FDR] {code} 가격만 로드, 수급 없음")
    except Exception as e:
        logger.debug(f"[FDR] {code} 실패: {e}")

    return result   # 빈 Series 반환


# ────────────────────────────────────────────────
# 수급 요약 텍스트 (리포트용)
# ────────────────────────────────────────────────

def supply_summary(foreign_10d: float, institution_10d: float) -> str:
    """
    외인/기관 10일 누적 순매수 (만주) → 요약 문자열
    예: "+85.1만▲ / +55.4만▲"
    """
    def fmt(val: float) -> str:
        sign = "+" if val >= 0 else ""
        arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
        return f"{sign}{val:.1f}만{arrow}"

    return f"{fmt(foreign_10d)} / {fmt(institution_10d)}"


# ────────────────────────────────────────────────
# 전체 시장 수급 상위 종목 스캔
# ────────────────────────────────────────────────

def scan_top_supply(
    codes: list[str],
    days: int = 10,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    codes 리스트에서 외인+기관 합산 순매수 상위 top_n 종목 반환
    반환 컬럼: code, foreign_10d(만주), institution_10d(만주), combined_10d(만주)
    """
    rows = []
    for code in codes:
        try:
            data = fetch_investor_data(code, days=days)
            f = data["foreign"].sum() / 10000
            i = data["institution"].sum() / 10000
            rows.append({
                "code": code,
                "foreign_10d": round(f, 1),
                "institution_10d": round(i, 1),
                "combined_10d": round(f + i, 1),
            })
        except Exception as e:
            logger.warning(f"[supply_scan] {code} 건너뜀: {e}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values("combined_10d", ascending=False).head(top_n).reset_index(drop=True)
