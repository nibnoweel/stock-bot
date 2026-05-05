"""
scorer.py — 종목 점수 시스템 + 스토캐스틱
기존 StockScanner._check_conditions() 결과(dict)를 받아 점수 계산
최대 150점
"""

import pandas as pd
from dataclasses import dataclass, field


# ────────────────────────────────────────────────
# 스토캐스틱 계산
# ────────────────────────────────────────────────

def calc_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    """
    df 필수 컬럼: 고가, 저가, 종가  (pykrx OHLCV 컬럼명 그대로)
    반환: stoch_k, stoch_d 컬럼 추가된 df
    """
    df = df.copy()
    low_min  = df["저가"].rolling(window=k).min()
    high_max = df["고가"].rolling(window=k).max()
    df["stoch_k"] = 100 * (df["종가"] - low_min) / (high_max - low_min + 1e-9)
    df["stoch_d"] = df["stoch_k"].rolling(window=d).mean()
    return df


def stoch_signal(k: float, d: float) -> str:
    """스토캐스틱 신호 문자열 (PDF 표기용)"""
    if k >= 80:             return "과매수"
    if k <= 20:             return "과매도"
    if k > d:               return "상승"
    if k < d:               return "하락"
    return                         "중립"


# ────────────────────────────────────────────────
# 점수 컨테이너
# ────────────────────────────────────────────────

@dataclass
class StockScore:
    code: str
    name: str

    # 세부 점수 (합계 최대 150)
    rsi_score:         int = 0   # 20점
    stoch_score:       int = 0   # 20점
    macd_score:        int = 0   # 15점
    foreign_score:     int = 0   # 20점
    institution_score: int = 0   # 20점
    news_score:        int = 0   # 25점
    theme_score:       int = 0   # 10점
    price_score:       int = 0   # 20점

    # raw 지표값 (리포트 표시용)
    rsi:              float = 0.0
    stoch_k_short:    float = 0.0
    stoch_d_short:    float = 0.0
    stoch_k_mid:      float = 0.0
    stoch_d_mid:      float = 0.0
    foreign_10d:      float = 0.0   # 만주
    institution_10d:  float = 0.0   # 만주
    news_sentiment:   float = 0.0
    close:            int   = 0
    change_pct:       float = 0.0
    volume_ratio:     float = 0.0
    ma200_gap:        float = 0.0
    market_cap:       float = 0.0   # 시가총액 (억원), 신규 추가
    divergence:       str   = "없음"
    golden_cross:     bool  = False
    hist_positive:    bool  = False

    stoch_short_signal: str = "-"
    stoch_mid_signal:   str = "-"
    sector: str = "기타"

    # 3스토 과열 신호
    triple_overbought:  bool = False   # 단기+중기 스토 + RSI 동시 과매수
    triple_oversold:    bool = False   # 단기+중기 스토 + RSI 동시 과매도 (매수 기회)

    @property
    def total(self) -> int:
        return (self.rsi_score + self.stoch_score + self.macd_score
                + self.foreign_score + self.institution_score
                + self.news_score + self.theme_score + self.price_score)
    @property
    def grade(self) -> str:
        t = self.total
        if t >= 120: return "★★★ 강매수"
        if t >= 90:  return "★★  매수"
        if t >= 60:  return "★   관심"
        if t >= 30:  return "    중립"
        return              "    회피"

    @property
    def cap_label(self) -> str:
        """시총 구간 레이블"""
        c = self.market_cap
        if c <= 0:       return "-"
        if c >= 100000:  return "대형 (10조↑)"
        if c >= 10000:   return "중형 (1~10조)"
        if c >= 3000:    return "중소형 (3천억~1조)"
        return                  "소형 (3천억↓)"

    @property
    def stoch_alert(self) -> str:
        """3스토 신호 레이블 (리포트/알림용)"""
        if self.triple_overbought: return "🔴 3스토과매수"
        if self.triple_oversold:   return "🟢 3스토과매도"
        return ""
# ────────────────────────────────────────────────
# 채점 함수
# ────────────────────────────────────────────────

def score_from_scan(
    scan_result: dict,          # StockScanner._check_conditions() 반환값
    df_ohlcv: pd.DataFrame,     # pykrx OHLCV (고가/저가/종가 컬럼)
    foreign_10d: float = 0.0,   # 외인 10일 순매수 (만주)
    institution_10d: float = 0.0,
    news_sentiment: float = 0.0,
    matched_themes: int = 0,
    sector: str = "기타",
) -> StockScore:
    """
    기존 scan_result dict + OHLCV df → StockScore
    scan_result 키: code, name, close, change_pct, volume_ratio,
                    ma200_gap, rsi, rsi_status, divergence,
                    golden_cross, hist_positive
    """
    s = StockScore(
        code=scan_result["code"],
        name=scan_result["name"],
        rsi=scan_result.get("rsi", 50.0),
        close=scan_result.get("close", 0),
        change_pct=scan_result.get("change_pct", 0.0),
        volume_ratio=scan_result.get("volume_ratio", 0.0),
        ma200_gap=scan_result.get("ma200_gap", 0.0),
        divergence=scan_result.get("divergence", "없음"),
        golden_cross=scan_result.get("golden_cross", False),
        hist_positive=scan_result.get("hist_positive", False),
        foreign_10d=foreign_10d,
        institution_10d=institution_10d,
        news_sentiment=news_sentiment,
        sector=sector,
    )

    rsi = s.rsi

    # ── 1. RSI (20점) ─────────────────────────
    if 40 <= rsi <= 60:   s.rsi_score = 20
    elif 30 <= rsi < 40 or 60 < rsi <= 70: s.rsi_score = 15
    elif 20 <= rsi < 30:  s.rsi_score = 10
    elif rsi > 80:        s.rsi_score = 5
    else:                 s.rsi_score = 8

    # 다이버전스 보너스
    if s.divergence == "상승":
        s.rsi_score = min(s.rsi_score + 5, 20)

    # ── 2. 스토캐스틱 (20점) ─────────────────
    if len(df_ohlcv) >= 10:
        df_s = calc_stochastic(df_ohlcv, k=5, d=3)
        s.stoch_k_short = float(df_s["stoch_k"].iloc[-1])
        s.stoch_d_short = float(df_s["stoch_d"].iloc[-1])
        s.stoch_short_signal = stoch_signal(s.stoch_k_short, s.stoch_d_short)

    if len(df_ohlcv) >= 25:
        df_m = calc_stochastic(df_ohlcv, k=20, d=5)
        s.stoch_k_mid = float(df_m["stoch_k"].iloc[-1])
        s.stoch_d_mid = float(df_m["stoch_d"].iloc[-1])
        s.stoch_mid_signal = stoch_signal(s.stoch_k_mid, s.stoch_d_mid)

    sk = s.stoch_k_short
    mk = s.stoch_k_mid
    if sk <= 20 and mk <= 30:   s.stoch_score = 20
    elif sk <= 30:              s.stoch_score = 15
    elif 30 < sk <= 50 and sk > s.stoch_d_short: s.stoch_score = 12
    elif sk >= 80:              s.stoch_score = 3
    else:                       s.stoch_score = 8

    # 3스토 과열/침체 판정
    s.triple_overbought = (sk >= 80 and mk >= 80 and s.rsi >= 70)
    s.triple_oversold   = (sk <= 20 and mk <= 20 and s.rsi <= 30)

    # ── 3. MACD (15점) ────────────────────────
    if s.golden_cross and s.hist_positive: s.macd_score = 15
    elif s.golden_cross:                   s.macd_score = 10
    elif s.hist_positive:                  s.macd_score = 8
    else:                                  s.macd_score = 0

    # ── 4. 외인 수급 (20점) ───────────────────
    f = foreign_10d
    if f > 50:    s.foreign_score = 20
    elif f > 10:  s.foreign_score = 15
    elif f > 0:   s.foreign_score = 10
    elif f > -10: s.foreign_score = 5
    else:         s.foreign_score = 0

    # ── 5. 기관 수급 (20점) ───────────────────
    i = institution_10d
    if i > 50:    s.institution_score = 20
    elif i > 10:  s.institution_score = 15
    elif i > 0:   s.institution_score = 10
    elif i > -10: s.institution_score = 5
    else:         s.institution_score = 0

    # ── 6. 뉴스 감성 (25점) ───────────────────
    ns = news_sentiment
    if ns >= 0.6:   s.news_score = 25
    elif ns >= 0.3: s.news_score = 18
    elif ns >= 0.0: s.news_score = 10
    elif ns >= -0.3:s.news_score = 5
    else:           s.news_score = 0

    # ── 7. 테마 이슈 (10점) ───────────────────
    s.theme_score = min(matched_themes * 5, 10)

    # ── 8. 가격 모멘텀 (20점) ─────────────────
    # 기존 필터 통과 = 거래량 2배 + 2% 상승 → 기본 점수 보장
    chg = s.change_pct
    vr  = s.volume_ratio
    if chg >= 5 and vr >= 3:    s.price_score = 20
    elif chg >= 3 and vr >= 2:  s.price_score = 15
    elif chg >= 2:              s.price_score = 10
    else:                       s.price_score = 5

    return s


def rank_scores(scores: list[StockScore]) -> list[StockScore]:
    return sorted(scores, key=lambda s: s.total, reverse=True)
