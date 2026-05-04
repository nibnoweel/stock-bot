"""
config.py  (업그레이드 버전)
환경변수 기반 설정
Railway 환경변수로 주입하면 됨
"""

import os

# ── 텔레그램 ─────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# ── 스케줄 ───────────────────────────────────────
REPORT_TIME = os.environ.get("REPORT_TIME", "09:00")   # "HH:MM" KST

# ── 스캔 설정 ─────────────────────────────────────
SCAN_TOP_N      = int(os.environ.get("SCAN_TOP_N",     "30"))
MAX_SCAN_CODES  = int(os.environ.get("MAX_SCAN_CODES", "500"))
SCAN_DELAY      = float(os.environ.get("SCAN_DELAY",   "0.3"))   # 요청 간격 (초)

# ── 뉴스 RSS ─────────────────────────────────────
RSS_SOURCES = [
    "https://www.mk.co.kr/rss/30100041/",            # 매일경제 증권
    "https://www.hankyung.com/feed/economy",         # 한국경제
    "https://finance.naver.com/news/news_list.nhn",  # 네이버 경제
    "https://www.sedaily.com/rss",                   # 서울경제
]

# ── 리포트 ───────────────────────────────────────
REPORT_OUTPUT_DIR = os.environ.get("REPORT_OUTPUT_DIR", "/tmp")
FONT_PATH = os.environ.get(
    "FONT_PATH",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
)

# ── 수급 데이터 ──────────────────────────────────
SUPPLY_LOOKBACK_DAYS = int(os.environ.get("SUPPLY_LOOKBACK_DAYS", "10"))

# ── 점수 임계값 (알림 기준) ───────────────────────
SCORE_ALERT_THRESHOLD = int(os.environ.get("SCORE_ALERT_THRESHOLD", "100"))
