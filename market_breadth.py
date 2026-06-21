"""
market_breadth.py
AI 밸류체인 안에서 '통매수 vs 눌림목' 비교
프로그램 짤 가치가 있는지 최종 검증
독립 실행: python market_breadth.py
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import FinanceDataReader as fdr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

LOOKBACK_MONTHS = 6
HOLD_DAYS = 30
TR_COST = 0.0021   # 왕복 거래비용

# ── AI 밸류체인 종목 (테마 구분 없이 전체) ──────────
THEME_STOCKS = {
    "반도체": ["005930","000660","042700","007660","000990",
              "058470","039030","403870","036930","089030"],
    "원전":   ["034020","015760","052690","051600","105840",
              "457550","094820","046120","083650","019990"],
    "전력":   ["010120","267260","298040","103590","062040",
              "033100","042370","017040","017510","006340"],
    "로봇":   ["454910","064350","066570","000880","267250",
              "277810","108490","058610","056080","348340"],
    "데이터센터":["018260","007660","006260","001440","006360",
              "093320","079940","083450","230240","377330"],
}


def _load(code: str, start: str, end: str) -> pd.DataFrame | None:
    load_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader(code, load_start, end)
    except Exception:
        return None
    if df is None or len(df) < 210:
        return None
    return df.reset_index()


# ── 눌림목 필터 (backtester.py와 동일) ──────────
def _passes_filters(df: pd.DataFrame, idx: int) -> bool:
    if idx < 60:
        return False
    today = df.iloc[idx]
    close = today["Close"]

    # 선행 상승: 최근 20일 내 +15%
    window = df.iloc[idx - 20:idx + 1]
    win_low  = window["Close"].min()
    win_high = window["High"].max()
    if win_low <= 0:
        return False
    if (win_high - win_low) / win_low * 100 < 15:
        return False

    # 조정: 고점 대비 -5 ~ -15%
    drop_pct = (close - win_high) / win_high * 100
    if not (-15 <= drop_pct <= -5):
        return False

    # 20일선 지지 ±3%
    ma20 = df["Close"].iloc[idx - 20:idx].mean()
    if ma20 <= 0:
        return False
    if abs((close - ma20) / ma20 * 100) > 3:
        return False

    # 60일선 위
    ma60 = df["Close"].iloc[idx - 60:idx].mean()
    if ma60 <= 0 or close < ma60:
        return False

    # 반등: 양봉 또는 아랫꼬리
    open_, high, low = today["Open"], today["High"], today["Low"]
    body_top = max(open_, close); body_bot = min(open_, close)
    upper = high - body_top; body = body_top - body_bot; lower = body_bot - low
    if not (close > open_ or (lower > body and lower > upper)):
        return False

    return True


def _returns(df: pd.DataFrame, start: str, only_pullback: bool) -> list[float]:
    """
    수익률 리스트 반환
    only_pullback=False → 모든 날 매수 (통매수)
    only_pullback=True  → 눌림목 신호일만 매수
    """
    start_dt = pd.Timestamp(start)
    rets = []
    for idx in range(len(df) - HOLD_DAYS - 1):
        if df["Date"].iloc[idx] < start_dt:
            continue
        if only_pullback and not _passes_filters(df, idx):
            continue
        if idx + 1 >= len(df):
            continue
        buy = df["Open"].iloc[idx + 1]
        sell_idx = idx + HOLD_DAYS
        if buy <= 0 or sell_idx >= len(df):
            continue
        sell = df["Close"].iloc[sell_idx]
        rets.append(((sell - buy) / buy - TR_COST) * 100)
    return rets


def run():
    end   = datetime.now()
    start = end - timedelta(days=LOOKBACK_MONTHS * 30)
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")
    logger.info("기간: %s ~ %s", start_str, end_str)

    # 전 종목 한 번씩만 로드 (중복 제거)
    all_codes = set()
    for codes in THEME_STOCKS.values():
        all_codes.update(codes)

    buy_all = []      # 통매수 수익률
    buy_pull = []     # 눌림목 수익률

    for n, code in enumerate(all_codes):
        logger.info("로드 %d/%d: %s", n + 1, len(all_codes), code)
        df = _load(code, start_str, end_str)
        if df is None:
            continue
        buy_all  += _returns(df, start_str, only_pullback=False)
        buy_pull += _returns(df, start_str, only_pullback=True)

    def summary(rets):
        if not rets:
            return (0, 0.0, 0.0)
        n = len(rets)
        avg = sum(rets) / n
        win = sum(1 for r in rets if r > 0) / n * 100
        return (n, avg, win)

    n1, avg1, win1 = summary(buy_all)
    n2, avg2, win2 = summary(buy_pull)

    print("\n" + "=" * 55)
    print(f"AI 밸류체인 전략 비교 ({HOLD_DAYS}일 보유, 비용 반영)")
    print(f"({start_str} ~ {end_str})")
    print("=" * 55)
    print(f"{'전략':<16}{'신호수':>8}{'평균수익':>10}{'승률':>8}")
    print("-" * 55)
    print(f"{'① 통매수':<16}{n1:>8}{avg1:>+9.2f}%{win1:>7.0f}%")
    print(f"{'② 눌림목':<16}{n2:>8}{avg2:>+9.2f}%{win2:>7.0f}%")
    print("-" * 55)
    diff = avg2 - avg1
    print(f"눌림목 초과수익: {diff:+.2f}%p")
    print("=" * 55)


if __name__ == "__main__":
    run()