"""
scorer.py
종목 점수 시스템 + 스토캐스틱 지표
PDF 리포트의 점수 컬럼 (0~150점) 재현
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ────────────────────────────────────────────────
# 스토캐스틱 계산
# ────────────────────────────────────────────────

def calc_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    """
    Stochastic Oscillator (%K, %D) 계산
    df 컬럼 필수: high, low, close
    반환: df에 stoch_k, stoch_d 컬럼 추가
    """
    low_min  = df["low"].rolling(window=k).min()
    high_max = df["high"].rolling(window=k).max()

    df = df.copy()
    df["stoch_k"] = 100 * (df["close"] - low_min) / (high_max - low_min + 1e-9)
    df["stoch_d"] = df["stoch_k"].rolling(window=d).mean()
    return df


def stoch_signal(stoch_k: float, stoch_d: float) -> str:
    """스토캐스틱 신호 문자열 반환 (PDF 표기 방식)"""
    if stoch_k >= 80:
        return "과매수"
    elif stoch_k <= 20:
        return "과매도"
    elif stoch_k > stoch_d:
        return "상승"
    elif stoch_k < stoch_d:
        return "하락"
    else:
        return "중립"


# ────────────────────────────────────────────────
# 점수 계산 로직
# ────────────────────────────────────────────────

@dataclass
class StockScore:
    """종목 종합 점수 컨테이너"""
    code: str
    name: str

    # 세부 점수 (각 항목 최대치 합산 = 150점)
    rsi_score:        int = 0   # 최대 20점
    stoch_score:      int = 0   # 최대 20점
    macd_score:       int = 0   # 최대 15점
    foreign_score:    int = 0   # 최대 20점  (외인 수급)
    institution_score: int = 0  # 최대 20점  (기관 수급)
    news_score:       int = 0   # 최대 25점  (뉴스 감성)
    theme_score:      int = 0   # 최대 10점  (테마 이슈 일치)
    price_score:      int = 0   # 최대 20점  (가격 모멘텀)

    # 지표 raw 값 (리포트 표시용)
    rsi:              float = 0.0
    stoch_k_short:    float = 0.0   # 단기 스토캐스틱 K (5일)
    stoch_d_short:    float = 0.0
    stoch_k_mid:      float = 0.0   # 중기 스토캐스틱 K (20일)
    stoch_d_mid:      float = 0.0
    foreign_10d:      float = 0.0   # 외인 10일 누적 (만주)
    institution_10d:  float = 0.0   # 기관 10일 누적 (만주)
    news_sentiment:   float = 0.0   # -1 ~ +1

    # 신호 문자열
    stoch_short_signal: str = "-"
    stoch_mid_signal:   str = "-"

    @property
    def total(self) -> int:
        return (
            self.rsi_score + self.stoch_score + self.macd_score
            + self.foreign_score + self.institution_score
            + self.news_score + self.theme_score + self.price_score
        )

    def grade(self) -> str:
        t = self.total
        if t >= 120: return "★★★ 강매수"
        if t >= 90:  return "★★  매수"
        if t >= 60:  return "★   관심"
        if t >= 30:  return "    중립"
        return            "    회피"


# ────────────────────────────────────────────────
# 메인 채점 함수
# ────────────────────────────────────────────────

def score_stock(
    code: str,
    name: str,
    ohlcv: pd.DataFrame,          # columns: open high low close volume
    foreign_series: pd.Series,    # 외인 일별 순매수 (주)
    institution_series: pd.Series,# 기관 일별 순매수 (주)
    news_sentiment: float = 0.0,  # -1 ~ +1
    matched_themes: int = 0,      # 오늘 테마 이슈 매칭 수
) -> StockScore:
    """
    종목 종합 점수 계산
    ohlcv: 최소 60일 데이터 권장
    """
    s = StockScore(code=code, name=name)

    if len(ohlcv) < 20:
        return s   # 데이터 부족

    ohlcv = ohlcv.copy().reset_index(drop=True)
    close = ohlcv["close"]

    # ── 1. RSI (20점) ─────────────────────────────
    rsi = _calc_rsi(close, 14)
    s.rsi = rsi
    if 40 <= rsi <= 60:
        s.rsi_score = 20
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        s.rsi_score = 15
    elif 20 <= rsi < 30:
        s.rsi_score = 10   # 과매도 → 반등 기대
    elif rsi > 80:
        s.rsi_score = 5    # 과매수 → 위험
    else:
        s.rsi_score = 8

    # ── 2. 스토캐스틱 (20점) ─────────────────────
    df_stoch = calc_stochastic(ohlcv, k=5, d=3)   # 단기
    s.stoch_k_short = float(df_stoch["stoch_k"].iloc[-1])
    s.stoch_d_short = float(df_stoch["stoch_d"].iloc[-1])
    s.stoch_short_signal = stoch_signal(s.stoch_k_short, s.stoch_d_short)

    df_stoch_mid = calc_stochastic(ohlcv, k=20, d=5)  # 중기
    s.stoch_k_mid = float(df_stoch_mid["stoch_k"].iloc[-1])
    s.stoch_d_mid = float(df_stoch_mid["stoch_d"].iloc[-1])
    s.stoch_mid_signal = stoch_signal(s.stoch_k_mid, s.stoch_d_mid)

    # 단기 + 중기 모두 과매도 구간 골든크로스 → 최고점
    stoch_stk = s.stoch_k_short
    stoch_mtk = s.stoch_k_mid
    if stoch_stk <= 20 and stoch_mtk <= 30:
        s.stoch_score = 20
    elif stoch_stk <= 30:
        s.stoch_score = 15
    elif 30 < stoch_stk <= 50 and stoch_stk > s.stoch_d_short:
        s.stoch_score = 12
    elif stoch_stk >= 80:
        s.stoch_score = 3   # 과매수
    else:
        s.stoch_score = 8

    # ── 3. MACD (15점) ────────────────────────────
    macd_line, signal_line = _calc_macd(close)
    macd_hist = macd_line - signal_line
    if macd_hist > 0 and macd_line > 0:
        s.macd_score = 15
    elif macd_hist > 0:
        s.macd_score = 10
    elif macd_hist > -0.5:
        s.macd_score = 5
    else:
        s.macd_score = 0

    # ── 4. 외인 수급 (20점) ───────────────────────
    if len(foreign_series) >= 10:
        f10 = foreign_series.iloc[-10:].sum()
        s.foreign_10d = round(f10 / 10000, 1)   # 만주 단위
        if f10 > 500_000:
            s.foreign_score = 20
        elif f10 > 100_000:
            s.foreign_score = 15
        elif f10 > 0:
            s.foreign_score = 10
        elif f10 > -100_000:
            s.foreign_score = 5
        else:
            s.foreign_score = 0

    # ── 5. 기관 수급 (20점) ───────────────────────
    if len(institution_series) >= 10:
        i10 = institution_series.iloc[-10:].sum()
        s.institution_10d = round(i10 / 10000, 1)
        if i10 > 500_000:
            s.institution_score = 20
        elif i10 > 100_000:
            s.institution_score = 15
        elif i10 > 0:
            s.institution_score = 10
        elif i10 > -100_000:
            s.institution_score = 5
        else:
            s.institution_score = 0

    # ── 6. 뉴스 감성 (25점) ───────────────────────
    s.news_sentiment = news_sentiment
    if news_sentiment >= 0.6:
        s.news_score = 25
    elif news_sentiment >= 0.3:
        s.news_score = 18
    elif news_sentiment >= 0.0:
        s.news_score = 10
    elif news_sentiment >= -0.3:
        s.news_score = 5
    else:
        s.news_score = 0

    # ── 7. 테마 이슈 (10점) ───────────────────────
    s.theme_score = min(matched_themes * 5, 10)

    # ── 8. 가격 모멘텀 (20점) ────────────────────
    if len(close) >= 20:
        ret_5d  = (close.iloc[-1] / close.iloc[-6]  - 1) * 100
        ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100
        mom = ret_5d * 0.4 + ret_20d * 0.6
        if mom >= 5:
            s.price_score = 20
        elif mom >= 2:
            s.price_score = 15
        elif mom >= 0:
            s.price_score = 10
        elif mom >= -2:
            s.price_score = 5
        else:
            s.price_score = 0

    return s


# ────────────────────────────────────────────────
# 내부 보조 함수
# ────────────────────────────────────────────────

def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.isna().all() else 50.0


def _calc_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    ema_fast   = close.ewm(span=fast, adjust=False).mean()
    ema_slow   = close.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


# ────────────────────────────────────────────────
# 편의 함수: 리스트 일괄 채점 후 정렬
# ────────────────────────────────────────────────

def rank_stocks(scores: list[StockScore]) -> list[StockScore]:
    """점수 내림차순 정렬"""
    return sorted(scores, key=lambda s: s.total, reverse=True)
