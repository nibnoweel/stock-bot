"""
scanner.py
pykrx → FinanceDataReader 전환
OHLCV 컬럼: Open, High, Low, Close, Volume (영문 대문자)
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import FinanceDataReader as fdr
import watchlist

from scorer import StockScore, score_from_scan, rank_scores
from supply_scanner import fetch_investor_data
from sector_theme import get_sector, match_stock_themes, ThemeIssue

logger = logging.getLogger(__name__)


class StockScanner:
    def __init__(self):
        self.markets = ["KOSPI", "KOSDAQ"]

    # ── 공휴일 / 거래일 (기존 완전 유지) ──────────
    KR_HOLIDAYS = {
        "20250101", "20250128", "20250129", "20250130",
        "20250301", "20250505", "20250506", "20250606",
        "20250815", "20251003", "20251006", "20251007", "20251008",
        "20251009", "20251225",
        "20260101", "20260216", "20260217", "20260218",
        "20260301", "20260505", "20260606",
        "20260815", "20260924", "20260925", "20260928",
        "20261009", "20261225",
    }

    def _is_holiday(self, d: datetime) -> bool:
        if d.weekday() >= 5:
            return True
        return d.strftime("%Y%m%d") in self.KR_HOLIDAYS

    def _is_maintenance_time(self) -> bool:
        return datetime.now().hour < 6

    def _is_today_trading_day(self) -> bool:
        return not self._is_holiday(datetime.now())

    def _latest_trading_day(self) -> str:
        now = datetime.now()
        if not self._is_holiday(now) and now.hour >= 16:
            return now.strftime("%Y%m%d")
        for i in range(1, 30):
            d = now - timedelta(days=i)
            if not self._is_holiday(d):
                return d.strftime("%Y%m%d")
        return (now - timedelta(days=1)).strftime("%Y%m%d")

    # ── OHLCV — FDR 전환 ─────────────────────────
    def _get_ohlcv(self, code: str, end_date: str, days: int = 300) -> pd.DataFrame:
        """
        FDR DataReader → 컬럼 Open/High/Low/Close/Volume
        pykrx 호환을 위해 한글 컬럼명으로 rename
        """
        end_dt   = datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=days + 60)
        df = fdr.DataReader(
            code,
            start_dt.strftime("%Y-%m-%d"),
            end_dt.strftime("%Y-%m-%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # FDR 컬럼 → 기존 pykrx 컬럼명으로 rename (내부 로직 재사용)
        rename_map = {
            "Open":   "시가",
            "High":   "고가",
            "Low":    "저가",
            "Close":  "종가",
            "Volume": "거래량",
        }
        df = df.rename(columns=rename_map)

        # 필요 컬럼만 추출
        needed = ["시가", "고가", "저가", "종가", "거래량"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            logger.debug("%s 컬럼 누락: %s", code, missing)
            return pd.DataFrame()

        return df[needed].dropna()

    # ── 전 종목 티커 — FDR 전환 ──────────────────
    def _get_all_tickers(self, trading_day: str) -> list[tuple[str, str]]:
        """FDR StockListing으로 KOSPI + KOSDAQ 전 종목"""
        tickers = []
        for market in self.markets:
            try:
                df = fdr.StockListing(market)
                df["Code"] = df["Code"].astype(str).str.zfill(6)
                for _, row in df.iterrows():
                    tickers.append((str(row["Code"]), str(row["Name"])))
            except Exception as e:
                logger.warning("%s 티커 로딩 실패: %s", market, e)
        logger.info("전 종목 로드: %d개", len(tickers))
        return tickers

    # ── 캔들 / RSI / MACD (기존 로직 완전 유지) ──
    @staticmethod
    def _candle_parts(row):
        open_ = row["시가"]; high  = row["고가"]
        low   = row["저가"]; close = row["종가"]
        body_top = max(open_, close); body_bot = min(open_, close)
        return high - body_top, body_top - body_bot, body_bot - low

    @staticmethod
    def _calc_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        return 100 - (100 / (1 + rs))

    def _detect_divergence(self, df, rsi):
        if len(df) < 20: return "없음"
        recent = df.iloc[-20:]; recent_rsi = rsi.iloc[-20:]
        current_rsi = rsi.iloc[-1]
        if current_rsi < 30:
            lows = recent["저가"].values; rsi_vals = recent_rsi.values
            for i in range(len(lows) - 5, 0, -1):
                if lows[-1] < lows[i] and 5 <= rsi_vals[-1] - rsi_vals[i] <= 10:
                    return "상승"
        if current_rsi > 70:
            highs = recent["고가"].values; rsi_vals = recent_rsi.values
            for i in range(len(highs) - 5, 0, -1):
                if highs[-1] > highs[i] and 5 <= rsi_vals[i] - rsi_vals[-1] <= 10:
                    return "하락"
        return "없음"

    @staticmethod
    def _calc_macd(closes):
        ema12  = closes.ewm(span=12, adjust=False).mean()
        ema26  = closes.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal, macd - signal

    @staticmethod
    def _detect_golden_cross(macd, signal):
        if len(macd) < 3: return False
        for i in range(-3, 0):
            if macd.iloc[i-1] < signal.iloc[i-1] and macd.iloc[i] > signal.iloc[i]:
                return True
        return False

    # ── 조건 검사 (기존 로직 완전 유지) ─────────
    def _check_conditions(self, code, name, end_date):
        try:
            df = self._get_ohlcv(code, end_date, days=90)
            if df is None or len(df) < 70:
                return None

            df = df.reset_index(drop=True) if df.index.name else df
            idx = len(df) - 1   # 오늘(마지막 봉)

            today     = df.iloc[idx]
            yesterday = df.iloc[idx - 1]
            close = today["종가"]

            # 등락률 (전일 종가 대비)
            if yesterday["종가"] == 0:
                return None
            change_pct = (close - yesterday["종가"]) / yesterday["종가"] * 100

            # ── 눌림목 필터 ──────────────────────
            # 1. 선행 상승: 최근 20일 내 +15%
            window = df.iloc[idx - 20:idx + 1]
            win_low  = window["종가"].min()
            win_high = window["고가"].max()
            if win_low <= 0:
                return None
            if (win_high - win_low) / win_low * 100 < 15:
                return None

            # 2. 조정: 고점 대비 -5 ~ -15%
            drop_pct = (close - win_high) / win_high * 100
            if not (-15 <= drop_pct <= -5):
                return None

            # 3. 20일선 지지 ±3%
            ma20 = df["종가"].iloc[idx - 20:idx].mean()
            if ma20 <= 0:
                return None
            if abs((close - ma20) / ma20 * 100) > 3:
                return None

            # 4. 60일선 위
            ma60 = df["종가"].iloc[idx - 60:idx].mean()
            if ma60 <= 0 or close < ma60:
                return None

            # 5. 반등: 양봉 또는 아랫꼬리
            upper_tail, body, lower_tail = self._candle_parts(today)
            is_bullish    = close > today["시가"]
            has_long_tail = lower_tail > body and lower_tail > upper_tail
            if not (is_bullish or has_long_tail):
                return None

            rsi_series  = self._calc_rsi(df["종가"])
            current_rsi = round(float(rsi_series.iloc[-1]), 1)
            divergence  = self._detect_divergence(df, rsi_series)
            rsi_status  = "과매수" if current_rsi >= 70 else ("과매도" if current_rsi <= 30 else "중립")

            macd_line, signal_line, hist = self._calc_macd(df["종가"])
            golden_cross  = self._detect_golden_cross(macd_line, signal_line)
            hist_positive = bool(hist.iloc[-1] > 0 and hist.iloc[-2] <= 0)

            return {
                "code": code, "name": name,
                "close": int(close),
                "change_pct": change_pct,        # 전일 대비 등락률
                "drop_from_high": drop_pct,      # 고점 대비 조정폭
                "ma20_gap": (close - ma20) / ma20 * 100,
                "theme": watchlist.code_to_theme().get(code, "-"),
                "rsi": current_rsi, "rsi_status": rsi_status, "divergence": divergence,
                "golden_cross": golden_cross, "hist_positive": hist_positive,
                "_df": df,
            }
        except Exception as e:
            logger.debug("%s 조건 검사 오류: %s", code, e)
            return None

    # ── scan() — watchlist 눌림목 스캔 ────────────
    def scan(self) -> list:
        if self._is_maintenance_time():
            logger.warning("KRX 서버 점검 시간 (00:00~06:00) — 스캔 불가")
            return []

        trading_day = self._latest_trading_day()
        tickers     = list(watchlist.code_to_name().items())
        logger.info("watchlist %d개 종목 스캔 시작 (기준일: %s)", len(tickers), trading_day)

        results = []
        for code, name in tickers:
            result = self._check_conditions(code, name, trading_day)
            if result:
                result.pop("_df", None)
                results.append(result)
                logger.info("눌림목 포착: %s (%s)", name, code)

        logger.info("스캔 완료 - %d개 종목 발견", len(results))
        return results

    # ── 신규 scan_with_score() ───────────────────
    def scan_with_score(
        self,
        themes: list[ThemeIssue],
        news_sentiment_map: dict[str, float],
    ) -> list[StockScore]:
        if self._is_maintenance_time():
            logger.warning("KRX 서버 점검 시간 — 스캔 불가")
            return []

        trading_day = self._latest_trading_day()
        tickers     = self._get_all_tickers(trading_day)
        logger.info("점수 스캔 시작: %d종목 (기준일: %s)", len(tickers), trading_day)

        scores: list[StockScore] = []
        for i, (code, name) in enumerate(tickers):
            if i % 100 == 0:
                logger.info("... %d / %d", i, len(tickers))
            result = self._check_conditions(code, name, trading_day)
            if not result:
                continue

            df_ohlcv = result.pop("_df")
            supply   = fetch_investor_data(code, days=10)
            s = score_from_scan(
                scan_result=result,
                df_ohlcv=df_ohlcv,
                foreign_10d=supply["foreign_10d"],
                institution_10d=supply["institution_10d"],
                news_sentiment=news_sentiment_map.get(code, 0.0),
                matched_themes=match_stock_themes(code, themes),
                sector=get_sector(code),
            )
            scores.append(s)
            logger.info("조건 만족: %s (%s) — %d점", name, code, s.total)

        logger.info("점수 스캔 완료: %d종목", len(scores))
        return rank_scores(scores)