"""
sector_theme.py
섹터 분류 + 테마별 이슈 분류
PDF 리포트의 "정책 관전 종목" 섹터 카드 및 "오늘의 매크로 이슈" 테마 재현
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import re


# ────────────────────────────────────────────────
# 섹터 매핑 (종목코드 → 섹터명)
# PDF 리포트 기준 섹터 분류
# ────────────────────────────────────────────────

SECTOR_MAP: dict[str, str] = {
    # 반도체/소부장
    "005930": "반도체/소부장",  # 삼성전자
    "000660": "반도체/소부장",  # SK하이닉스
    "000990": "반도체/소부장",  # DB하이텍
    "058470": "반도체/소부장",  # 리노공업
    "009150": "반도체/소부장",  # 삼성전기
    "036830": "반도체/소부장",  # 솔브레인홀딩스
    "042700": "반도체/소부장",  # 한미반도체
    "093370": "반도체/소부장",  # LX세미콘
    "095340": "반도체/소부장",  # ISC
    "035900": "반도체/소부장",  # JYP엔터 → 제외
    # AI/IT/게임
    "035420": "AI/IT/게임",    # NAVER
    "035720": "AI/IT/게임",    # 카카오
    "251270": "AI/IT/게임",    # 넷마블
    "036570": "AI/IT/게임",    # 엔씨소프트
    "263750": "AI/IT/게임",    # 펄어비스
    "112040": "AI/IT/게임",    # 위메이드
    # 바이오/제약
    "068270": "바이오/제약",   # 셀트리온
    "207940": "바이오/제약",   # 삼성바이오로직스
    "000100": "바이오/제약",   # 유한양행
    "128940": "바이오/제약",   # 한미약품
    "009270": "바이오/제약",   # 한미사이언스
    "326030": "바이오/제약",   # SK바이오팜
    "271560": "바이오/제약",   # 오스템임플란트
    # 방산
    "012450": "방산",          # 한화에어로스페이스
    "000680": "방산",          # LS네트웍스 → 제외
    "079550": "방산",          # LIG넥스원
    "047810": "방산",          # 한국항공우주
    "093820": "방산",          # 풍산
    "064350": "방산",          # 현대로템
    "015760": "방산",          # 한국전력 → 제외
    # 에너지/화학
    "010950": "에너지/화학",   # S-Oil
    "051910": "에너지/화학",   # LG화학
    "011790": "에너지/화학",   # SKC
    "006650": "에너지/화학",   # 금호석유화학
    # 조선/해운
    "009540": "조선/해운",     # HD한국조선해양
    "042660": "조선/해운",     # 한화오션
    "011200": "조선/해운",     # HMM
    "003490": "조선/해운",     # 대한항공 → 운송
    # 건설/부동산
    "000720": "건설/부동산",   # 현대건설
    "000140": "건설/부동산",   # 하이트진로 → 제외
    "011760": "건설/부동산",   # 현대개발
    # 유통/소비재
    "139480": "유통/소비재",   # 이마트
    "023530": "유통/소비재",   # 롯데쇼핑
    "069960": "유통/소비재",   # 현대백화점
    # 전력/전기장비/ESS
    "010120": "전력/전기장비/ESS",  # LS ELECTRIC
    "064760": "전력/전기장비/ESS",  # 수산인더스트리 → 제외
    "001440": "전력/전기장비/ESS",  # 대한전선
    "034020": "전력/전기장비/ESS",  # 두산에너빌리티
    # 2차전지
    "096770": "2차전지",       # SK이노베이션
    "247540": "2차전지",       # 에코프로비엠
    "086520": "2차전지",       # 에코프로
    "002380": "2차전지",       # KCC글라스 → 제외
    # 자동차/부품
    "005380": "자동차/부품",   # 현대차
    "000270": "자동차/부품",   # 기아
    "011210": "자동차/부품",   # 현대위아
    # 금융/보험
    "105560": "금융/보험",     # KB금융
    "055550": "금융/보험",     # 신한지주
    "086790": "금융/보험",     # 하나금융지주
    "316140": "금융/보험",     # 우리금융지주
    # 운송/물류
    "003490": "운송/물류",     # 대한항공
    "020560": "운송/물류",     # 아시아나항공
    "002620": "운송/물류",     # 제주항공
}


def get_sector(code: str, default: str = "기타") -> str:
    """종목코드로 섹터 반환"""
    return SECTOR_MAP.get(code, default)


def classify_by_sector(codes: list[str]) -> dict[str, list[str]]:
    """코드 리스트를 섹터별로 분류"""
    sectors: dict[str, list[str]] = {}
    for code in codes:
        sec = get_sector(code)
        sectors.setdefault(sec, []).append(code)
    return sectors


# ────────────────────────────────────────────────
# 테마 이슈 분류
# ────────────────────────────────────────────────

# 테마 키워드 → (테마명, 방향, 관련섹터)
THEME_KEYWORDS: list[tuple[list[str], str, str, list[str]]] = [
    # keywords, theme_name, direction, related_sectors
    (["AI", "인공지능", "엔비디아", "HBM", "데이터센터"],
     "AI/데이터센터 투자 확대", "▲상승", ["AI/IT/게임", "반도체/소부장", "전력/전기장비/ESS"]),

    (["반도체", "파운드리", "메모리", "D램"],
     "반도체 수출 호조", "▲상승", ["반도체/소부장"]),

    (["방산", "K-방산", "수출", "무기"],
     "K-방산 수출 확대", "▲상승", ["방산"]),

    (["원전", "SMR", "핵발전", "K-원전"],
     "원전/SMR 정책 수혜", "▲상승", ["전력/전기장비/ESS"]),

    (["중동", "호르무즈", "이란", "이스라엘", "전쟁"],
     "중동 긴장 고조", "▲상승", ["방산", "에너지/화학", "조선/해운"]),

    (["종전", "휴전", "평화"],
     "종전/평화 기대", "▲상승", ["건설/부동산", "유통/소비재", "운송/물류"]),

    (["바이오", "신약", "임상", "FDA", "GLP-1"],
     "바이오 신약/임상", "▲상승", ["바이오/제약"]),

    (["스테이블코인", "가상자산", "코인", "디지털자산"],
     "스테이블코인/디지털자산 법제화", "▲상승", ["AI/IT/게임", "금융/보험"]),

    (["관세", "트럼프", "무역"],
     "미국 관세 리스크", "▼하락", ["자동차/부품", "반도체/소부장"]),

    (["2차전지", "배터리", "IRA", "전기차"],
     "2차전지/배터리 정책", "▲상승", ["2차전지"]),

    (["금리", "Fed", "FOMC", "기준금리"],
     "금리 정책 변화", "▲상승", ["금융/보험", "건설/부동산"]),

    (["해운", "운임", "조선"],
     "조선/해운 수주 강세", "▲상승", ["조선/해운"]),
]


@dataclass
class ThemeIssue:
    """테마 이슈 하나"""
    theme_name: str
    direction: str          # "▲상승" / "▼하락"
    related_sectors: list[str]
    matched_keywords: list[str]
    news_count: int = 0
    summary: str = ""
    related_stocks: list[str] = field(default_factory=list)  # 종목코드

    @property
    def is_bullish(self) -> bool:
        return "상승" in self.direction


def classify_news_to_themes(news_texts: list[str]) -> list[ThemeIssue]:
    """
    뉴스 텍스트 리스트를 분석해 테마 이슈 목록 반환
    반환: 매칭 뉴스 건수 많은 순 정렬
    """
    theme_hits: dict[str, ThemeIssue] = {}

    for text in news_texts:
        text_upper = text.upper()

        for keywords, theme_name, direction, sectors in THEME_KEYWORDS:
            matched = [kw for kw in keywords if kw.upper() in text_upper]
            if not matched:
                continue

            if theme_name not in theme_hits:
                theme_hits[theme_name] = ThemeIssue(
                    theme_name=theme_name,
                    direction=direction,
                    related_sectors=sectors,
                    matched_keywords=matched,
                )
            else:
                for kw in matched:
                    if kw not in theme_hits[theme_name].matched_keywords:
                        theme_hits[theme_name].matched_keywords.append(kw)

            theme_hits[theme_name].news_count += 1

    # 뉴스 건수 내림차순 정렬
    return sorted(theme_hits.values(), key=lambda t: t.news_count, reverse=True)


def match_stock_themes(code: str, themes: list[ThemeIssue]) -> int:
    """
    특정 종목이 오늘 테마에 몇 개 매칭되는지 반환 (점수용)
    """
    sector = get_sector(code)
    count = 0
    for theme in themes:
        if sector in theme.related_sectors:
            count += 1
    return count


# ────────────────────────────────────────────────
# 핫 키워드 카운트 (뉴스 제목 기반)
# ────────────────────────────────────────────────

HOT_KEYWORDS = [
    "트럼프", "반도체", "현대차", "삼성전자", "바이오",
    "이스라엘", "뉴욕증시", "호르무즈", "AI", "원전",
    "조선", "방산", "전기차", "금리", "환율",
]


def count_hot_keywords(news_texts: list[str], top_n: int = 8) -> list[tuple[str, int]]:
    """
    뉴스 제목 리스트에서 핫 키워드 빈도 집계
    반환: [(키워드, 건수), ...] 상위 top_n
    """
    counts: dict[str, int] = {kw: 0 for kw in HOT_KEYWORDS}
    for text in news_texts:
        for kw in HOT_KEYWORDS:
            if kw in text:
                counts[kw] += 1

    sorted_kw = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [(kw, cnt) for kw, cnt in sorted_kw if cnt > 0][:top_n]


# ────────────────────────────────────────────────
# 정책 관련 종목 그루핑 (테마 → 종목 카드)
# ────────────────────────────────────────────────

@dataclass
class PolicyThemeGroup:
    """PDF '정책 관전 종목' 카드 하나"""
    theme_label: str         # 예: "원전/수소"
    policy_summary: str      # 정책 한줄 요약
    stocks: list[str]        # 종목코드 리스트

    def emoji(self) -> str:
        emoji_map = {
            "원전": "⚛️", "방산": "🛡️", "AI": "🤖",
            "바이오": "💊", "반도체": "🔬", "조선": "⚓",
            "2차전지": "🔋", "스테이블": "💰", "전력": "⚡",
        }
        for key, em in emoji_map.items():
            if key in self.theme_label:
                return em
        return "📌"
