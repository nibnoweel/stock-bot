import os

# ── 텔레그램 (기존 변수명 유지) ──────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

# bot.py 새 코드 호환 별칭
TELEGRAM_BOT_TOKEN = TELEGRAM_TOKEN
TELEGRAM_CHAT_ID   = CHAT_ID

# ── 스캔 스케줄 (기존 유지) ──────────────────────
WEEKDAY_SCAN_TIMES = ["08:30"]
WEEKEND_SCAN_TIMES = ["08:30"]

# report_generator / bot.py 에서 쓰는 단일 시간값
REPORT_TIME = WEEKDAY_SCAN_TIMES[0]   # "08:30"

# ── 스캔 설정 (신규) ─────────────────────────────
SCAN_TOP_N     = int(os.environ.get("SCAN_TOP_N",     "30"))
MAX_SCAN_CODES = int(os.environ.get("MAX_SCAN_CODES", "500"))
SCAN_DELAY     = float(os.environ.get("SCAN_DELAY",   "0.3"))

# ── 리포트 출력 (신규) ───────────────────────────
REPORT_OUTPUT_DIR     = os.environ.get("REPORT_OUTPUT_DIR", "/tmp")
SUPPLY_LOOKBACK_DAYS  = int(os.environ.get("SUPPLY_LOOKBACK_DAYS",  "10"))
SCORE_ALERT_THRESHOLD = int(os.environ.get("SCORE_ALERT_THRESHOLD", "100"))

# ── OpenAI (beta: GPT 동적 테마 감지) ────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")