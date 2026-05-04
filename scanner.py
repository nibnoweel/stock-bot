"""
scanner.py  (업그레이드 버전)
KOSPI / KOSDAQ 전 종목 스캔
기존 RSI + MACD → + 스토캐스틱 + 외인/기관 수급 + 종목 점수 통합
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import FinanceDataReader as fdr

from scorer import StockScore, score_stock, rank_stocks
from supply_scanner import fetch_investor_data
from sector_theme import get_sector, match_stock_themes, ThemeIssue

logger = logging.getLogger(__name__)

# 스캔 대상 시가총액 하한 (억원) — 너무 작은 종목 제외
MIN_MARKET_CAP = 500
# 일일 최소 거래대금 (억원)
MIN_TRADING_VALUE = 10


# ────────────────────────────────────────────────
# 전 종목 코드 수집
# ────────────────────────────────────────────────

def get_all_codes() -> pd.DataFrame:
    """
    KOSPI + KOSDAQ 전 종목 코드/이름 반환
    columns: Code, Name, Market
    """
    kospi  = fdr.StockListing("KOSPI")[["Code", "Name"]].assign(Market="KOSPI")
    kosdaq = fdr.StockListing("KOSDAQ")[["Code", "Name"]].assign(Market="KOSDAQ")
    return pd.concat([kospi, kosdaq], ignore_index=True)


# ────────────────────────────────────────────────
# 단일 종목 OHLCV
# ────────────────────────────────────────────────

def fetch_ohlcv(code: str, days: int = 90) -> pd.DataFrame:
    """
    단일 종목 OHLCV (open, high, low, close, volume) 반환
    최근 days 거래일 데이터
    """
    end   = datetime.today()
    start = end - timedelta(days=days * 2)   # 주말 여유분
    df = fdr.DataReader(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns=str.lower)
    needed = {"open", "high", "low", "close", "volume"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()

    return df[list(needed)].dropna().tail(days)


# ────────────────────────────────────────────────
# RSI 계산 (기존 호환)
# ────────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else 50.0


# ────────────────────────────────────────────────
# RSI 다이버전스 감지 (기존 유지)
# ────────────────────────────────────────────────

def detect_rsi_divergence(close: pd.Series, rsi_series: pd.Series) -> Optional[str]:
    """
    강세 / 약세 다이버전스 감지
    반환: "bullish" | "bearish" | None
    """
    if len(close) < 20:
        return None

    price_low1  = close.iloc[-10:].min()
    price_low2  = close.iloc[-20:-10].min()
    rsi_low1    = rsi_series.iloc[-10:].min()
    rsi_low2    = rsi_series.iloc[-20:-10].min()

    # 강세 다이버전스: 가격 저점↓ / RSI 저점↑
    if price_low1 < price_low2 and rsi_low1 > rsi_low2:
        return "bullish"

    price_high1 = close.iloc[-10:].max()
    price_high2 = close.iloc[-20:-10].max()
    rsi_high1   = rsi_series.iloc[-10:].max()
    rsi_high2   = rsi_series.iloc[-20:-10].max()

    # 약세 다이버전스: 가격 고점↑ / RSI 고점↓
    if price_high1 > price_high2 and rsi_high1 < rsi_high2:
        return "bearish"

    return None


# ────────────────────────────────────────────────
# MACD 계산 (기존 유지)
# ────────────────────────────────────────────────

def calc_macd(close: pd.Series) -> dict:
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return {
        "macd":   float(macd.iloc[-1])   if pd.notna(macd.iloc[-1])   else 0.0,
        "signal": float(signal.iloc[-1]) if pd.notna(signal.iloc[-1]) else 0.0,
        "hist":   float(hist.iloc[-1])   if pd.notna(hist.iloc[-1])   else 0.0,
    }


# ────────────────────────────────────────────────
# 종합 스캔 함수
# ────────────────────────────────────────────────

def scan_stocks(
    themes: list[ThemeIssue],
    news_sentiment_map: dict[str, float],   # code → 감성 점수
    top_n: int = 30,
    max_codes: int = 500,
    delay: float = 0.3,
) -> list[StockScore]:
    """
    전 종목 스캔 후 상위 top_n 종목 점수 리스트 반환
    themes: sector_theme.classify_news_to_themes() 결과
    news_sentiment_map: news_scanner에서 종목별 감성 점수
    """
    all_codes = get_all_codes()

    # 시총 필터링 (pykrx 또는 FDR 제공 시)
    try:
        all_codes = _filter_by_market_cap(all_codes)
    except Exception:
        pass

    # 상위 max_codes 종목만 스캔 (시간 절약)
    sample = all_codes.head(max_codes)

    scores: list[StockScore] = []

    for _, row in sample.iterrows():
        code = str(row["Code"]).zfill(6)
        name = str(row["Name"])

        try:
            # OHLCV
            ohlcv = fetch_ohlcv(code, days=90)
            if ohlcv.empty or len(ohlcv) < 20:
                continue

            # 수급
            supply = fetch_investor_data(code, days=10)

            # 뉴스 감성
            sentiment = news_sentiment_map.get(code, 0.0)

            # 테마 매칭 수
            theme_match = match_stock_themes(code, themes)

            # 종합 점수
            s = score_stock(
                code=code,
                name=name,
                ohlcv=ohlcv,
                foreign_series=supply["foreign"],
                institution_series=supply["institution"],
                news_sentiment=sentiment,
                matched_themes=theme_match,
            )
            scores.append(s)

            time.sleep(delay)

        except Exception as e:
            logger.debug(f"[scan] {code} {name} 건너뜀: {e}")

    logger.info(f"스캔 완료: {len(scores)}종목 / 상위 {top_n}개 추출")
    return rank_stocks(scores)[:top_n]


# ────────────────────────────────────────────────
# 내부: 시가총액 필터
# ────────────────────────────────────────────────

def _filter_by_market_cap(df: pd.DataFrame) -> pd.DataFrame:
    """
    pykrx로 시가총액 정보 가져와 MIN_MARKET_CAP 억원 이상만 유지
    실패하면 원본 그대로 반환
    """
    from pykrx import stock as krx
    today = datetime.today().strftime("%Y%m%d")

    cap_data = []
    try:
        kospi_cap  = krx.get_market_cap_by_ticker(today, market="KOSPI")
        kosdaq_cap = krx.get_market_cap_by_ticker(today, market="KOSDAQ")
        cap_all = pd.concat([kospi_cap, kosdaq_cap])
        cap_all["cap_억"] = cap_all["시가총액"] / 1e8

        codes_ok = set(cap_all[cap_all["cap_억"] >= MIN_MARKET_CAP].index.astype(str).str.zfill(6))
        df["Code"] = df["Code"].astype(str).str.zfill(6)
        return df[df["Code"].isin(codes_ok)].reset_index(drop=True)
    except Exception as e:
        logger.debug(f"시가총액 필터 실패: {e}")
        return df
