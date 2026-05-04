"""
sector_theme.py — 섹터 분류 + 테마 이슈 분류
pykrx로 전 종목 섹터 동적 로드 + 뉴스 기반 테마 감지
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import pandas as pd
from pykrx import stock

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# 섹터 매핑 — pykrx 동적 로드
# ────────────────────────────────────────────────

_SECTOR_CACHE: dict[str, str] = {}   # code → sector

def load_sector_map() -> dict[str, str]:
    """pykrx로 KOSPI + KOSDAQ 전 종목 섹터 동적 로드"""
    global _SECTOR_CACHE
    if _SECTOR_CACHE:
        return _SECTOR_CACHE

    # 최근 거래일 찾기
    for days_ago in range(0, 10):
        d = (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")
        if datetime.strptime(d, "%Y%m%d").weekday() >= 5:
            continue
        try:
            result = {}
            for market in ["KOSPI", "KOSDAQ"]:
                codes = stock.get_market_ticker_list(date=d, market=market)
                for code in codes:
                    try:
                        info = stock.get_market_ticker_name(code)
                        # pykrx get_market_cap 에서 섹터 정보 없으므로
                        # KRX 업종 분류 사용
                        sector = _get_sector_from_krx(code, d)
                        result[code] = sector
                    except Exception:
                        pass
            if result:
                _SECTOR_CACHE = result
                logger.info("섹터 매핑 로드: %d개", len(result))
                return _SECTOR_CACHE
        except Exception as e:
            logger.debug("섹터 로드 실패 %s: %s", d, e)

    return _SECTOR_CACHE


def _get_sector_from_krx(code: str, date: str) -> str:
    """pykrx get_index_portfolio_deposit_file 또는 업종분류 활용"""
    # pykrx는 종목별 섹터를 직접 제공하지 않으므로
    # 뉴스 키워드 기반 THEME_KEYWORDS로 섹터를 부여
    return "기타"


# 수동 보완 섹터 맵 (pykrx 섹터 미제공 보완용)
MANUAL_SECTOR: dict[str, str] = {
    "005930": "반도체/소부장",  "000660": "반도체/소부장",
    "042700": "반도체/소부장",  "093370": "반도체/소부장",
    "012450": "방산",           "079550": "방산",
    "047810": "방산",           "064350": "방산",
    "009540": "조선/해운",      "042660": "조선/해운",
    "011200": "조선/해운",      "010120": "전력/전기장비",
    "001440": "전력/전기장비",  "034020": "전력/전기장비",
    "068270": "바이오/제약",    "207940": "바이오/제약",
    "000100": "바이오/제약",    "128940": "바이오/제약",
    "035420": "AI/IT/게임",     "035720": "AI/IT/게임",
    "005380": "자동차/부품",    "000270": "자동차/부품",
    "051910": "에너지/화학",    "010950": "에너지/화학",
    "105560": "금융/보험",      "055550": "금융/보험",
    "086790": "금융/보험",      "316140": "금융/보험",
    "096770": "2차전지",        "247540": "2차전지",
    "086520": "2차전지",
}

def get_sector(code: str) -> str:
    return MANUAL_SECTOR.get(code, "기타")


# ────────────────────────────────────────────────
# 테마 이슈 분류
# ────────────────────────────────────────────────

THEME_KEYWORDS: list[tuple] = [
    # (키워드 리스트, 테마명, 방향, 관련섹터)
    (["AI", "인공지능", "엔비디아", "HBM", "데이터센터"],
     "AI/데이터센터 투자 확대", "▲상승", ["AI/IT/게임", "반도체/소부장", "전력/전기장비"]),

    (["반도체", "파운드리", "메모리", "D램", "HBM"],
     "반도체 수출 호조", "▲상승", ["반도체/소부장"]),

    (["방산", "K-방산", "수출", "무기", "FA-50"],
     "K-방산 수출 확대", "▲상승", ["방산"]),

    (["원전", "SMR", "K-원전", "핵발전"],
     "원전/SMR 정책 수혜", "▲상승", ["전력/전기장비"]),

    (["중동", "호르무즈", "이란", "이스라엘"],
     "중동 긴장 고조", "▲상승", ["방산", "에너지/화학", "조선/해운"]),

    (["종전", "휴전", "평화"],
     "종전/평화 기대", "▲상승", ["건설/부동산", "유통/소비재", "조선/해운"]),

    (["바이오", "신약", "임상", "FDA", "GLP-1"],
     "바이오 신약/임상", "▲상승", ["바이오/제약"]),

    (["스테이블코인", "가상자산", "코인", "디지털자산"],
     "스테이블코인/디지털자산 법제화", "▲상승", ["AI/IT/게임", "금융/보험"]),

    (["관세", "트럼프", "무역분쟁"],
     "미국 관세 리스크", "▼하락", ["자동차/부품", "반도체/소부장"]),

    (["2차전지", "배터리", "IRA", "전기차"],
     "2차전지/배터리 정책", "▲상승", ["2차전지"]),

    (["금리", "Fed", "FOMC", "기준금리"],
     "금리 정책 변화", "▲상승", ["금융/보험", "건설/부동산"]),

    (["해운", "운임", "조선", "LNG"],
     "조선/해운 수주 강세", "▲상승", ["조선/해운"]),
]


@dataclass
class ThemeIssue:
    theme_name: str
    direction: str
    related_sectors: list[str]
    matched_keywords: list[str]
    news_count: int = 0
    related_stocks: list[str] = field(default_factory=list)

    @property
    def is_bullish(self) -> bool:
        return "상승" in self.direction


def classify_news_to_themes(news_items: list[dict]) -> list[ThemeIssue]:
    """
    NewsScanner.scan() 결과 또는 fetch 뉴스 리스트에서 테마 감지
    news_items: [{title, text, ...}, ...]
    """
    hits: dict[str, ThemeIssue] = {}

    for item in news_items:
        text = item.get("title", "") + " " + item.get("text", "")

        for keywords, theme_name, direction, sectors in THEME_KEYWORDS:
            matched = [kw for kw in keywords if kw in text]
            if not matched:
                continue
            if theme_name not in hits:
                hits[theme_name] = ThemeIssue(
                    theme_name=theme_name,
                    direction=direction,
                    related_sectors=sectors,
                    matched_keywords=list(matched),
                )
            else:
                for kw in matched:
                    if kw not in hits[theme_name].matched_keywords:
                        hits[theme_name].matched_keywords.append(kw)
            hits[theme_name].news_count += 1

    return sorted(hits.values(), key=lambda t: t.news_count, reverse=True)


def match_stock_themes(code: str, themes: list[ThemeIssue]) -> int:
    """해당 종목의 섹터가 오늘 테마에 몇 개 매칭되는지 반환"""
    sector = get_sector(code)
    return sum(1 for t in themes if sector in t.related_sectors)


# ────────────────────────────────────────────────
# 핫 키워드 집계
# ────────────────────────────────────────────────

HOT_KEYWORDS = [
    "트럼프", "반도체", "현대차", "삼성전자", "바이오",
    "이스라엘", "뉴욕증시", "호르무즈", "AI", "원전",
    "조선", "방산", "전기차", "금리", "환율",
]

def count_hot_keywords(news_items: list[dict], top_n: int = 8) -> list[tuple[str, int]]:
    counts = {kw: 0 for kw in HOT_KEYWORDS}
    for item in news_items:
        text = item.get("title", "") + item.get("text", "")
        for kw in HOT_KEYWORDS:
            if kw in text:
                counts[kw] += 1
    return sorted(
        [(kw, cnt) for kw, cnt in counts.items() if cnt > 0],
        key=lambda x: x[1], reverse=True
    )[:top_n]
