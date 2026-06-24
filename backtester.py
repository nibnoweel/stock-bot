"""
backtester.py
AI밸류체인 watchlist 종목의 20일선 구간별 수익률 검증
구간: 진입(+3~-2%) / 도달(-2~-7%) / 이탈(-7%↓)
독립 실행: python backtester.py
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import FinanceDataReader as fdr
import watchlist

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

LOOKBACK_MONTHS = 6
HOLD_DAYS = 20
TR_COST   = 0.0021


def _classify_pullback(df: pd.DataFrame, idx: int) -> str | None:
    """눌림목 검사 + 20일선 대비 구간 분류. 반환: 진입/도달/이탈/None"""
    if idx < 60:
        return None
    today = df.iloc[idx]
    close = today["Close"]

    # 1. 선행 상승: 최근 20일 +15%
    window = df.iloc[idx - 20:idx + 1]
    win_low  = window["Close"].min()
    win_high = window["High"].max()
    if win_low <= 0:
        return None
    if (win_high - win_low) / win_low * 100 < 15:
        return None

    # 2. 조정: 고점 대비 -5 ~ -15%
    drop_pct = (close - win_high) / win_high * 100
    if not (-15 <= drop_pct <= -5):
        return None

    # 3. 60일선 위
    ma60 = df["Close"].iloc[idx - 60:idx].mean()
    if ma60 <= 0 or close < ma60:
        return None

    # 4. 반등: 양봉 또는 아랫꼬리
    open_, high, low = today["Open"], today["High"], today["Low"]
    body_top = max(open_, close); body_bot = min(open_, close)
    upper = high - body_top; body = body_top - body_bot; lower = body_bot - low
    if not (close > open_ or (lower > body and lower > upper)):
        return None

    # 5. 20일선 대비 구간 분류
    ma20 = df["Close"].iloc[idx - 20:idx].mean()
    if ma20 <= 0:
        return None
    gap20 = (close - ma20) / ma20 * 100

    if gap20 > 3:
        return None          # 미조정 → 제외
    elif gap20 >= -2:
        return "진입"
    elif gap20 >= -7:
        return "도달"
    else:
        return "이탈"


def _backtest_stock(code: str, start: str, end: str) -> list[dict]:
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

    for idx in range(len(df) - HOLD_DAYS - 1):
        if df["Date"].iloc[idx] < start_dt:
            continue
        zone = _classify_pullback(df, idx)
        if zone is None:
            continue

        buy_idx = idx + 1
        if buy_idx >= len(df):
            continue
        buy = df["Open"].iloc[buy_idx]
        if buy <= 0:
            continue
        sell_idx = buy_idx + HOLD_DAYS - 1
        if sell_idx >= len(df):
            continue
        sell = df["Close"].iloc[sell_idx]
        ret = ((sell - buy) / buy - TR_COST) * 100
        records.append({"zone": zone, "ret": ret})

    return records


def run_backtest():
    end   = datetime.now()
    start = end - timedelta(days=LOOKBACK_MONTHS * 30)
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")
    logger.info("백테스트 기간: %s ~ %s", start_str, end_str)

    codes = watchlist.all_codes()
    logger.info("대상 종목 (watchlist): %d개", len(codes))

    all_records = []
    for n, code in enumerate(codes):
        if n % 10 == 0:
            logger.info("진행: %d / %d", n, len(codes))
        all_records += _backtest_stock(code, start_str, end_str)

    if not all_records:
        logger.info("신호 없음")
        return

    zones = ["진입", "도달", "이탈"]
    print("\n" + "=" * 50)
    print(f"20일선 구간별 {HOLD_DAYS}일 수익률 ({start_str} ~ {end_str})")
    print("=" * 50)
    print(f"{'구간':<8}{'신호수':>8}{'평균수익':>10}{'승률':>8}")
    print("-" * 50)
    for z in zones:
        rets = [r["ret"] for r in all_records if r["zone"] == z]
        if not rets:
            print(f"{z:<8}{0:>8}{'-':>10}{'-':>8}")
            continue
        avg = sum(rets) / len(rets)
        win = sum(1 for r in rets if r > 0) / len(rets) * 100
        print(f"{z:<8}{len(rets):>8}{avg:>+9.2f}%{win:>7.0f}%")

    all_rets = [r["ret"] for r in all_records]
    avg = sum(all_rets) / len(all_rets)
    win = sum(1 for r in all_rets if r > 0) / len(all_rets) * 100
    print("-" * 50)
    print(f"{'전체':<8}{len(all_rets):>8}{avg:>+9.2f}%{win:>7.0f}%")
    print("=" * 50)


if __name__ == "__main__":
    run_backtest()