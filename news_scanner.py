"""
news_scanner.py (업그레이드)
기존 NewsScanner 클래스 완전 유지
+ fetch_all_news / classify_sentiment / build_stock_sentiment_map 추가
"""

import logging
import feedparser
import difflib
from datetime import datetime, timedelta
from pykrx import stock

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    ("한국경제",   "https://www.hankyung.com/feed/finance"),
    ("매일경제",   "https://www.mk.co.kr/rss/30000001/"),
    ("연합뉴스",   "https://www.yna.co.kr/rss/economy.xml"),
    ("머니투데이", "https://rss.mt.co.kr/mt_news_top.xml"),
    ("이데일리",   "https://rss.edaily.co.kr/edaily_stocknews.xml"),
    ("서울경제",   "https://www.sedaily.com/rss/Stock"),
]

POSITIVE_KEYWORDS = [
    "수주","계약","특허","승인","허가","급등","상한가","신고가",
    "흑자","실적개선","매출증가","호실적","어닝서프라이즈",
    "대형계약","수출","FDA","임상성공","기술이전","MOU","협약",
    "신제품","출시","개발성공","양산","독점","우선협상",
]

NEGATIVE_KEYWORDS = [
    "횡령","배임","소송","적자","영업손실","매출감소","실적악화",
    "하한가","급락","상장폐지","관리종목","감사의견","불성실공시",
    "사기","검찰","수사","구속","기소","과징금","제재",
    "리콜","결함","반품","취소","해지","파산","워크아웃",
]


# ────────────────────────────────────────────────
# 기존 NewsScanner 클래스 (완전 유지)
# ────────────────────────────────────────────────

class NewsScanner:
    def __init__(self):
        self._ticker_cache = {}

    def _load_tickers(self):
        if self._ticker_cache:
            return self._ticker_cache
        result = {}
        for days_ago in [0, 3, 7]:
            d = (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")
            for market in ["KOSPI", "KOSDAQ"]:
                try:
                    codes = stock.get_market_ticker_list(date=d, market=market)
                    for code in codes:
                        try:
                            name = stock.get_market_ticker_name(code)
                            result[name] = code
                        except Exception:
                            pass
                except Exception:
                    pass
            if result:
                break
        self._ticker_cache = result
        logger.info("종목명 캐시 로드: %d개", len(result))
        return result

    def _is_duplicate(self, new_title, existing_titles, threshold=0.7):
        for title in existing_titles:
            ratio = difflib.SequenceMatcher(None, new_title, title).ratio()
            if ratio > threshold:
                return True
        return False

    def _fetch_news(self):
        news_list = []
        seen_links = set()
        seen_titles = []

        for source_name, url in RSS_SOURCES:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:30]:
                    title   = entry.get("title", "").strip()
                    link    = entry.get("link", "").strip()
                    summary = entry.get("summary", "")
                    if link in seen_links:
                        continue
                    if self._is_duplicate(title, seen_titles):
                        continue
                    seen_links.add(link)
                    seen_titles.append(title)
                    news_list.append({
                        "source": source_name, "title": title,
                        "link": link, "summary": summary,
                        "text": title + " " + summary,
                    })
            except Exception as e:
                logger.debug("%s RSS 수집 실패: %s", source_name, str(e))

        logger.info("중복 제거 후 총 %d개 뉴스 수집", len(news_list))
        return news_list

    def _match_tickers(self, text, tickers):
        matched = []
        for name, code in tickers.items():
            if len(name) < 2:
                continue
            if name in text:
                matched.append((name, code))
        return matched

    def _classify(self, text):
        pos = [kw for kw in POSITIVE_KEYWORDS if kw in text]
        neg = [kw for kw in NEGATIVE_KEYWORDS if kw in text]
        return pos, neg

    def scan(self):
        tickers   = self._load_tickers()
        news_list = self._fetch_news()
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
                    stock_news[name] = {"code": code, "pos_kw": set(), "neg_kw": set(), "news": []}
                stock_news[name]["pos_kw"].update(pos_kw)
                stock_news[name]["neg_kw"].update(neg_kw)
                existing = [n["title"] for n in stock_news[name]["news"]]
                if news["title"] not in existing:
                    stock_news[name]["news"].append({
                        "title": news["title"], "link": news["link"], "source": news["source"],
                    })

        positive_results = []
        negative_results = []
        for name, data in stock_news.items():
            item = {"name": name, "code": data["code"], "news": data["news"][:3]}
            if data["pos_kw"]:
                positive_results.append({**item, "keywords": list(data["pos_kw"])})
            if data["neg_kw"]:
                negative_results.append({**item, "keywords": list(data["neg_kw"])})

        logger.info("긍정: %d종목, 부정: %d종목", len(positive_results), len(negative_results))
        return positive_results, negative_results


# ────────────────────────────────────────────────
# 새 함수 — bot.py 새 파이프라인용
# ────────────────────────────────────────────────

def fetch_all_news() -> list[dict]:
    """RSS 전체 수집 → [{title, link, source, text}, ...] (테마 분류용)"""
    ns = NewsScanner()
    return ns._fetch_news()


def classify_sentiment(text: str) -> float:
    """감성 점수 (-1.0 ~ +1.0)"""
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def build_stock_sentiment_map(news_items: list[dict]) -> dict[str, float]:
    """
    뉴스 제목에서 pykrx 전 종목명 매칭 → {종목코드: 평균감성점수}
    하드코딩 없이 pykrx 동적 로드
    """
    ns      = NewsScanner()
    tickers = ns._load_tickers()   # pykrx 전 종목 {이름: 코드}

    scores: dict[str, list[float]] = {}
    for item in news_items:
        title = item.get("title", "")
        sentiment = classify_sentiment(title)
        for name, code in tickers.items():
            if len(name) < 2:
                continue
            if name in title:
                scores.setdefault(code, []).append(sentiment)

    return {
        code: round(sum(vals) / len(vals), 3)
        for code, vals in scores.items()
    }
