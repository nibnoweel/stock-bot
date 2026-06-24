"""
diagnose.py
watchlist 50종목에 눌림목 필터를 단계별로 적용
어느 조건에서 몇 종목이 걸러지는지 진단
독립 실행: python diagnose.py
"""

from datetime import datetime, timedelta
import FinanceDataReader as fdr
import watchlist


def get_ohlcv(code, end_date, days=90):
    end_dt   = datetime.strptime(end_date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=days + 60)
    try:
        df = fdr.DataReader(code, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.rename(columns={"Open":"시가","High":"고가","Low":"저가","Close":"종가","Volume":"거래량"})
    return df[["시가","고가","저가","종가","거래량"]].dropna().reset_index(drop=True)


def latest_trading_day():
    now = datetime.now()
    if now.hour >= 16 and now.weekday() < 5:
        return now.strftime("%Y%m%d")
    for i in range(1, 10):
        d = now - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return now.strftime("%Y%m%d")


def candle_parts(row):
    o, h, l, c = row["시가"], row["고가"], row["저가"], row["종가"]
    bt, bb = max(o, c), min(o, c)
    return h - bt, bt - bb, bb - l


def diagnose():
    end_date = latest_trading_day()
    name_map = watchlist.code_to_name()
    print(f"진단 기준일: {end_date}, 종목수: {len(name_map)}\n")

    # 단계별 카운터
    cnt = {
        "데이터OK": 0,
        "1_선행상승": 0,
        "2_조정구간": 0,
        "3_20일선지지": 0,
        "4_60일선위": 0,
        "5_반등신호": 0,
    }
    # 각 단계 통과 종목 기록
    survivors = {k: [] for k in cnt}

    for code, name in name_map.items():
        df = get_ohlcv(code, end_date)
        if df is None or len(df) < 70:
            continue
        cnt["데이터OK"] += 1

        idx = len(df) - 1
        today = df.iloc[idx]
        close = today["종가"]

        # 1. 선행상승 +15%
        window = df.iloc[idx - 20:idx + 1]
        win_low, win_high = window["종가"].min(), window["고가"].max()
        if win_low <= 0:
            continue
        rise = (win_high - win_low) / win_low * 100
        if rise < 15:
            continue
        cnt["1_선행상승"] += 1
        survivors["1_선행상승"].append(f"{name}({rise:.0f}%)")

        # 2. 조정 -5~-15%
        drop = (close - win_high) / win_high * 100
        if not (-15 <= drop <= -5):
            continue
        cnt["2_조정구간"] += 1
        survivors["2_조정구간"].append(f"{name}({drop:.0f}%)")

        # 3. 20일선 지지 ±3%
        ma20 = df["종가"].iloc[idx - 20:idx].mean()
        if ma20 <= 0:
            continue
        gap20 = (close - ma20) / ma20 * 100
        if abs(gap20) > 3:
            continue
        cnt["3_20일선지지"] += 1
        survivors["3_20일선지지"].append(f"{name}({gap20:+.0f}%)")

        # 4. 60일선 위
        ma60 = df["종가"].iloc[idx - 60:idx].mean()
        if ma60 <= 0 or close < ma60:
            continue
        cnt["4_60일선위"] += 1
        survivors["4_60일선위"].append(name)

        # 5. 반등 신호
        upper, body, lower = candle_parts(today)
        is_bullish = close > today["시가"]
        has_tail = lower > body and lower > upper
        if not (is_bullish or has_tail):
            continue
        cnt["5_반등신호"] += 1
        survivors["5_반등신호"].append(name)

    # 출력
    print("=" * 50)
    print("단계별 통과 종목 수 (AND 조건, 순차 적용)")
    print("=" * 50)
    for k in ["데이터OK", "1_선행상승", "2_조정구간", "3_20일선지지", "4_60일선위", "5_반등신호"]:
        print(f"{k:<14} {cnt[k]:>3}종목")
    print("=" * 50)

    # 각 단계 생존 종목 (1~3단계만, 너무 길지 않게)
    for k in ["1_선행상승", "2_조정구간", "3_20일선지지"]:
        s = survivors[k]
        if s:
            print(f"\n[{k}] {', '.join(s[:15])}")


if __name__ == "__main__":
    diagnose()