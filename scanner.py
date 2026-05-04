"""
KRX 주식 스캐너 - yfinance 버전
한국 주식: 종목코드 + .KS (KOSPI) 또는 .KQ (KOSDAQ)
"""

import logging
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# KOSPI 주요 종목 + KOSDAQ 주요 종목 하드코딩 리스트
# yfinance는 종목 목록 API가 없어서 주요 종목만 스캔
KOSPI_TICKERS = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"),
    ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("000270", "기아"),
    ("068270", "셀트리온"), ("105560", "KB금융"), ("055550", "신한지주"),
    ("012330", "현대모비스"), ("028260", "삼성물산"), ("066570", "LG전자"),
    ("017670", "SK텔레콤"), ("032830", "삼성생명"), ("003550", "LG"),
    ("009150", "삼성전기"), ("011200", "HMM"), ("010130", "고려아연"),
    ("096770", "SK이노베이션"), ("034730", "SK"), ("003490", "대한항공"),
    ("000810", "삼성화재"), ("086790", "하나금융지주"), ("018260", "삼성에스디에스"),
    ("011070", "LG이노텍"), ("047050", "포스코인터내셔널"), ("033780", "KT&G"),
    ("030200", "KT"), ("316140", "우리금융지주"), ("010950", "S-Oil"),
    ("139480", "이마트"), ("097950", "CJ제일제당"), ("004020", "현대제철"),
    ("011790", "SKC"), ("009830", "한화솔루션"), ("000100", "유한양행"),
    ("021240", "코웨이"), ("024110", "기업은행"), ("000720", "현대건설"),
    ("161390", "한국타이어앤테크놀로지"), ("090430", "아모레퍼시픽"),
    ("002790", "아모레G"), ("000080", "하이트진로"), ("271560", "오리온"),
    ("006800", "미래에셋증권"), ("003670", "포스코퓨처엠"),
]

KOSDAQ_TICKERS = [
    ("247540", "에코프로비엠"), ("086520", "에코프로"), ("196170", "알테오젠"),
    ("091990", "셀트리온헬스케어"), ("357780", "솔브레인"), ("145020", "휴젤"),
    ("112040", "위메이드"), ("041510", "에스엠"), ("035900", "JYP Ent"),
    ("122870", "와이지엔터테인먼트"), ("095340", "ISC"), ("293490", "카카오게임즈"),
    ("036570", "엔씨소프트"), ("251270", "넷마블"), ("263750", "펄어비스"),
    ("058970", "엠플러스"), ("214150", "클래시스"), ("226340", "본느"),
    ("950130", "엑스페릭스"), ("066970", "엘앤에프"),
]


class StockScanner:
    def __init__(self):
        self.tickers = KOSPI_TICKERS + KOSDAQ_TICKERS

    KR_HOLIDAYS = {
        "20250101","20250128","20250129","20250130","20250301",
        "20250505","20250506","20250606","20250815","20251003",
        "20251006","20251007","20251008","20251009","20251225",
        "20260101","20260216","20260217","20260218","20260301",
        "20260505","20260606","20260815","20260924","20260925",
        "20260928","20261009","20261225",
    }

    def _is_holiday(self, d: datetime) -> bool:
        if d.weekday() >= 5:
            return True
        return d.strftime("%Y%m%d") in self.KR_HOLIDAYS

    def _is_today_trading_day(self) -> bool:
        return not self._is_holiday(datetime.now())

    def _latest_trading_day(self) -> str:
        now = datetime.now()
        if not self._is_holiday(now) and now.hour >= 16:
            logger.info("기준 거래일: %s (당일 마감 후)", now.strftime("%Y%m%d"))
            return now.strftime("%Y%m%d")
        for i in range(1, 30):
            d = now - timedelta(days=i)
            if not self._is_holiday(d):
                logger.info("기준 거래일: %s", d.strftime("%Y%m%d"))
                return d.strftime("%Y%m%d")
        return (now - timedelta(days=1)).strftime("%Y%m%d")

    def _get_ohlcv(self, code: str, days: int = 300) -> pd.DataFrame:
        # yfinance: KOSPI는 .KS, KOSDAQ은 .KQ
        for suffix in [".KS", ".KQ"]:
            try:
                ticker = yf.Ticker(code + suffix)
                df = ticker.history(period=f"{days}d")
                if len(df) > 50:
                    df = df.rename(columns={
                        "Open": "시가", "High": "고가", "Low": "저가",
                        "Close": "종가", "Volume": "거래량"
                    })
                    return df[["시가", "고가", "저가", "종가", "거래량"]]
            except Exception:
                continue
        return pd.DataFrame()

    @staticmethod
    def _candle_parts(row):
        o, h, l, c = row["시가"], row["고가"], row["저가"], row["종가"]
        top = max(o, c); bot = min(o, c)
        return h - top, top - bot, bot - l

    @staticmethod
    def _calc_rsi(closes, period=14):
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        ag = gain.ewm(com=period-1, min_periods=period).mean()
        al = loss.ewm(com=period-1, min_periods=period).mean()
        rs = ag / al.replace(0, 1e-10)
        return 100 - (100 / (1 + rs))

    def _detect_divergence(self, df, rsi):
        if len(df) < 20:
            return "없음"
        recent = df.iloc[-20:]
        rr = rsi.iloc[-20:]
        cur = rsi.iloc[-1]
        if cur < 30:
            lows = recent["저가"].values; rv = rr.values
            for i in range(len(lows)-5, 0, -1):
                if lows[-1] < lows[i]:
                    d = rv[-1] - rv[i]
                    if 5 <= d <= 10: return "상승"
        if cur > 70:
            highs = recent["고가"].values; rv = rr.values
            for i in range(len(highs)-5, 0, -1):
                if highs[-1] > highs[i]:
                    d = rv[i] - rv[-1]
                    if 5 <= d <= 10: return "하락"
        return "없음"

    @staticmethod
    def _calc_macd(closes):
        e12 = closes.ewm(span=12, adjust=False).mean()
        e26 = closes.ewm(span=26, adjust=False).mean()
        macd = e12 - e26
        sig = macd.ewm(span=9, adjust=False).mean()
        return macd, sig, macd - sig

    @staticmethod
    def _golden_cross(macd, signal):
        if len(macd) < 3: return False
        for i in range(-3, 0):
            if macd.iloc[i-1] < signal.iloc[i-1] and macd.iloc[i] > signal.iloc[i]:
                return True
        return False

    def _check(self, code, name):
        try:
            df = self._get_ohlcv(code)
            if len(df) < 205: return None
            t = df.iloc[-1]; y = df.iloc[-2]

            if y["거래량"] == 0: return None
            vr = t["거래량"] / y["거래량"]
            if vr < 2.0: return None

            if y["종가"] == 0: return None
            cp = (t["종가"] - y["종가"]) / y["종가"] * 100
            if cp < 2.0: return None

            cnt = 0; gap = 0.0
            for i in range(1, 6):
                idx = len(df) - i
                if idx < 200: return None
                ma = df["종가"].iloc[idx-200:idx].mean()
                g = (df["종가"].iloc[idx] - ma) / ma * 100
                if g >= 3.0: cnt += 1
                if i == 1: gap = g
            if cnt < 5: return None

            ut, b, lt = self._candle_parts(t)
            if not (ut < b and ut < lt): return None

            rsi = self._calc_rsi(df["종가"])
            cr = round(float(rsi.iloc[-1]), 1)
            div = self._detect_divergence(df, rsi)
            rs = "과매수" if cr >= 70 else ("과매도" if cr <= 30 else "중립")

            ml, sl, hl = self._calc_macd(df["종가"])
            gc = self._golden_cross(ml, sl)
            hp = bool(hl.iloc[-1] > 0 and hl.iloc[-2] <= 0)

            return {
                "code": code, "name": name,
                "close": int(t["종가"]), "change_pct": cp,
                "volume_ratio": vr, "ma200_gap": gap,
                "upper_tail": int(ut), "body": int(b), "lower_tail": int(lt),
                "rsi": cr, "rsi_status": rs, "divergence": div,
                "golden_cross": gc, "hist_positive": hp,
            }
        except Exception as e:
            logger.debug("%s 오류: %s", code, str(e))
            return None

    def scan(self) -> list:
        trading_day = self._latest_trading_day()
        logger.info("총 %d개 종목 스캔 시작 (기준일: %s)", len(self.tickers), trading_day)

        results = []
        for i, (code, name) in enumerate(self.tickers):
            if i % 10 == 0:
                logger.info("... %d / %d", i, len(self.tickers))
            r = self._check(code, name)
            if r:
                results.append(r)
                logger.info("조건 만족: %s (%s)", name, code)

        logger.info("스캔 완료 - %d개 종목", len(results))
        return results