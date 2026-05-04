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


def _fetch_krx_investor(code: str, date: str) -> dict:
    """
    KRX data.krx.co.kr 에서 투자자별 순매수 조회
    반환: {"외국인": int, "기관합계": int, "개인": int}  단위: 주
    """
    params = {
        "bld":        "dbms/MDC/STAT/standard/MDCSTAT02202",
        "mktId":      "ALL",
        "trdDd":      date,
        "isuCd":      code,
        "money":      "1",      # 1=주식수
        "csvxls_isNo": "false",
    }
    try:
        resp = requests.post(_KRX_INVESTOR_URL, data=params,
                             headers=_KRX_HEADERS, timeout=10)
        data = resp.json()
        rows = data.get("output", [])
        result = {"외국인": 0, "기관합계": 0, "개인": 0}
        for row in rows:
            investor = row.get("INVST_TP_NM", "")
            try:
                val = int(str(row.get("NETBID_TRDVOL", "0")).replace(",", "").replace("-", "-"))
            except Exception:
                val = 0
            if "외국인" in investor:
                result["외국인"] += val
            elif "기관" in investor:
                result["기관합계"] += val
            elif "개인" in investor:
                result["개인"] += val
        return result
    except Exception as e:
        logger.debug("KRX 투자자 API 실패 %s %s: %s", code, date, e)
        return {"외국인": 0, "기관합계": 0, "개인": 0}


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
    외인 / 기관 / 개인 10일 순매수 반환
    반환: {
        "foreign_10d":      float (만주),
        "institution_10d":  float (만주),
        "individual_10d":   float (만주),
        "foreign_series":   pd.Series,
        "institution_series": pd.Series,
    }
    """
    dates = _trading_dates(days)

    foreign_list     = []
    institution_list = []
    individual_list  = []

    for date in dates:
        row = _fetch_krx_investor(code, date)
        foreign_list.append(row["외국인"])
        institution_list.append(row["기관합계"])
        individual_list.append(row["개인"])

    f_series   = pd.Series(foreign_list)
    i_series   = pd.Series(institution_list)
    ind_series = pd.Series(individual_list)

    return {
        "foreign_10d":        round(f_series.sum()   / 10000, 1),
        "institution_10d":    round(i_series.sum()   / 10000, 1),
        "individual_10d":     round(ind_series.sum() / 10000, 1),
        "foreign_series":     f_series,
        "institution_series": i_series,
    }


def supply_arrow(val: float) -> str:
    sign  = "+" if val >= 0 else ""
    arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
    return f"{sign}{val:.1f}만{arrow}"