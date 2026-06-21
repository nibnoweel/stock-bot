"""
backtester.py
과거 6개월간 필터 4개 통과 종목의 1·3·5일 후 수익률 검증
독립 실행 스크립트 — 봇과 무관, 로컬에서 실행

실행: python backtester.py
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import FinanceDataReader as fdr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────
LOOKBACK_MONTHS = 6        # 검증 기간
HOLD_DAYS       = [5, 10, 20]  # 보유 기간
TR_COST         = 0.0021   # 왕복 거래비용 (거래세 0.18% + 수수료 0.03%)
MARKETS         = ["KOSPI", "KOSDAQ"]


# ── 필터 로직 (scanner.py와 동일) ──────────────
def _candle_parts(row):
    open_, high = row["Open"], row["High"]
    low, close  = row["Low"], row["Close"]
    body_top = max(open_, close)
    body_bot = min(open_, close)
    return high - body_top, body_top - body_bot, body_bot - low


def _passes_filters(df: pd.DataFrame, idx: int) -> bool:
    """
    1차 눌림목 검사
    선행상승 → 조정(-5~-15%) → 20일선 지지 → 추세유지 → 반등신호
    """
    # 60일선 + 선행상승 확인 위해 최소 60봉 필요
    if idx < 60:
        return False

    today = df.iloc[idx]
    close = today["Close"]

    # ── 1. 선행 상승: 최근 20일 내 +15% 이상 오른 적 있음 ──
    window = df.iloc[idx - 20:idx + 1]
    win_low  = window["Close"].min()
    win_high = window["High"].max()
    if win_low <= 0:
        return False
    if (win_high - win_low) / win_low * 100 < 15:
        return False

    # ── 2. 조정 진행: 최근 고점 대비 -5 ~ -15% 구간 ──
    drop_pct = (close - win_high) / win_high * 100  # 음수
    if not (-15 <= drop_pct <= -5):
        return False

    # ── 3. 20일선 지지: 종가가 20일선 ±3% 이내 ──
    ma20 = df["Close"].iloc[idx - 20:idx].mean()
    if ma20 <= 0:
        return False
    gap20 = (close - ma20) / ma20 * 100
    if abs(gap20) > 3:
        return False

    # ── 4. 추세 유지: 종가가 60일선 위 ──
    ma60 = df["Close"].iloc[idx - 60:idx].mean()
    if ma60 <= 0 or close < ma60:
        return False

    # ── 5. 반등 신호: 양봉 또는 아랫꼬리 (지지 확인) ──
    open_, high, low = today["Open"], today["High"], today["Low"]
    body_top = max(open_, close)
    body_bot = min(open_, close)
    upper_tail = high - body_top
    body       = body_top - body_bot
    lower_tail = body_bot - low

    is_bullish    = close > open_                      # 양봉
    has_long_tail = lower_tail > body and lower_tail > upper_tail  # 긴 아랫꼬리
    if not (is_bullish or has_long_tail):
        return False

    # ── 6. 거래량 바닥: 최근 5일 평균 < 상승기 거래량 ──
    trans_rate = 0.6
    recent_vol = df["Volume"].iloc[idx - 4:idx + 1].mean()   # 최근 5일 평균
    rise_vol   = df["Volume"].iloc[idx - 20:idx - 5].max()   # 상승기 최대 거래량
    if rise_vol <= 0:
        return False
    if recent_vol >= rise_vol * trans_rate:   # 40% 이상이면 제외
        return False

    return True

# ── 단일 종목 백테스트 ─────────────────────────
def _backtest_stock(code: str, start: str, end: str) -> list[dict]:
    """한 종목에서 발생한 모든 신호의 수익률 기록 반환"""
    # 이평선 계산 위해 시작일 이전 300일 추가 로드
    load_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader(code, load_start, end)
    except Exception:
        return []

    if df is None or len(df) < 210:
        return []

    df = df.reset_index()
    if "Date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Date"})

    records = []
    start_dt = pd.Timestamp(start)

    # 신호 검사 (검증 구간 내에서만, 매도일 확보 위해 끝에서 max(HOLD) 제외)
    for idx in range(len(df) - max(HOLD_DAYS) - 1):
        if df["Date"].iloc[idx] < start_dt:
            continue
        if not _passes_filters(df, idx):
            continue

        # 매수: 신호 다음날 시가
        buy_idx = idx + 1
        if buy_idx >= len(df):
            continue
        buy_price = df["Open"].iloc[buy_idx]
        if buy_price <= 0:
            continue

        rec = {"code": code, "date": df["Date"].iloc[idx].strftime("%Y-%m-%d")}
        for hold in HOLD_DAYS:
            sell_idx = buy_idx + hold - 1
            if sell_idx >= len(df):
                rec[f"ret_{hold}d"] = None
                continue
            sell_price = df["Close"].iloc[sell_idx]
            gross = (sell_price - buy_price) / buy_price
            rec[f"ret_{hold}d"] = (gross - TR_COST) * 100  # % 단위, 비용 차감
        records.append(rec)

    return records


# ── 벤치마크 (전 종목 평균 수익률) ─────────────
def _benchmark(all_dfs: dict, start: str) -> dict:
    """같은 기간 전 종목 평균 N일 수익률 (무작위 매수 기준)"""
    bench = {h: [] for h in HOLD_DAYS}
    start_dt = pd.Timestamp(start)
    for code, df in all_dfs.items():
        for idx in range(len(df) - max(HOLD_DAYS) - 1):
            if df["Date"].iloc[idx] < start_dt:
                continue
            buy_idx = idx + 1
            if buy_idx >= len(df):
                continue
            buy = df["Open"].iloc[buy_idx]
            if buy <= 0:
                continue
            for h in HOLD_DAYS:
                sell_idx = buy_idx + h - 1
                if sell_idx >= len(df):
                    continue
                sell = df["Close"].iloc[sell_idx]
                bench[h].append((sell - buy) / buy * 100)
    return {h: (sum(v) / len(v) if v else 0.0) for h, v in bench.items()}


# ── 메인 ───────────────────────────────────────
def run_backtest():
    end   = datetime.now()
    start = end - timedelta(days=LOOKBACK_MONTHS * 30)
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    logger.info("백테스트 기간: %s ~ %s", start_str, end_str)

    # 종목 리스트
    codes = []
    for market in MARKETS:
        try:
            df = fdr.StockListing(market)
            df["Code"] = df["Code"].astype(str).str.zfill(6)
            codes += df["Code"].tolist()
        except Exception as e:
            logger.warning("%s 리스팅 실패: %s", market, e)
    logger.info("대상 종목: %d개", len(codes))

    all_records = []
    for n, code in enumerate(codes):
        if n % 100 == 0:
            logger.info("진행: %d / %d", n, len(codes))
        all_records += _backtest_stock(code, start_str, end_str)

    if not all_records:
        logger.info("신호 없음")
        return

    rdf = pd.DataFrame(all_records)
    logger.info("\n총 신호: %d건", len(rdf))

    # 집계
    print("\n" + "=" * 50)
    print(f"백테스트 결과 ({start_str} ~ {end_str})")
    print(f"신호 발생: 총 {len(rdf)}건")
    print("=" * 50)
    print(f"{'':>8}", *[f"{h}일후".rjust(8) for h in HOLD_DAYS])

    avg_row = ["평균수익"]
    win_row = ["승률    "]
    for h in HOLD_DAYS:
        col = rdf[f"ret_{h}d"].dropna()
        avg_row.append(f"{col.mean():+.2f}%".rjust(8))
        win_row.append(f"{(col > 0).mean() * 100:.0f}%".rjust(8))
    print(*avg_row)
    print(*win_row)

    print("=" * 50)
    print("초과수익(벤치마크 대비)은 별도 계산이 필요하면 활성화하세요.")


if __name__ == "__main__":
    run_backtest()