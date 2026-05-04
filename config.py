import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# 평일 스캔 시간 (월~금)
WEEKDAY_SCAN_TIMES = [
    "08:30",   # 개장 전
    "12:30",   # 점심
    "16:00",   # 장 마감 후
]

# 주말/공휴일 스캔 시간 (토~일 + 공휴일)
WEEKEND_SCAN_TIMES = [
    "08:30",   # 오전
    "20:00",   # 오후 8시
]
