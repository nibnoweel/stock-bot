"""
news_scanner.py
pykrx → FinanceDataReader 전환
종목 리스팅: fdr.StockListing('KOSPI' / 'KOSDAQ')

[업그레이드]
- fetch_all_news(): 날짜(date) 필드 추가
- build_theme_news_map(): 테마별 관련 헤드라인 매핑
- build_hot_keyword_map(): 키워드별 출처 건수 + 관련 종목 + 헤드라인
"""

import logging
import feedparser
import difflib
from datetime import datetime, timedelta
import FinanceDataReader as fdr
# ── [신규] 증권사 목표주가 변동 수집 ────────────
import re
# 네이버 금융 리서치 RSS (공개)
_RESEARCH_RSS = "https://finance.naver.com/research/debenture_list.naver"
logger = logging.getLogger(__name__)

RSS_SOURCES = [
    ("한국경제",   "https://www.hankyung.com/feed/finance"),
    ("매일경제",   "https://www.mk.co.kr/rss/30000001/"),
    ("연합뉴스",   "https://www.yna.co.kr/rss/economy.xml"),
    ("머니투데이", "https://rss.mt.co.kr/mt_news_top.xml"),
    ("이데일리",   "https://rss.edaily.co.kr/edaily_stocknews.xml"),
    ("서울경제",   "https://www.sedaily.com/rss/Stock"),
]

# ────────────────────────────────────────────────
# 5단계 가중치 키워드 시스템
# ────────────────────────────────────────────────

POSITIVE_WEIGHTS: dict[str, int] = {
    "상한가": 5, "어닝서프라이즈": 5, "FDA 승인": 5, "임상 성공": 5,
    "기술수출": 5, "대형 수주": 5, "최대 실적": 5, "사상 최대": 5,
    "턴어라운드": 5, "흑자전환": 5,
    "신고가": 4, "급등": 4, "어닝": 4, "수주": 4, "계약 체결": 4,
    "기술이전": 4, "임상 3상": 4, "FDA": 4, "실적 개선": 4,
    "영업이익 증가": 4, "매출 증가": 4, "자사주 매입": 4, "자사주 소각": 4,
    "합병": 4, "인수": 4, "독점 공급": 4, "우선협상": 4, "양산": 4, "상장": 4,
    "호실적": 3, "흑자": 3, "수출": 3, "특허": 3, "승인": 3, "허가": 3,
    "신제품": 3, "출시": 3, "개발 성공": 3, "MOU": 3, "협약": 3,
    "공급 계약": 3, "배당 증가": 3, "목표주가 상향": 3, "투자의견 상향": 3,
    "바이": 3, "매수": 3, "임상 2상": 3, "품목허가": 3,
    "수익성 개선": 3, "원가 절감": 3, "점유율 확대": 3,
    "계약": 2, "협력": 2, "파트너십": 2, "투자 유치": 2, "증설": 2,
    "생산 확대": 2, "수요 증가": 2, "회복": 2, "반등": 2, "저평가": 2,
    "임상 1상": 2, "IND 승인": 2, "시장 확대": 2, "신규 고객": 2, "수주 잔고": 2,
    "기대": 1, "전망": 1, "모색": 1, "추진": 1, "검토": 1,
    "논의": 1, "긍정적": 1, "상승세": 1, "관심": 1,
}

NEGATIVE_WEIGHTS: dict[str, int] = {
    "하한가": 5, "상장폐지": 5, "파산": 5, "부도": 5, "횡령": 5,
    "배임": 5, "구속": 5, "기소": 5, "감사의견 거절": 5, "거래정지": 5, "워크아웃": 5,
    "급락": 4, "어닝쇼크": 4, "적자전환": 4, "영업손실": 4, "대규모 손실": 4,
    "불성실공시": 4, "관리종목": 4, "감사의견": 4, "수사": 4, "검찰": 4,
    "과징금": 4, "유상증자": 4, "전환사채": 4, "신주인수권": 4,
    "리콜": 4, "결함": 4, "제재": 4, "계약 해지": 4, "수주 취소": 4,
    "적자": 3, "손실": 3, "매출 감소": 3, "실적 악화": 3, "하향": 3,
    "목표주가 하향": 3, "투자의견 하향": 3, "매도": 3, "소송": 3, "사기": 3,
    "반품": 3, "취소": 3, "파기": 3, "임상 실패": 3, "FDA 거절": 3,
    "허가 취소": 3, "공급 차질": 3, "납품 지연": 3,
    "교환사채": 3, "무상감자": 3, "최대주주 변경": 3,
    "우려": 2, "부진": 2, "둔화": 2, "감소": 2, "하락": 2, "악화": 2,
    "지연": 2, "불확실": 2, "위험": 2, "리스크": 2, "조정": 2,
    "대량 매도": 2, "블록딜": 2, "오버행": 2, "보호예수 해제": 2, "임원 매도": 2,
    "약세": 1, "부담": 1, "경쟁 심화": 1, "포화": 1, "둔화 우려": 1,
    "관망": 1, "부정적": 1, "하락세": 1,
}

POSITIVE_KEYWORDS = list(POSITIVE_WEIGHTS.keys())
NEGATIVE_KEYWORDS = list(NEGATIVE_WEIGHTS.keys())


def weighted_sentiment(text: str) -> float:
    pos = sum(w for kw, w in POSITIVE_WEIGHTS.items() if kw in text)
    neg = sum(w for kw, w in NEGATIVE_WEIGHTS.items() if kw in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


# ────────────────────────────────────────────────
# NewsScanner
# ────────────────────────────────────────────────

class NewsScanner:
    def __init__(self):
        self._ticker_cache = {}

    def _load_tickers(self) -> dict[str, str]:
        if self._ticker_cache:
            return self._ticker_cache
        try:
            kospi  = fdr.StockListing("KOSPI")[["Code", "Name"]]
            kosdaq = fdr.StockListing("KOSDAQ")[["Code", "Name"]]
            df = (
                kospi._append(kosdaq)
                .drop_duplicates(subset="Code")
                .reset_index(drop=True)
            )
            df["Code"] = df["Code"].astype(str).str.zfill(6)
            self._ticker_cache = dict(zip(df["Name"], df["Code"]))
            logger.info("종목명 캐시 로드: %d개", len(self._ticker_cache))
        except Exception as e:
            logger.error("종목 리스팅 실패: %s", e)
        return self._ticker_cache

    def _is_duplicate(self, new_title, existing_titles, threshold=0.7):
        for title in existing_titles:
            if difflib.SequenceMatcher(None, new_title, title).ratio() > threshold:
                return True
        return False

    def _fetch_news(self) -> list[dict]:
        news_list   = []
        seen_links  = set()
        seen_titles = []

        for source_name, url in RSS_SOURCES:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:30]:
                    title   = entry.get("title", "").strip()
                    link    = entry.get("link",  "").strip()
                    summary = entry.get("summary", "")

                    # 날짜 파싱 (published 필드)
                    date_str = ""
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            import time
                            t = entry.published_parsed
                            date_str = f"{t.tm_mon:02d}.{t.tm_mday:02d}"
                        except Exception:
                            pass
                    if not date_str:
                        date_str = datetime.now().strftime("%m.%d")

                    if link in seen_links:
                        continue
                    if self._is_duplicate(title, seen_titles):
                        continue
                    seen_links.add(link)
                    seen_titles.append(title)
                    news_list.append({
                        "source":  source_name,
                        "title":   title,
                        "link":    link,
                        "summary": summary,
                        "text":    title + " " + summary,
                        "date":    date_str,
                    })
            except Exception as e:
                logger.debug("%s RSS 수집 실패: %s", source_name, e)

        logger.info("중복 제거 후 총 %d개 뉴스 수집", len(news_list))
        return news_list

    def _match_tickers(self, text, tickers):
        return [
            (name, code) for name, code in tickers.items()
            if len(name) >= 2 and name in text
        ]

    def _classify(self, text):
        pos_kw = [kw for kw in POSITIVE_WEIGHTS if kw in text]
        neg_kw = [kw for kw in NEGATIVE_WEIGHTS if kw in text]
        pos_score = sum(POSITIVE_WEIGHTS[kw] for kw in pos_kw)
        neg_score = sum(NEGATIVE_WEIGHTS[kw] for kw in neg_kw)
        valid_pos = pos_kw if pos_score >= 2 else []
        valid_neg = neg_kw if neg_score >= 2 else []
        return valid_pos, valid_neg

    def scan(self):
        tickers    = self._load_tickers()
        news_list  = self._fetch_news()
        stock_news = {}

        for news in news_list:
            text    = news["text"]
            matched = self._match_tickers(text, tickers)
            if not matched:
                continue
            pos_kw, neg_kw = self._classify(text)
            if not pos_kw and not neg_kw:
                continue

            for name, code in matched:
                if name not in stock_news:
                    stock_news[name] = {"code": code, "pos_kw": {}, "neg_kw": {}, "news": []}
                for kw in pos_kw:
                    stock_news[name]["pos_kw"][kw] = POSITIVE_WEIGHTS[kw]
                for kw in neg_kw:
                    stock_news[name]["neg_kw"][kw] = NEGATIVE_WEIGHTS[kw]
                existing = [n["title"] for n in stock_news[name]["news"]]
                if news["title"] not in existing:
                    stock_news[name]["news"].append({
                        "title":  news["title"],
                        "link":   news["link"],
                        "source": news["source"],
                        "date":   news.get("date", ""),
                    })

        positive_results, negative_results = [], []
        for name, data in stock_news.items():
            item = {"name": name, "code": data["code"], "news": data["news"][:3]}
            if data["pos_kw"]:
                sorted_pos = sorted(data["pos_kw"], key=data["pos_kw"].get, reverse=True)
                positive_results.append({**item, "keywords": sorted_pos,
                                          "score": sum(data["pos_kw"].values())})
            if data["neg_kw"]:
                sorted_neg = sorted(data["neg_kw"], key=data["neg_kw"].get, reverse=True)
                negative_results.append({**item, "keywords": sorted_neg,
                                          "score": sum(data["neg_kw"].values())})

        positive_results.sort(key=lambda x: x["score"], reverse=True)
        negative_results.sort(key=lambda x: x["score"], reverse=True)
        logger.info("긍정: %d종목, 부정: %d종목", len(positive_results), len(negative_results))
        return positive_results, negative_results


# ── bot.py 파이프라인용 함수 ─────────────────────

def fetch_all_news() -> list[dict]:
    return NewsScanner()._fetch_news()

def classify_sentiment(text: str) -> float:
    return weighted_sentiment(text)

def build_stock_sentiment_map(news_items: list[dict]) -> dict[str, float]:
    ns      = NewsScanner()
    tickers = ns._load_tickers()
    scores: dict[str, list[float]] = {}
    for item in news_items:
        title = item.get("title", "")
        score = weighted_sentiment(title)
        for name, code in tickers.items():
            if len(name) >= 2 and name in title:
                scores.setdefault(code, []).append(score)
    return {code: round(sum(v) / len(v), 3) for code, v in scores.items()}


# ── [신규] 테마별 헤드라인 매핑 ─────────────────

def build_theme_news_map(
    news_items: list[dict],
    theme_keywords: list[tuple],
    max_headlines: int = 8,
) -> dict[str, list[dict]]:
    """
    테마별로 매칭된 뉴스 헤드라인 리스트 반환.
    반환: { theme_name: [ {date, source, title, link}, ... ] }
    """
    theme_map: dict[str, list[dict]] = {}

    for keywords, theme_name, _, _ in theme_keywords:
        matched = []
        for item in news_items:
            text = item.get("title", "") + " " + item.get("summary", "")
            if any(kw in text for kw in keywords):
                matched.append({
                    "date":   item.get("date", ""),
                    "source": item.get("source", ""),
                    "title":  item.get("title", ""),
                    "link":   item.get("link",  ""),
                })
        theme_map[theme_name] = matched[:max_headlines]

    return theme_map


# ── [신규] 핫 키워드별 상세 매핑 ────────────────

HOT_KEYWORDS = ["트럼프", "반도체", "현대차", "삼성전자", "바이오",
                "이스라엘", "AI", "원전", "조선", "방산"]

def build_hot_keyword_map(
    news_items: list[dict],
    top_n: int = 8,
    max_headlines: int = 3,
) -> list[dict]:
    """
    핫 키워드별 출처 건수 + 관련 헤드라인 반환.
    반환:
    [
      {
        "keyword": "트럼프",
        "total": 13,
        "by_source": {"네이버_세계": 12, "네이버_경제": 1},
        "headlines": [ {date, source, title, link}, ... ],
      },
      ...
    ]
    """
    kw_data: dict[str, dict] = {
        kw: {"total": 0, "by_source": {}, "headlines": []}
        for kw in HOT_KEYWORDS
    }

    for item in news_items:
        title  = item.get("title", "")
        source = item.get("source", "")
        date   = item.get("date",   "")
        link   = item.get("link",   "")

        for kw in HOT_KEYWORDS:
            if kw in title:
                kw_data[kw]["total"] += 1
                kw_data[kw]["by_source"][source] = \
                    kw_data[kw]["by_source"].get(source, 0) + 1
                if len(kw_data[kw]["headlines"]) < max_headlines:
                    kw_data[kw]["headlines"].append({
                        "date":   date,
                        "source": source,
                        "title":  title,
                        "link":   link,
                    })

    # 건수 기준 정렬 후 top_n
    result = sorted(
        [{"keyword": kw, **data} for kw, data in kw_data.items() if data["total"] > 0],
        key=lambda x: x["total"],
        reverse=True,
    )
    return result[:top_n]

def fetch_target_price_changes(max_items: int = 20) -> list[dict]:
    """
    네이버 금융 리서치에서 목표주가 변동 리포트 수집.
    반환:
    [
      {
        "name":       "삼성전자",
        "direction":  "상향" | "하향" | "유지" | "신규",
        "target":     80000,      # 목표주가 (원), 없으면 None
        "current":    75000,      # 현재가, 없으면 None
        "gap_pct":    6.7,        # 괴리율 (%), 없으면 None
        "firm":       "하나증권",
        "summary":    "리포트 제목",
        "date":       "04.17",
      },
      ...
    ]
    """
    results = []
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(
            "https://finance.naver.com/research/debenture_list.naver",
            headers=headers, timeout=10
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table.type_1 tr")
        for row in rows[:max_items * 2]:
            cols = row.select("td")
            if len(cols) < 5:
                continue
            try:
                name    = cols[0].get_text(strip=True)
                title   = cols[1].get_text(strip=True)
                firm    = cols[2].get_text(strip=True)
                date    = cols[4].get_text(strip=True)

                # 목표주가 파싱 (제목에서 숫자 추출)
                price_matches = re.findall(r"[\d,]+원", title)
                target = None
                if price_matches:
                    try:
                        target = int(price_matches[-1].replace(",", "").replace("원", ""))
                    except Exception:
                        pass

                # 방향 감지
                direction = "유지"
                if any(kw in title for kw in ["상향", "목표주가 상향", "TP 상향"]):
                    direction = "상향"
                elif any(kw in title for kw in ["하향", "목표주가 하향", "TP 하향"]):
                    direction = "하향"
                elif any(kw in title for kw in ["신규", "커버리지 개시"]):
                    direction = "신규"

                if not name or len(name) < 2:
                    continue

                results.append({
                    "name":      name,
                    "direction": direction,
                    "target":    target,
                    "current":   None,   # 현재가는 별도 조회 필요
                    "gap_pct":   None,
                    "firm":      firm,
                    "summary":   title[:60],
                    "date":      date,
                })

                if len(results) >= max_items:
                    break

            except Exception:
                continue

    except ImportError:
        logger.warning("beautifulsoup4 미설치 — 목표주가 수집 스킵")
    except Exception as e:
        logger.warning("목표주가 수집 실패: %s", e)

    return results