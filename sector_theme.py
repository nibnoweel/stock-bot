"""
sector_theme.py — 섹터 분류 + 테마 이슈 분류
Finance-DataReader로 전 종목 섹터 로드 + 뉴스 기반 테마 감지

[beta] GPT-5 Mini 동적 테마 감지 추가:
  - 기존 하드코딩 12개 테마는 그대로 유지
  - OPENAI_API_KEY 미설정 시 기존 방식으로 폴백
"""

import json
import logging
from dataclasses import dataclass, field
import pandas as pd
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# 섹터 매핑 — Finance-DataReader 동적 로드
# ────────────────────────────────────────────────

_SECTOR_CACHE: dict[str, str] = {}

def load_sector_map() -> dict[str, str]:
    """MANUAL_SECTOR만 사용 (FDR은 Sector 컬럼 미제공)"""
    global _SECTOR_CACHE
    if _SECTOR_CACHE:
        return _SECTOR_CACHE
    _SECTOR_CACHE = MANUAL_SECTOR.copy()
    logger.info("섹터 매핑 로드: %d개 (수동)", len(_SECTOR_CACHE))
    return _SECTOR_CACHE

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
    if code in MANUAL_SECTOR:
        return MANUAL_SECTOR[code]
    sector_map = load_sector_map()
    return sector_map.get(code, "기타")

# ────────────────────────────────────────────────
# 테마 이슈 분류 (하드코딩)
# ────────────────────────────────────────────────

THEME_KEYWORDS: list[tuple] = [
    (["AI", "인공지능", "엔비디아", "HBM", "데이터센터"], "AI/데이터센터 투자 확대", "▲상승", ["AI/IT/게임", "반도체/소부장", "전력/전기장비"]),
    (["반도체", "파운드리", "메모리", "D램", "HBM"], "반도체 수출 호조", "▲상승", ["반도체/소부장"]),
    (["방산", "K-방산", "수출", "무기", "FA-50"], "K-방산 수출 확대", "▲상승", ["방산"]),
    (["원전", "SMR", "K-원전", "핵발전"], "원전/SMR 정책 수혜", "▲상승", ["전력/전기장비"]),
    (["중동", "호르무즈", "이란", "이스라엘"], "중동 긴장 고조", "▲상승", ["방산", "에너지/화학", "조선/해운"]),
    (["종전", "휴전", "평화"], "종전/평화 기대", "▲상승", ["건설/부동산", "유통/소비재", "조선/해운"]),
    (["바이오", "신약", "임상", "FDA", "GLP-1"], "바이오 신약/임상", "▲상승", ["바이오/제약"]),
    (["스테이블코인", "가상자산", "코인", "디지털자산"], "스테이블코인/디지털자산 법제화", "▲상승", ["AI/IT/게임", "금융/보험"]),
    (["관세", "트럼프", "무역분쟁"], "미국 관세 리스크", "▼하락", ["자동차/부품", "반도체/소부장"]),
    (["2차전지", "배터리", "IRA", "전기차"], "2차전지/배터리 정책", "▲상승", ["2차전지"]),
    (["금리", "Fed", "FOMC", "기준금리"], "금리 정책 변화", "▲상승", ["금융/보험", "건설/부동산"]),
    (["해운", "운임", "조선", "LNG"], "조선/해운 수주 강세", "▲상승", ["조선/해운"]),
]

@dataclass
class ThemeIssue:
    theme_name: str
    direction: str
    related_sectors: list[str]
    matched_keywords: list[str]
    news_count: int = 0
    related_stocks: list[str] = field(default_factory=list)
    source: str = "keyword"  # "keyword" | "gpt"

    @property
    def is_bullish(self) -> bool:
        return "상승" in self.direction

def classify_news_to_themes(news_items: list[dict]) -> list[ThemeIssue]:
    hits: dict[str, ThemeIssue] = {}
    for item in news_items:
        text = item.get("title", "") + " " + item.get("text", "")
        for keywords, theme_name, direction, sectors in THEME_KEYWORDS:
            matched = [kw for kw in keywords if kw in text]
            if not matched:
                continue
            if theme_name not in hits:
                hits[theme_name] = ThemeIssue(
                    theme_name=theme_name, direction=direction,
                    related_sectors=sectors, matched_keywords=list(matched),
                    source="keyword"
                )
            else:
                for kw in matched:
                    if kw not in hits[theme_name].matched_keywords:
                        hits[theme_name].matched_keywords.append(kw)
            hits[theme_name].news_count += 1
    return sorted(hits.values(), key=lambda t: t.news_count, reverse=True)

# ────────────────────────────────────────────────
# [beta] GPT-5 Mini 동적 테마 감지
# ────────────────────────────────────────────────

_KNOWN_SECTORS = [
    "반도체/소부장", "방산", "조선/해운", "전력/전기장비", "바이오/제약",
    "AI/IT/게임", "자동차/부품", "에너지/화학", "금융/보험", "2차전지",
    "건설/부동산", "유통/소비재", "기타"
]

_GPT_SYSTEM_PROMPT = """당신은 한국 주식시장 전문 애널리스트입니다.
뉴스 제목 목록을 보고 오늘 주식시장에서 주목해야 할 테마 이슈를 추출합니다.

규칙:
1. 하드코딩 테마(아래 목록)에 해당하지 않는 새로운 테마만 추출합니다.
2. 최소 3개 이상의 뉴스가 뒷받침되는 테마만 포함합니다.
3. 최대 5개까지 추출합니다.
4. 반드시 JSON 배열만 반환합니다. 다른 텍스트 없이.

이미 처리된 기존 테마 목록 (이것들은 제외):
- AI/데이터센터 투자 확대
- 반도체 수출 호조
- K-방산 수출 확대
- 원전/SMR 정책 수혜
- 중동 긴장 고조
- 종전/평화 기대
- 바이오 신약/임상
- 스테이블코인/디지털자산 법제화
- 미국 관세 리스크
- 2차전지/배터리 정책
- 금리 정책 변화
- 조선/해운 수주 강세

응답 형식 (JSON 배열):
[
  {
    "theme_name": "테마명 (간결하게 10자 이내)",
    "direction": "▲상승 또는 ▼하락",
    "related_sectors": ["섹터1", "섹터2"],
    "matched_keywords": ["키워드1", "키워드2"],
    "news_count": 관련뉴스수(정수)
  }
]

사용 가능한 섹터 목록: """ + ", ".join(_KNOWN_SECTORS)


def _detect_themes_with_gpt(news_items: list[dict], known_theme_names: set[str]) -> list[ThemeIssue]:
    try:
        from config import OPENAI_API_KEY
        if not OPENAI_API_KEY:
            logger.info("[GPT 테마] OPENAI_API_KEY 미설정 — 스킵")
            return []

        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        titles = [item.get("title", "") for item in news_items if item.get("title")][:150]
        if not titles:
            return []

        news_text = "\n".join(f"- {t}" for t in titles)
        user_msg = f"다음은 오늘 수집된 한국 경제 뉴스 제목 {len(titles)}개입니다:\n\n{news_text}"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _GPT_SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=800,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            name = item.get("theme_name", "").strip()
            if not name or name in known_theme_names:
                continue
            results.append(ThemeIssue(
                theme_name=name,
                direction=item.get("direction", "▲상승"),
                related_sectors=item.get("related_sectors", ["기타"]),
                matched_keywords=item.get("matched_keywords", []),
                news_count=int(item.get("news_count", 0)),
                source="gpt",
            ))

        logger.info("[GPT 테마] 새 테마 %d개 감지", len(results))
        return results

    except json.JSONDecodeError as e:
        logger.warning("[GPT 테마] JSON 파싱 실패: %s", e)
        return []
    except Exception as e:
        logger.warning("[GPT 테마] 오류 발생 (폴백): %s", e)
        return []


def classify_news_to_themes_with_gpt(news_items: list[dict]) -> list[ThemeIssue]:
    """[beta] 하드코딩 테마 + GPT 동적 테마를 합쳐서 반환."""
    keyword_themes = classify_news_to_themes(news_items)
    known_names = {t.theme_name for t in keyword_themes}
    gpt_themes = _detect_themes_with_gpt(news_items, known_names)
    return keyword_themes + gpt_themes

# ────────────────────────────────────────────────
# Scanner에서 호출하는 핵심 함수
# ────────────────────────────────────────────────

def match_stock_themes(code: str, themes: list[ThemeIssue]) -> int:
    sector = get_sector(code)
    return sum(1 for t in themes if sector in t.related_sectors)

# ────────────────────────────────────────────────
# 핫 키워드 집계
# ────────────────────────────────────────────────

HOT_KEYWORDS = ["트럼프", "반도체", "현대차", "삼성전자", "바이오", "이스라엘", "AI", "원전", "조선", "방산"]

def count_hot_keywords(news_items: list[dict], top_n: int = 8) -> list[tuple[str, int]]:
    counts = {kw: 0 for kw in HOT_KEYWORDS}
    for item in news_items:
        text = item.get("title", "") + item.get("text", "")
        for kw in HOT_KEYWORDS:
            if kw in text:
                counts[kw] += 1
    return sorted([(kw, cnt) for kw, cnt in counts.items() if cnt > 0], key=lambda x: x[1], reverse=True)[:top_n]