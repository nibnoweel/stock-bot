"""
news_scanner.py
pykrx → FinanceDataReader 전환
종목 리스팅: fdr.StockListing('KOSPI' / 'KOSDAQ')
"""

import logging
import feedparser
import difflib
from datetime import datetime, timedelta
import FinanceDataReader as fdr

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
    # 5단계
    "상한가": 5, "어닝서프라이즈": 5, "FDA 승인": 5, "임상 성공": 5,
    "기술수출": 5, "대형 수주": 5, "최대 실적": 5, "사상 최대": 5,
    "턴어라운드": 5, "흑자전환": 5,
    # 4단계
    "신고가": 4, "급등": 4, "어닝": 4, "수주": 4, "계약 체결": 4,
    "기술이전": 4, "임상 3상": 4, "FDA": 4, "실적 개선": 4,
    "영업이익 증가": 4, "매출 증가": 4, "자사주 매입": 4, "자사주 소각": 4,
    "합병": 4, "인수": 4, "독점 공급": 4, "우선협상": 4, "양산": 4, "상장": 4,
    # 3단계
    "호실적": 3, "흑자": 3, "수출": 3, "특허": 3, "승인": 3, "허가": 3,
    "신제품": 3, "출시": 3, "개발 성공": 3, "MOU": 3, "협약": 3,
    "공급 계약": 3, "배당 증가": 3, "목표주가 상향": 3, "투자의견 상향": 3,
    "바이": 3, "매수": 3, "임상 2상": 3, "품목허가": 3,
    "수익성 개선": 3, "원가 절감": 3, "점유율 확대": 3,
    # 2단계
    "계약": 2, "협력": 2, "파트너십": 2, "투자 유치": 2, "증설": 2,
    "생산 확대": 2, "수요 증가": 2, "회복": 2, "반등": 2, "저평가": 2,
    "임상 1상": 2, "IND 승인": 2, "시장 확대": 2, "신규 고객": 2, "수주 잔고": 2,
    # 1단계
    "기대": 1, "전망": 1, "모색": 1, "추진": 1, "검토": 1,
    "논의": 1, "긍정적": 1, "상승세": 1, "관심": 1,
}

NEGATIVE_WEIGHTS: dict[str, int] = {
    # 5단계
    "하한가": 5, "상장폐지": 5, "파산": 5, "부도": 5, "횡령": 5,
    "배임": 5, "구속": 5, "기소": 5, "감사의견 거절": 5, "거래정지": 5, "워크아웃": 5,
    # 4단계
    "급락": 4, "어닝쇼크": 4, "적자전환": 4, "영업손실": 4, "대규모 손실": 4,
    "불성실공시": 4, "관리종목": 4, "감사의견": 4, "수사": 4, "검찰": 4,
    "과징금": 4, "유상증자": 4, "전환사채": 4, "신주인수권": 4,
    "리콜": 4, "결함": 4, "제재": 4, "계약 해지": 4, "수주 취소": 4,
    # 3단계
    "적자": 3, "손실": 3, "매출 감소": 3, "실적 악화": 3, "하향": 3,
    "목표주가 하향": 3, "투자의견 하향": 3, "매도": 3, "소송": 3, "사기": 3,
    "반품": 3, "취소": 3, "파기": 3, "임상 실패": 3, "FDA 거절": 3,
    "허가 취소": 3, "공급 차질": 3, "납품 지연": 3,
    "교환사채": 3, "무상감자": 3, "최대주주 변경": 3,
    # 2단계
    "우려": 2, "부진": 2, "둔화": 2, "감소": 2, "하락": 2, "악화": 2,
    "지연": 2, "불확실": 2, "위험": 2, "리스크": 2, "조정": 2,
    "대량 매도": 2, "블록딜": 2, "오버행": 2, "보호예수 해제": 2, "임원 매도": 2,
    # 1단계
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
# NewsScanner — pykrx → FDR 전환
# ────────────────────────────────────────────────

class NewsScanner:
    def __init__(self):
        self._ticker_cache = {}   # {종목명: 종목코드}

    def _load_tickers(self) -> dict[str, str]:
        """FDR로 KOSPI + KOSDAQ 전 종목 {이름: 코드} 로드"""
        if self._ticker_cache:
            return self._ticker_cache
        try:
            kospi  = fdr.StockListing("KOSPI")[["Code", "Name"]]
            kosdaq = fdr.StockListing("KOSDAQ")[["Code", "Name"]]
            df = (
                kospi._append(kosdaq)          # pandas 2.x 호환
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
                        "title": news["title"], "link": news["link"], "source": news["source"],
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