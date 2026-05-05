"""
scanner.py
pykrx → FinanceDataReader 전환
OHLCV 컬럼: Open, High, Low, Close, Volume (영문 대문자)

[최적화] StockListing 1차 필터 + ThreadPoolExecutor 병렬 처리
  - 2771종목 순차 → 후보 필터 후 병렬 처리
  - 예상 속도: 23분 → 1~2분
"""

import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import FinanceDataReader as fdr

from scorer import StockScore, score_from_scan, rank_scores
from supply_scanner import fetch_investor_data
from sector_theme import get_sector, match_stock_themes, ThemeIssue

logger = logging.getLogger(__name__)

# 병렬 처리 워커 수
_OHLCV_WORKERS   = 20   # OHLCV 조회 병렬 수
_SUPPLY_WORKERS  = 10   # 수급 조회 병렬 수

# 1차 필터 기준 (StockListing 데이터로 사전 필터링)
_PRE_FILTER_CHANGE_PCT  = 1.5   # 등락률 최소 (%)  — 여유있게 설정
_PRE_FILTER_VOLUME_MIN  = 10000 # 최소 거래량 (주)


class StockScanner:
    def __init__(self):
        self.markets = ["KOSPI", "KOSDAQ"]

    # ── 공휴일 / 거래일 ──────────────────────────
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

    # ── OHLCV — FDR ──────────────────────────────
    def _get_ohlcv(self, code: str, end_date: str, days: int = 300) -> pd.DataFrame:
        end_dt   = datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=days + 60)
        df = fdr.DataReader(
            code,
            start_dt.strftime("%Y-%m-%d"),
            end_dt.strftime("%Y-%m-%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()

        rename_map = {
            "Open":   "시가",
            "High":   "고가",
            "Low":    "저가",
            "Close":  "종가",
            "Volume": "거래량",
        }
        df = df.rename(columns=rename_map)
        needed = ["시가", "고가", "저가", "종가", "거래량"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            return pd.DataFrame()
        return df[needed].dropna()

    # ── [신규] 1차 필터 — StockListing 기반 ──────
    def _pre_filter_tickers(self, trading_day: str) -> list[tuple[str, str, float]]:
        """
        StockListing에서 당일 등락률 / 거래량으로 사전 필터링.
        반환: (code, name, market_cap_억원) 튜플 리스트
        """
        candidates = []
        for market in self.markets:
            try:
                df = fdr.StockListing(market)
                df["Code"] = df["Code"].astype(str).str.zfill(6)

                col_map = {}
                for c in df.columns:
                    cl = c.lower()
                    if "change" in cl and "ratio" in cl:
                        col_map["change"] = c
                    elif cl == "volume" or cl == "거래량":
                        col_map["volume"] = c
                    elif cl in ("marcap", "시가총액", "marketcap"):
                        col_map["marcap"] = c

                if "change" not in col_map or "volume" not in col_map:
                    logger.warning("%s StockListing 컬럼 부재 — 전체 스캔", market)
                    for _, row in df.iterrows():
                        candidates.append((str(row["Code"]), str(row["Name"]), 0.0))
                    continue

                change_col = col_map["change"]
                volume_col = col_map["volume"]
                marcap_col = col_map.get("marcap")

                filtered = df[
                    (pd.to_numeric(df[change_col], errors="coerce").fillna(0) >= _PRE_FILTER_CHANGE_PCT) &
                    (pd.to_numeric(df[volume_col], errors="coerce").fillna(0) >= _PRE_FILTER_VOLUME_MIN)
                ]
                for _, row in filtered.iterrows():
                    marcap = 0.0
                    if marcap_col:
                        try:
                            marcap = float(row[marcap_col]) / 1e8  # 원 → 억원
                        except Exception:
                            pass
                    candidates.append((str(row["Code"]), str(row["Name"]), marcap))

                logger.info("%s: %d개 → 1차 필터 후 %d개", market, len(df), len(filtered))

            except Exception as e:
                logger.warning("%s 1차 필터 실패 — 전체 스캔 폴백: %s", market, e)
                try:
                    df = fdr.StockListing(market)
                    df["Code"] = df["Code"].astype(str).str.zfill(6)
                    for _, row in df.iterrows():
                        candidates.append((str(row["Code"]), str(row["Name"]), 0.0))
                except Exception:
                    pass

        logger.info("1차 필터 완료: %d개 후보", len(candidates))
        return candidates

    def _get_all_tickers(self, trading_day: str) -> list[tuple[str, str]]:
        """FDR StockListing으로 KOSPI + KOSDAQ 전 종목 (폴백용 유지)"""
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

    # ── 캔들 / RSI / MACD ────────────────────────
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

    # ── 조건 검사 ────────────────────────────────
    def _check_conditions(self, code, name, end_date):
        try:
            df = self._get_ohlcv(code, end_date, days=300)
            if df is None or len(df) < 202: return None

            today = df.iloc[-1]; yesterday = df.iloc[-2]
            if yesterday["거래량"] == 0: return None
            volume_ratio = today["거래량"] / yesterday["거래량"]
            if volume_ratio < 2.0: return None

            if yesterday["종가"] == 0: return None
            change_pct = (today["종가"] - yesterday["종가"]) / yesterday["종가"] * 100
            if change_pct < 2.0: return None

            if len(df) < 205: return None
            above_count = 0; ma200_gap = 0.0
            for i in range(1, 6):
                idx = len(df) - i
                if idx < 200: return None
                ma200 = df["종가"].iloc[idx - 200:idx].mean()
                gap   = (df["종가"].iloc[idx] - ma200) / ma200 * 100
                if gap >= 3.0: above_count += 1
                if i == 1: ma200_gap = gap
            if above_count < 5: return None

            upper_tail, body, lower_tail = self._candle_parts(today)
            if not (upper_tail < body and upper_tail < lower_tail): return None

            rsi_series  = self._calc_rsi(df["종가"])
            current_rsi = round(float(rsi_series.iloc[-1]), 1)
            divergence  = self._detect_divergence(df, rsi_series)
            rsi_status  = "과매수" if current_rsi >= 70 else ("과매도" if current_rsi <= 30 else "중립")

            macd_line, signal_line, hist = self._calc_macd(df["종가"])
            golden_cross  = self._detect_golden_cross(macd_line, signal_line)
            hist_positive = bool(hist.iloc[-1] > 0 and hist.iloc[-2] <= 0)

            return {
                "code": code, "name": name,
                "close": int(today["종가"]),
                "change_pct": change_pct, "volume_ratio": volume_ratio,
                "ma200_gap": ma200_gap,
                "upper_tail": int(upper_tail), "body": int(body), "lower_tail": int(lower_tail),
                "rsi": current_rsi, "rsi_status": rsi_status, "divergence": divergence,
                "golden_cross": golden_cross, "hist_positive": hist_positive,
                "_df": df,
            }
        except Exception as e:
            logger.debug("%s 조건 검사 오류: %s", code, e)
            return None

    # ── [최적화] 병렬 OHLCV 스캔 ─────────────────
    def _parallel_scan(self, tickers: list[tuple[str, str]], trading_day: str) -> list[dict]:
        """ThreadPoolExecutor로 OHLCV 조회 + 조건 검사 병렬 처리"""
        results = []
        total = len(tickers)
        done  = 0

        with ThreadPoolExecutor(max_workers=_OHLCV_WORKERS) as executor:
            future_map = {
                executor.submit(self._check_conditions, code, name, trading_day): (code, name)
                for code, name in tickers
            }
            for future in as_completed(future_map):
                done += 1
                if done % 50 == 0:
                    logger.info("OHLCV 검사 중... %d / %d", done, total)
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        logger.info("조건 만족: %s (%s)", result["name"], result["code"])
                except Exception as e:
                    code, name = future_map[future]
                    logger.debug("%s 병렬 처리 오류: %s", code, e)

        return results

    # ── [최적화] 병렬 수급 조회 ───────────────────
    def _parallel_supply(self, results: list[dict]) -> dict[str, dict]:
        """조건 통과 종목 수급을 병렬로 한꺼번에 조회"""
        supply_map: dict[str, dict] = {}

        def _fetch(code):
            return code, fetch_investor_data(code, days=10)

        with ThreadPoolExecutor(max_workers=_SUPPLY_WORKERS) as executor:
            futures = {executor.submit(_fetch, r["code"]): r["code"] for r in results}
            for future in as_completed(futures):
                try:
                    code, data = future.result()
                    supply_map[code] = data
                except Exception as e:
                    code = futures[future]
                    logger.debug("%s 수급 조회 오류: %s", code, e)
                    supply_map[code] = {"foreign_10d": 0.0, "institution_10d": 0.0}

        return supply_map

    # ── scan() ────────────────────────────────────
    def scan(self) -> list:
        if self._is_maintenance_time():
            logger.warning("KRX 서버 점검 시간 (00:00~06:00) — 스캔 불가")
            return []

        trading_day = self._latest_trading_day()
        candidates  = self._pre_filter_tickers(trading_day)
        logger.info("OHLCV 상세 검사 시작: %d개 후보 (기준일: %s)", len(candidates), trading_day)

        results = self._parallel_scan(candidates, trading_day)
        for r in results:
            r.pop("_df", None)

        logger.info("스캔 완료 - %d개 종목 발견", len(results))
        return results

    # ── scan_with_score() ─────────────────────────
    def scan_with_score(
        self,
        themes: list[ThemeIssue],
        news_sentiment_map: dict[str, float],
    ) -> list[StockScore]:
        if self._is_maintenance_time():
            logger.warning("KRX 서버 점검 시간 — 스캔 불가")
            return []

        trading_day = self._latest_trading_day()
        candidates  = self._pre_filter_tickers(trading_day)
        logger.info("점수 스캔 시작: %d개 후보 (기준일: %s)", len(candidates), trading_day)

        results = self._parallel_scan(candidates, trading_day)
        logger.info("조건 통과: %d종목 → 수급 조회 시작", len(results))

        if not results:
            return []

        supply_map = self._parallel_supply(results)

        scores: list[StockScore] = []
        for result in results:
            code     = result["code"]
            df_ohlcv = result.pop("_df")
            supply   = supply_map.get(code, {"foreign_10d": 0.0, "institution_10d": 0.0})
            marcap   = marcap_map.get(code, 0.0)   # 신규

            s = score_from_scan(
                scan_result=result,
                df_ohlcv=df_ohlcv,
                foreign_10d=supply["foreign_10d"],
                institution_10d=supply["institution_10d"],
                news_sentiment=news_sentiment_map.get(code, 0.0),
                matched_themes=match_stock_themes(code, themes),
                sector=get_sector(code),
            )
            s.market_cap = marcap   # StockScore에 동적 추가
            scores.append(s)
            logger.info("점수: %s (%s) — %d점", result["name"], code, s.total)

        logger.info("점수 스캔 완료: %d종목", len(scores))
        return rank_scores(scores)