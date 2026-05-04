"""
KRX 주식 스캐너
- 기존 4가지 조건 필터
- RSI 다이버전스 (상승/하락) 참고용 표시
- MACD 골든크로스 / 히스토그램 참고용 표시
- KRX 서버 점검 시간대 (자정~06:00) 안내
"""

import logging
import logging.handlers
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

logger = logging.getLogger(__name__)

# pykrx 내부 로그 충돌 방지
logging.getLogger("pykrx").setLevel(logging.ERROR)
root_logger = logging.getLogger("root")
if not any(isinstance(h, logging.NullHandler) for h in root_logger.handlers):
    root_logger.addHandler(logging.NullHandler())


class StockScanner:
    def __init__(self):
        self.markets = ["KOSPI", "KOSDAQ"]

    # ────────────────────────────────────────────
    # 한국 공휴일 목록 (연도별)
    # ────────────────────────────────────────────
    KR_HOLIDAYS = {
        # 2025
        "20250101", "20250128", "20250129", "20250130",
        "20250301", "20250505", "20250506", "20250606",
        "20250815", "20251003", "20251006", "20251007", "20251008",
        "20251009", "20251225",
        # 2026
        "20260101", "20260216", "20260217", "20260218",
        "20260301", "20260505", "20260606",
        "20260815", "20260924", "20260925", "20260928",
        "20261009", "20261225",
    }

    def _is_holiday(self, d: datetime) -> bool:
        """주말 또는 공휴일 여부"""
        if d.weekday() >= 5:
            return True
        return d.strftime("%Y%m%d") in self.KR_HOLIDAYS

    # ────────────────────────────────────────────
    # KRX 서버 점검 시간 체크
    # ────────────────────────────────────────────
    def _is_maintenance_time(self) -> bool:
        """KRX 서버 점검 시간 (00:00 ~ 06:00) 여부"""
        return datetime.now().hour < 6

    # ────────────────────────────────────────────
    # 오늘이 거래일인지 확인
    # ────────────────────────────────────────────
    def _is_today_trading_day(self) -> bool:
        """공휴일 목록 기반으로 오늘이 거래일인지 판단 (장 시간 무관)"""
        return not self._is_holiday(datetime.now())

    # ────────────────────────────────────────────
    # 최근 거래일 찾기
    # ────────────────────────────────────────────
    def _latest_trading_day(self) -> str:
        """
        가장 최근 거래일 반환.
        - 장 마감 후(16:00~): 오늘이 거래일이면 오늘
        - 장 시작 전 / 장중: 가장 최근 과거 거래일
        """
        now = datetime.now()

        # 장 마감 후면 오늘 데이터 사용
        if not self._is_holiday(now) and now.hour >= 16:
            logger.info("기준 거래일: %s (당일 마감 후)", now.strftime("%Y%m%d"))
            return now.strftime("%Y%m%d")

        # 그 외: 어제부터 거슬러 올라가며 가장 최근 거래일 반환
        for i in range(1, 30):
            d = now - timedelta(days=i)
            if not self._is_holiday(d):
                logger.info("기준 거래일: %s", d.strftime("%Y%m%d"))
                return d.strftime("%Y%m%d")

        # fallback
        return (now - timedelta(days=1)).strftime("%Y%m%d")

    def _date_n_days_ago(self, n: int) -> str:
        return (datetime.now() - timedelta(days=n)).strftime("%Y%m%d")

    # ────────────────────────────────────────────
    # OHLCV 조회
    # ────────────────────────────────────────────
    def _get_ohlcv(self, code: str, end_date: str, days: int = 300) -> pd.DataFrame:
        start = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days + 60)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end_date, code)
        return df

    # ────────────────────────────────────────────
    # 캔들 요소
    # ────────────────────────────────────────────
    @staticmethod
    def _candle_parts(row: pd.Series):
        open_ = row["시가"]
        high  = row["고가"]
        low   = row["저가"]
        close = row["종가"]
        body_top = max(open_, close)
        body_bot = min(open_, close)
        return high - body_top, body_top - body_bot, body_bot - low

    # ────────────────────────────────────────────
    # RSI 계산
    # ────────────────────────────────────────────
    @staticmethod
    def _calc_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        return 100 - (100 / (1 + rs))

    # ────────────────────────────────────────────
    # RSI 다이버전스 감지
    # ────────────────────────────────────────────
    def _detect_divergence(self, df: pd.DataFrame, rsi: pd.Series) -> str:
        if len(df) < 20:
            return "없음"
        recent     = df.iloc[-20:]
        recent_rsi = rsi.iloc[-20:]
        current_rsi = rsi.iloc[-1]

        # 상승다이버전스 (과매도 구간)
        if current_rsi < 30:
            lows     = recent["저가"].values
            rsi_vals = recent_rsi.values
            for i in range(len(lows) - 5, 0, -1):
                if lows[-1] < lows[i]:
                    rsi_diff = rsi_vals[-1] - rsi_vals[i]
                    if 5 <= rsi_diff <= 10:
                        return "상승"

        # 하락다이버전스 (과매수 구간)
        if current_rsi > 70:
            highs    = recent["고가"].values
            rsi_vals = recent_rsi.values
            for i in range(len(highs) - 5, 0, -1):
                if highs[-1] > highs[i]:
                    rsi_diff = rsi_vals[i] - rsi_vals[-1]
                    if 5 <= rsi_diff <= 10:
                        return "하락"

        return "없음"

    # ────────────────────────────────────────────
    # MACD 계산
    # ────────────────────────────────────────────
    @staticmethod
    def _calc_macd(closes: pd.Series):
        ema12  = closes.ewm(span=12, adjust=False).mean()
        ema26  = closes.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist   = macd - signal
        return macd, signal, hist

    @staticmethod
    def _detect_golden_cross(macd: pd.Series, signal: pd.Series) -> bool:
        if len(macd) < 3:
            return False
        for i in range(-3, 0):
            if macd.iloc[i-1] < signal.iloc[i-1] and macd.iloc[i] > signal.iloc[i]:
                return True
        return False

    # ────────────────────────────────────────────
    # 조건 검사
    # ────────────────────────────────────────────
    def _check_conditions(self, code: str, name: str, end_date: str):
        try:
            df = self._get_ohlcv(code, end_date, days=300)
            if len(df) < 202:
                return None

            today     = df.iloc[-1]
            yesterday = df.iloc[-2]

            # 필터 1: 거래량 2배
            if yesterday["거래량"] == 0:
                return None
            volume_ratio = today["거래량"] / yesterday["거래량"]
            if volume_ratio < 2.0:
                return None

            # 필터 2: 2% 이상 상승
            if yesterday["종가"] == 0:
                return None
            change_pct = (today["종가"] - yesterday["종가"]) / yesterday["종가"] * 100
            if change_pct < 2.0:
                return None

            # 필터 3: 200일선 5일 연속
            if len(df) < 205:
                return None
            above_count = 0
            ma200_gap   = 0.0
            for i in range(1, 6):
                idx = len(df) - i
                if idx < 200:
                    return None
                ma200 = df["종가"].iloc[idx - 200:idx].mean()
                gap   = (df["종가"].iloc[idx] - ma200) / ma200 * 100
                if gap >= 3.0:
                    above_count += 1
                if i == 1:
                    ma200_gap = gap
            if above_count < 5:
                return None

            # 필터 4: 캔들 패턴
            upper_tail, body, lower_tail = self._candle_parts(today)
            if not (upper_tail < body and upper_tail < lower_tail):
                return None

            # 참고용: RSI
            rsi_series  = self._calc_rsi(df["종가"])
            current_rsi = round(float(rsi_series.iloc[-1]), 1)
            divergence  = self._detect_divergence(df, rsi_series)
            if current_rsi >= 70:
                rsi_status = "과매수"
            elif current_rsi <= 30:
                rsi_status = "과매도"
            else:
                rsi_status = "중립"

            # 참고용: MACD
            macd_line, signal_line, hist = self._calc_macd(df["종가"])
            golden_cross  = self._detect_golden_cross(macd_line, signal_line)
            hist_positive = bool(hist.iloc[-1] > 0 and hist.iloc[-2] <= 0)

            return {
                "code":          code,
                "name":          name,
                "close":         int(today["종가"]),
                "change_pct":    change_pct,
                "volume_ratio":  volume_ratio,
                "ma200_gap":     ma200_gap,
                "upper_tail":    int(upper_tail),
                "body":          int(body),
                "lower_tail":    int(lower_tail),
                "rsi":           current_rsi,
                "rsi_status":    rsi_status,
                "divergence":    divergence,
                "golden_cross":  golden_cross,
                "hist_positive": hist_positive,
            }

        except Exception as e:
            logger.debug("%s 조건 검사 오류: %s", code, str(e))
            return None

    # ────────────────────────────────────────────
    # 티커 목록
    # ────────────────────────────────────────────
    def _get_all_tickers(self, trading_day: str) -> list:
        tickers = []
        for market in self.markets:
            try:
                codes = stock.get_market_ticker_list(date=trading_day, market=market)
                for code in codes:
                    try:
                        name = stock.get_market_ticker_name(code)
                        tickers.append((code, name))
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("%s 티커 로딩 실패: %s", market, str(e))
        return tickers

    # ────────────────────────────────────────────
    # 메인 스캔
    # ────────────────────────────────────────────
    def scan(self) -> list:
        # KRX 서버 점검 시간 체크
        if self._is_maintenance_time():
            logger.warning("KRX 서버 점검 시간 (00:00~06:00) — 스캔 불가")
            return []

        trading_day = self._latest_trading_day()
        tickers     = self._get_all_tickers(trading_day)
        logger.info("총 %d개 종목 스캔 시작 (기준일: %s)", len(tickers), trading_day)

        results = []
        for i, (code, name) in enumerate(tickers):
            if i % 100 == 0:
                logger.info("... %d / %d", i, len(tickers))
            result = self._check_conditions(code, name, trading_day)
            if result:
                results.append(result)
                logger.info("조건 만족: %s (%s)", name, code)

        logger.info("스캔 완료 - %d개 종목 발견", len(results))
        return results
