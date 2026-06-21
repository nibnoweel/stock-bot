"""
supply_scanner.py
pykrx → FinanceDataReader 전환
FDR은 외인/기관 수급을 직접 제공하지 않으므로
KRX 투자자별 거래 데이터를 requests로 직접 수집
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# KRX 투자자별 거래 API (공개 엔드포인트)
_KRX_INVESTOR_URL = (
    "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
)
_KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://data.krx.co.kr",
}


def _trading_dates(days: int) -> list[str]:
    """최근 N 거래일 날짜 리스트 (주말 제외)"""
    dates = []
    d = datetime.now()
    while len(dates) < days:
        if d.weekday() < 5:   # 월~금
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return dates


def fetch_investor_data(code: str, days: int = 10) -> dict:
    """
    KRX API 단일 호출로 기간 합산 수급 조회
    날짜별 루프(10번) → 기간 조회(1번)으로 변경
    """
    end   = datetime.now()
    start = end - timedelta(days=days * 2)  # 주말 여유분
    start_str = start.strftime("%Y%m%d")
    end_str   = end.strftime("%Y%m%d")

    params = {
        "bld":         "dbms/MDC/STAT/standard/MDCSTAT02203",  # 기간별 투자자
        "mktId":       "ALL",
        "strtDd":      start_str,
        "endDd":       end_str,
        "isuCd":       code,
        "money":       "1",
        "csvxls_isNo": "false",
    }

    empty = {
        "foreign_10d": 0.0, "institution_10d": 0.0, "individual_10d": 0.0,
        "foreign_series": pd.Series(dtype=float),
        "institution_series": pd.Series(dtype=float),
    }

    try:
        resp = requests.post(
            _KRX_INVESTOR_URL, data=params,
            headers=_KRX_HEADERS, timeout=10
        )
        data = resp.json()
        rows = data.get("output", [])
        if not rows:
            return empty

        f_total = i_total = ind_total = 0
        for row in rows:
            investor = row.get("INVST_TP_NM", "")
            try:
                val = int(str(row.get("NETBID_TRDVOL", "0")).replace(",", ""))
            except Exception:
                val = 0
            if "외국인" in investor:
                f_total += val
            elif "기관" in investor:
                i_total += val
            elif "개인" in investor:
                ind_total += val

        return {
            "foreign_10d":        round(f_total   / 10000, 1),
            "institution_10d":    round(i_total   / 10000, 1),
            "individual_10d":     round(ind_total / 10000, 1),
            "foreign_series":     pd.Series([f_total]),
            "institution_series": pd.Series([i_total]),
        }

    except Exception as e:
        logger.debug("KRX 수급 API 실패 %s: %s", code, e)
        return empty


def supply_arrow(val: float) -> str:
    sign  = "+" if val >= 0 else ""
    arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
    return f"{sign}{val:.1f}만{arrow}"

def supply_icon(val: float) -> str:
    """
    외인/기관 10일 순매수 아이콘
    🔥 : 50만주 이상 대량 순매수
    ▲  : 0 초과 순매수
    •  : -10만주 ~ 0 (소폭 순매도)
    ▼  : -10만주 미만 순매도
    """
    if val >= 50:   return "🔥"
    if val > 0:     return "▲"
    if val >= -10:  return "•"
    return                 "▼"

def supply_fmt(val: float) -> str:
    """리포트 표시용 — +85.1만 🔥 형태"""
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}만 {supply_icon(val)}"