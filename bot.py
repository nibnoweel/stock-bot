"""
bot.py (업그레이드)
기존 구조 완전 유지
수정: scheduler를 app.post_init으로 이동 (no running event loop 해결)
"""

import logging
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scanner import StockScanner
from news_scanner import (NewsScanner, fetch_all_news, build_stock_sentiment_map, build_theme_news_map, build_hot_keyword_map, fetch_target_price_changes)   # 신규
from sector_theme import classify_news_to_themes_with_gpt, count_hot_keywords, THEME_KEYWORDS
from report_generator import generate_report
from config import TELEGRAM_TOKEN, CHAT_ID, WEEKDAY_SCAN_TIMES, WEEKEND_SCAN_TIMES

# 모든 로그의 기본 레벨은 INFO로 두되,
logging.basicConfig(level=logging.INFO)

# httpx(텔레그램 통신 라이브러리)의 로그만 WARNING 등급으로 높여서
# 200 OK 같은 일반 정보는 안 찍히게 만듭니다.
logging.getLogger("httpx").setLevel(logging.WARNING)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scanner      = StockScanner()
news_scanner = NewsScanner()


def _is_trading_day() -> bool:
    return not scanner._is_holiday(datetime.now())


# ────────────────────────────────────────────────
# 통합 스캔 + PDF 전송
# ────────────────────────────────────────────────
async def run_full_scan(context: ContextTypes.DEFAULT_TYPE = None, bot: Bot = None):
    _bot = bot or (context.bot if context else None)
    if not _bot:
        return

    is_trading = _is_trading_day()
    logger.info("스캔 시작 (거래일: %s)", is_trading)

#     if datetime.now().hour < 6:
#         await _bot.send_message(
#             chat_id=CHAT_ID,
#             text="⚠️ 현재 KRX 서버 점검 시간(00:00~06:00)입니다.\n오전 6시 이후에 다시 시도해주세요.",
#             parse_mode="Markdown"
#         )
#         return

    try:
        trading_day = scanner._latest_trading_day()

        # 1. 기존 주식 스캔
        stock_results = scanner.scan()
        logger.info("주식 스캔 완료: %d종목", len(stock_results))

        # 2. 기존 뉴스 스캔
        positive_news, negative_news = news_scanner.scan()
        logger.info("뉴스 스캔 완료: 긍정 %d, 부정 %d", len(positive_news), len(negative_news))

        # 3. 테마 분류
        news_items = fetch_all_news()
        themes = classify_news_to_themes_with_gpt(news_items)
        logger.info("테마 감지: %d개", len(themes))

        # 4. 점수 스캔
        scores = None
        if stock_results:
            sentiment_map = build_stock_sentiment_map(news_items)
            scores = scanner.scan_with_score(
                themes=themes,
                news_sentiment_map=sentiment_map,
            )
            logger.info("점수 계산 완료: %d종목", len(scores) if scores else 0)

        # 3스토 과열 알림
        if scores:
            overbought = [s for s in scores if s.triple_overbought]
            oversold   = [s for s in scores if s.triple_oversold]

            if overbought or oversold:
                alert_lines = ["⚠️ *3스토 신호 감지*\n"]
                if overbought:
                    alert_lines.append("🔴 *과매수 (매도 주의!!)*")
                    for s in overbought[:5]:
                        alert_lines.append(
                            f"  {s.name} | RSI {s.rsi:.0f} | "
                            f"단기스토 {s.stoch_k_short:.0f} | 중기스토 {s.stoch_k_mid:.0f} | {s.total}점"
                        )
                if oversold:
                    alert_lines.append("\n🟢 *과매도 (매수 기회)*")
                    for s in oversold[:5]:
                        alert_lines.append(
                            f"  {s.name} | RSI {s.rsi:.0f} | "
                            f"단기스토 {s.stoch_k_short:.0f} | 중기스토 {s.stoch_k_mid:.0f} | {s.total}점"
                        )
                await _bot.send_message(
                    chat_id=CHAT_ID,
                    text="\n".join(alert_lines),
                    parse_mode="Markdown"
                )

        # 5. PDF 생성
        theme_news_map = build_theme_news_map(news_items, THEME_KEYWORDS)
        hot_kw_map     = build_hot_keyword_map(news_items)
        tp_list        = fetch_target_price_changes()   # 신규

        pdf_path = generate_report(
            stock_results=stock_results,
            positive_news=positive_news,
            negative_news=negative_news,
            trading_day=trading_day,
            scores=scores,
            themes=themes,
            theme_news_map=theme_news_map,
            hot_kw_map=hot_kw_map,
            tp_list=tp_list,   # 신규
        )

        # 6. 요약 메시지
        d   = datetime.strptime(trading_day, "%Y%m%d")
        now = datetime.now()
        trading_day_date = d.date()
        is_today = trading_day_date == now.date()

        if is_today:
            day_label = f"📅 {d.strftime('%Y-%m-%d')} (오늘)"
        elif now.weekday() >= 5:
            day_label = f"📅 {d.strftime('%Y-%m-%d')} 기준 _(오늘은 주말 휴장)_"
        else:
            day_label = f"📅 {d.strftime('%Y-%m-%d')} 기준 _(오늘은 공휴일 휴장)_"

        theme_lines = ""
        if themes:
            theme_lines = "\n\n🔥 *오늘의 테마*\n" + "\n".join(
                f"  {t.direction} {t.theme_name} ({t.news_count}건)" for t in themes[:3]
            )

        score_lines = ""
        if scores:
            score_lines = "\n\n🎯 *점수 TOP 3*\n" + "\n".join(
                f"  {s.name} *{s.total}점* {s.grade.strip()}" for s in scores[:3]
            )

        summary = (
            f"📋 *KRX 스캔 리포트* — {now.strftime('%H:%M')}\n"
            f"{day_label}\n\n"
            f"📊 주식 조건 만족: *{len(stock_results)}종목*\n"
            f"🟢 긍정 뉴스 이슈: *{len(positive_news)}종목*\n"
            f"🔴 부정 뉴스 이슈: *{len(negative_news)}종목*"
            f"{theme_lines}"
            f"{score_lines}\n\n"
            f"아래 PDF 파일을 확인하세요 👇"
        )
        await _bot.send_message(chat_id=CHAT_ID, text=summary, parse_mode="Markdown")

        # 7. PDF 전송
        filename = f"KRX_리포트_{now.strftime('%Y%m%d_%H%M')}.pdf"
        with open(pdf_path, "rb") as f:
            await _bot.send_document(
                chat_id=CHAT_ID, document=f, filename=filename,
                caption=f"📄 KRX 스캔 리포트 ({now.strftime('%Y-%m-%d %H:%M')})"
            )
        logger.info("PDF 전송 완료")

    except Exception as e:
        logger.error("스캔 오류: %s", str(e))
        await _bot.send_message(chat_id=CHAT_ID, text="⚠️ 스캔 중 오류 발생: " + str(e))


# ────────────────────────────────────────────────
# 스케줄 함수
# ────────────────────────────────────────────────
async def scheduled_weekday_scan(bot: Bot = None):
    if not _is_trading_day():
        logger.info("평일 스캔 스킵 (공휴일)")
        return
    await run_full_scan(bot=bot)


async def scheduled_weekend_scan(bot: Bot = None):
    if _is_trading_day():
        logger.info("주말 스캔 스킵 (거래일)")
        return
    await run_full_scan(bot=bot)


# ────────────────────────────────────────────────
# 명령어 핸들러
# ────────────────────────────────────────────────
async def cmd_scan(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 스캔을 시작합니다!\n"
        "주식 조건 스캔 → 뉴스 이슈 스캔 → 점수 계산 → PDF 리포트 생성\n"
        "⏳ 10~20분 정도 소요됩니다."
    )
    await run_full_scan(bot=context.bot)


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    is_trading = _is_trading_day()
    status = "📈 오늘은 거래일입니다." if is_trading else "💤 오늘은 휴장일입니다."
    await update.message.reply_text(
        f"👋 *KRX 주식 스캐너 봇*\n\n"
        f"{status}\n\n"
        "⏰ *자동 스캔 스케줄:*\n"
        f"평일 (거래일): {' / '.join(WEEKDAY_SCAN_TIMES)}\n"
        f"주말·공휴일: {' / '.join(WEEKEND_SCAN_TIMES)}\n\n"
        "📌 *명령어:*\n"
        "/scan — 즉시 전체 스캔 + PDF\n"
        "/theme — 오늘의 테마 이슈\n"
        "/status — 봇 상태\n"
        "/help — 도움말",
        parse_mode="Markdown"
    )


async def cmd_status(update, context: ContextTypes.DEFAULT_TYPE):
    trading_day = scanner._latest_trading_day()
    d = datetime.strptime(trading_day, "%Y%m%d")
    is_trading = _is_trading_day()
    await update.message.reply_text(
        f"✅ 봇 정상 작동 중\n"
        f"📅 오늘 상태: {'📈 거래일' if is_trading else '💤 휴장일'}\n"
        f"📅 최근 거래일: {d.strftime('%Y-%m-%d')}\n\n"
        f"⏰ 평일 스캔: {' / '.join(WEEKDAY_SCAN_TIMES)}\n"
        f"⏰ 주말 스캔: {' / '.join(WEEKEND_SCAN_TIMES)}",
        parse_mode="Markdown"
    )


async def cmd_theme(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 테마 분석 중...")
    try:
        news_items = fetch_all_news()
        themes = classify_news_to_themes_with_gpt(news_items)
        hot_kw     = count_hot_keywords(news_items)

        lines = ["🔥 *오늘의 테마 이슈*\n"]
        for i, t in enumerate(themes[:8], 1):
            lines.append(
                f"*{i}. {t.theme_name}*  {t.direction}\n"
                f"  키워드: {', '.join(t.matched_keywords)}\n"
                f"  섹터: {' · '.join(t.related_sectors)}  |  뉴스: {t.news_count}건\n"
            )
        if hot_kw:
            lines.append("\n📊 *핫 키워드*")
            lines.append("  " + "  ".join(f"#{kw}({cnt})" for kw, cnt in hot_kw[:5]))

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 오류: {e}")


async def cmd_help(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *도움말*\n\n"
        "/scan — 즉시 전체 스캔 + PDF 리포트\n"
        "/theme — 오늘의 테마 이슈 + 핫 키워드\n"
        "/status — 봇 상태 및 스케줄 확인\n"
        "/help — 이 메시지",
        parse_mode="Markdown"
    )


# ────────────────────────────────────────────────
# 스케줄러 설정 — post_init으로 이벤트 루프 안에서 실행
# ────────────────────────────────────────────────
async def post_init(app: Application) -> None:
    """Application이 이벤트 루프를 띄운 뒤에 스케줄러 시작"""
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    for time_str in WEEKDAY_SCAN_TIMES:
        hour, minute = map(int, time_str.split(":"))
        scheduler.add_job(
            scheduled_weekday_scan, trigger="cron",
            day_of_week="mon-fri", hour=hour, minute=minute,
            kwargs={"bot": app.bot}
        )
        logger.info("평일 스캔 등록: %s (월~금)", time_str)

    for time_str in WEEKEND_SCAN_TIMES:
        hour, minute = map(int, time_str.split(":"))
        # 토·일
        scheduler.add_job(
            scheduled_weekend_scan, trigger="cron",
            day_of_week="sat,sun", hour=hour, minute=minute,
            kwargs={"bot": app.bot}
        )
        # 평일 공휴일 커버
        scheduler.add_job(
            scheduled_weekend_scan, trigger="cron",
            day_of_week="mon-fri", hour=hour, minute=minute,
            kwargs={"bot": app.bot}
        )
        logger.info("주말 스캔 등록: %s", time_str)

    scheduler.start()
    logger.info("스케줄러 시작 완료")


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────
def main():
    import requests, time

    # 웹훅 초기화
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": True},
            timeout=10
        )
        logger.info("웹훅 초기화 완료")
    except Exception as e:
        logger.warning("웹훅 초기화 실패 (무시): %s", e)

    # 이전 인스턴스 종료 대기 (Railway rolling deploy 대응)
    logger.info("이전 인스턴스 종료 대기 중... (15초)")
    time.sleep(15)

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("scan",   cmd_scan))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("theme",  cmd_theme))
    app.add_handler(CommandHandler("help",   cmd_help))

    logger.info("봇 시작")
    app.run_polling()


if __name__ == "__main__":
    main()