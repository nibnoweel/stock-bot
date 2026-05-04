"""
bot.py  (업그레이드 버전)
텔레그램 봇 메인 진입점
파이프라인:
  1. 뉴스 RSS 수집 + 감성 분류        (news_scanner.py)
  2. 테마 이슈 분류                   (sector_theme.py)
  3. 전 종목 스캔 + 점수 계산          (scanner.py + scorer.py)
  4. PDF 리포트 생성                  (report_generator.py)
  5. 텔레그램 전송
"""

import asyncio
import logging
import os
from datetime import datetime

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    REPORT_TIME,           # "09:00"
    SCAN_TOP_N,            # 30
    MAX_SCAN_CODES,        # 500
)
from news_scanner import fetch_all_news, classify_sentiment, build_stock_sentiment_map
from sector_theme import classify_news_to_themes, count_hot_keywords
from scanner import scan_stocks
from report_generator import generate_report, build_telegram_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────
# 핵심 파이프라인
# ────────────────────────────────────────────────

async def run_daily_report(bot: Bot, chat_id: str):
    """매일 자동 실행되는 전체 리포트 파이프라인"""
    logger.info("=== 일일 리포트 파이프라인 시작 ===")

    try:
        # ── Step 1: 뉴스 수집 ─────────────────────
        await bot.send_message(chat_id=chat_id, text="📡 뉴스 수집 중...")
        news_items = fetch_all_news()       # [{title, link, source, published}, ...]
        news_texts = [n["title"] for n in news_items]
        logger.info(f"뉴스 수집: {len(news_items)}건")

        # ── Step 2: 감성 분류 + 종목별 매핑 ──────
        sentiments = [classify_sentiment(n["title"]) for n in news_items]
        stock_sentiment_map = build_stock_sentiment_map(news_items)

        # ── Step 3: 테마 이슈 분류 ────────────────
        themes = classify_news_to_themes(news_texts)
        logger.info(f"테마 감지: {len(themes)}개")

        # ── Step 4: 전 종목 스캔 + 점수 계산 ─────
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔍 종목 스캔 중... (최대 {MAX_SCAN_CODES}종목)"
        )
        scores = scan_stocks(
            themes=themes,
            news_sentiment_map=stock_sentiment_map,
            top_n=SCAN_TOP_N,
            max_codes=MAX_SCAN_CODES,
        )
        logger.info(f"스캔 완료: 상위 {len(scores)}종목")

        # ── Step 5: PDF 생성 ──────────────────────
        report_path = f"/tmp/이슈리포트_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        generate_report(
            themes=themes,
            scores=scores,
            news_texts=news_texts,
            news_count=len(news_items),
            output_path=report_path,
        )
        logger.info(f"PDF 생성 완료: {report_path}")

        # ── Step 6: 텔레그램 전송 ─────────────────
        # 요약 텍스트
        summary = build_telegram_summary(themes, scores)
        await bot.send_message(
            chat_id=chat_id,
            text=summary,
            parse_mode="Markdown",
        )

        # PDF 파일
        with open(report_path, "rb") as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=os.path.basename(report_path),
                caption=f"📋 오늘의 이슈 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            )

        logger.info("=== 일일 리포트 전송 완료 ===")

    except Exception as e:
        logger.error(f"파이프라인 오류: {e}", exc_info=True)
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ 리포트 생성 중 오류 발생\n`{str(e)[:200]}`",
            parse_mode="Markdown",
        )


# ────────────────────────────────────────────────
# 텔레그램 명령어 핸들러
# ────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 KRX 주식 스캐너 봇\n\n"
        "/report — 지금 즉시 리포트 생성\n"
        "/top — 점수 상위 10종목 요약\n"
        "/theme — 오늘의 매크로 이슈\n"
        "/supply <종목코드> — 외인/기관 수급\n"
        "/score <종목코드> — 종목 점수 상세\n"
        "/status — 봇 상태 확인\n"
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """즉시 리포트 생성 명령"""
    await update.message.reply_text("⏳ 리포트 생성 시작... (2~5분 소요)")
    bot = context.bot
    chat_id = str(update.effective_chat.id)
    await run_daily_report(bot, chat_id)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """점수 상위 종목 빠른 조회"""
    await update.message.reply_text("⏳ 스캔 중...")
    try:
        news_items = fetch_all_news()
        news_texts = [n["title"] for n in news_items]
        stock_sentiment = build_stock_sentiment_map(news_items)
        themes = classify_news_to_themes(news_texts)

        scores = scan_stocks(
            themes=themes,
            news_sentiment_map=stock_sentiment,
            top_n=10,
            max_codes=200,
        )
        text = build_telegram_summary(themes, scores, top_n=10)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 오류: {e}")


async def cmd_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """오늘의 테마 이슈"""
    try:
        news_items = fetch_all_news()
        news_texts = [n["title"] for n in news_items]
        themes = classify_news_to_themes(news_texts)

        lines = ["🔥 *오늘의 매크로 이슈*\n"]
        for i, t in enumerate(themes[:8], 1):
            sectors = " · ".join(t.related_sectors)
            lines.append(
                f"*{i}. {t.theme_name}* {t.direction}\n"
                f"  키워드: {', '.join(t.matched_keywords)}\n"
                f"  섹터: {sectors}\n"
                f"  뉴스: {t.news_count}건\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 오류: {e}")


async def cmd_supply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """외인/기관 수급 조회: /supply 005930"""
    from supply_scanner import fetch_investor_data
    args = context.args
    if not args:
        await update.message.reply_text("사용법: /supply <종목코드>  예) /supply 005930")
        return

    code = args[0].zfill(6)
    try:
        data = fetch_investor_data(code, days=10)
        f10 = data["foreign"].sum() / 10000
        i10 = data["institution"].sum() / 10000
        ind10 = data["individual"].sum() / 10000

        f_sign  = "+" if f10  >= 0 else ""
        i_sign  = "+" if i10  >= 0 else ""
        id_sign = "+" if ind10 >= 0 else ""

        text = (
            f"📊 *{code} 10일 수급 현황*\n\n"
            f"🔵 외국인:  {f_sign}{f10:.1f}만주\n"
            f"🟠 기관:    {i_sign}{i10:.1f}만주\n"
            f"⚫ 개인:    {id_sign}{ind10:.1f}만주\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 수급 조회 실패: {e}")


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """종목 점수 상세: /score 005930"""
    from scanner import fetch_ohlcv
    from supply_scanner import fetch_investor_data
    from scorer import score_stock

    args = context.args
    if not args:
        await update.message.reply_text("사용법: /score <종목코드>  예) /score 005930")
        return

    code = args[0].zfill(6)
    try:
        ohlcv  = fetch_ohlcv(code)
        supply = fetch_investor_data(code)
        s = score_stock(
            code=code, name=code,
            ohlcv=ohlcv,
            foreign_series=supply["foreign"],
            institution_series=supply["institution"],
        )

        text = (
            f"🎯 *{code} 점수 상세*\n\n"
            f"총점: *{s.total}점*  {s.grade()}\n\n"
            f"```\n"
            f"RSI          {s.rsi_score:>3}/20   (RSI={s.rsi:.0f})\n"
            f"스토캐스틱   {s.stoch_score:>3}/20   단기={s.stoch_short_signal}\n"
            f"MACD         {s.macd_score:>3}/15\n"
            f"외인수급     {s.foreign_score:>3}/20   {s.foreign_10d:+.1f}만주\n"
            f"기관수급     {s.institution_score:>3}/20   {s.institution_10d:+.1f}만주\n"
            f"뉴스감성     {s.news_score:>3}/25\n"
            f"테마이슈     {s.theme_score:>3}/10\n"
            f"가격모멘텀   {s.price_score:>3}/20\n"
            f"────────────────\n"
            f"합계         {s.total:>3}/150\n"
            f"```"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 점수 조회 실패: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇 상태"""
    await update.message.reply_text(
        f"✅ 봇 정상 동작 중\n"
        f"🕐 현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📅 리포트 스케줄: 매일 {REPORT_TIME}"
    )


# ────────────────────────────────────────────────
# 스케줄러 설정
# ────────────────────────────────────────────────

def setup_scheduler(app: Application) -> AsyncIOScheduler:
    hour, minute = map(int, REPORT_TIME.split(":"))
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    async def scheduled_job():
        await run_daily_report(app.bot, TELEGRAM_CHAT_ID)

    scheduler.add_job(scheduled_job, "cron", hour=hour, minute=minute)
    return scheduler


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 핸들러 등록
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("report",  cmd_report))
    app.add_handler(CommandHandler("top",     cmd_top))
    app.add_handler(CommandHandler("theme",   cmd_theme))
    app.add_handler(CommandHandler("supply",  cmd_supply))
    app.add_handler(CommandHandler("score",   cmd_score))
    app.add_handler(CommandHandler("status",  cmd_status))

    # 스케줄러 시작
    scheduler = setup_scheduler(app)
    scheduler.start()
    logger.info(f"스케줄러 시작: 매일 {REPORT_TIME} KST")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
