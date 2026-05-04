"""
report_generator.py  (업그레이드 버전)
PDF 이슈 리포트 생성 — 참고 PDF 레이아웃 재현
섹션:
  1. 오늘의 매크로 이슈 (테마별)
  2. 핫 키워드 TOP 8
  3. 텔레그램 채널 인텔리전스 (목표주가)
  4. 대통령/정부 정책 동향 (섹터별)
  5. 정책 관전 종목 (종목 카드: 외인/기관/RSI/스토캐스틱/점수)
"""

import os
import io
from datetime import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from scorer import StockScore
from sector_theme import ThemeIssue, count_hot_keywords

# ── 한글 폰트 등록 ──────────────────────────────
_FONT_PATHS = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/app/fonts/NanumGothic.ttf",
    "./fonts/NanumGothic.ttf",
]

def _register_fonts():
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("NanumGothic", path))
                pdfmetrics.registerFont(TTFont("NanumGothicBold", path.replace("Gothic", "GothicBold")))
                return "NanumGothic", "NanumGothicBold"
            except Exception:
                pass
    # 폴백: 기본 폰트
    return "Helvetica", "Helvetica-Bold"

FONT_REGULAR, FONT_BOLD = _register_fonts()

# ── 색상 팔레트 ──────────────────────────────────
C_ORANGE  = colors.HexColor("#E8530A")   # 헤더/강조 (상승)
C_BLUE    = colors.HexColor("#1A6FB5")   # 파랑 (섹터/수급 양)
C_RED     = colors.HexColor("#D42B2B")   # 빨강 (하락/손실)
C_GRAY    = colors.HexColor("#555555")
C_LIGHT   = colors.HexColor("#F5F5F5")
C_WHITE   = colors.white
C_BLACK   = colors.black
C_BORDER  = colors.HexColor("#DDDDDD")
C_HEADER_BG = colors.HexColor("#FFF3ED")
C_CARD_BG   = colors.HexColor("#FAFAFA")

W, H = A4  # 595 × 842 pt


# ────────────────────────────────────────────────
# 스타일 정의
# ────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    def S(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent],
                              fontName=kw.pop("fontName", FONT_REGULAR), **kw)
    return {
        "title":    S("title",    fontSize=16, fontName=FONT_BOLD,    textColor=C_ORANGE, spaceAfter=4),
        "subtitle": S("subtitle", fontSize=10, textColor=C_GRAY,      spaceAfter=8),
        "section":  S("section",  fontSize=13, fontName=FONT_BOLD,    textColor=C_BLACK,  spaceBefore=10, spaceAfter=4),
        "theme_h":  S("theme_h",  fontSize=11, fontName=FONT_BOLD,    textColor=C_BLACK),
        "theme_s":  S("theme_s",  fontSize=9,  textColor=C_GRAY),
        "kw_lbl":   S("kw_lbl",   fontSize=8,  textColor=C_BLUE,      fontName=FONT_BOLD),
        "body":     S("body",     fontSize=9,  textColor=C_GRAY,      spaceAfter=2),
        "stock_n":  S("stock_n",  fontSize=9,  fontName=FONT_BOLD,    textColor=C_ORANGE),
        "score_hi": S("score_hi", fontSize=9,  fontName=FONT_BOLD,    textColor=C_ORANGE),
        "score_lo": S("score_lo", fontSize=9,  fontName=FONT_BOLD,    textColor=C_GRAY),
        "cell":     S("cell",     fontSize=8,  textColor=C_GRAY),
        "cell_b":   S("cell_b",   fontSize=8,  fontName=FONT_BOLD,    textColor=C_BLACK),
        "supply_p": S("supply_p", fontSize=8,  textColor=C_BLUE),
        "supply_n": S("supply_n", fontSize=8,  textColor=C_RED),
    }


# ────────────────────────────────────────────────
# 공통 유틸
# ────────────────────────────────────────────────

def _hr(width=None, color=C_BORDER, thickness=0.5):
    return HRFlowable(width=width or "100%", thickness=thickness,
                      color=color, spaceAfter=4, spaceBefore=4)


def _supply_fmt(val: float) -> tuple[str, str]:
    """수급 만주 → (표시문자열, 색상키)"""
    sign = "+" if val >= 0 else ""
    arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
    return f"{sign}{val:.1f}만{arrow}", ("supply_p" if val >= 0 else "supply_n")


def _stoch_color(signal: str) -> colors.Color:
    if "과매수" in signal: return C_RED
    if "과매도" in signal: return C_BLUE
    if "상승" in signal:  return C_BLUE
    if "하락" in signal:  return C_RED
    return C_GRAY


def _score_color(score: int) -> colors.Color:
    if score >= 120: return C_ORANGE
    if score >= 90:  return C_BLUE
    if score >= 60:  return C_GRAY
    return colors.HexColor("#AAAAAA")


# ────────────────────────────────────────────────
# 섹션 빌더
# ────────────────────────────────────────────────

def _build_header(ST: dict, collected_at: str, news_count: int) -> list:
    elems = []
    elems.append(Paragraph("📋 오늘의 이슈 리포트", ST["title"]))
    elems.append(Paragraph(
        f"조회 시간: {collected_at}　|　수집 뉴스: 총 {news_count}건",
        ST["subtitle"]
    ))
    elems.append(_hr(thickness=1, color=C_ORANGE))
    return elems


def _build_theme_section(ST: dict, themes: list[ThemeIssue]) -> list:
    elems = []
    elems.append(Paragraph("🔥 오늘의 매크로 이슈", ST["section"]))
    elems.append(_hr())

    for i, theme in enumerate(themes[:8], 1):
        arrow_color = C_ORANGE if theme.is_bullish else C_RED
        direction_para = Paragraph(
            f"<font color='#{arrow_color.hexval()[1:]}'>　{theme.direction}</font>",
            ST["body"]
        )

        header_table = Table(
            [[Paragraph(f"{i}　{theme.theme_name}", ST["theme_h"]), direction_para]],
            colWidths=[120*mm, 40*mm]
        )
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), C_LIGHT),
            ("BOX", (0,0), (-1,-1), 0.3, C_BORDER),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING", (0,0), (0,-1), 6),
        ]))
        elems.append(header_table)

        kw_text = "　".join(f"<b>{kw}</b>" for kw in theme.matched_keywords)
        sector_text = "　".join(
            f"<font color='#{C_BLUE.hexval()[1:]}'>{s}</font>"
            for s in theme.related_sectors
        )

        detail_data = [
            ["감지 키워드:", Paragraph(kw_text, ST["kw_lbl"])],
            ["관련 섹터:",   Paragraph(sector_text, ST["kw_lbl"])],
            ["뉴스 출처:",   Paragraph(f"{theme.news_count}건", ST["cell"])],
        ]
        if theme.summary:
            detail_data.insert(0, ["요약:", Paragraph(theme.summary, ST["body"])])

        detail_table = Table(detail_data, colWidths=[30*mm, 130*mm])
        detail_table.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (0,-1), 12),
            ("TOPPADDING", (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("TEXTCOLOR", (0,0), (0,-1), C_GRAY),
            ("FONTNAME", (0,0), (0,-1), FONT_REGULAR),
            ("FONTSIZE", (0,0), (0,-1), 8),
        ]))
        elems.append(detail_table)
        elems.append(Spacer(1, 4*mm))

    return elems


def _build_hot_keywords(ST: dict, keywords: list[tuple[str, int]]) -> list:
    elems = []
    elems.append(Paragraph("📊 핫 키워드 TOP 8", ST["section"]))
    elems.append(_hr())

    rows = []
    for rank, (kw, cnt) in enumerate(keywords, 1):
        rows.append([
            Paragraph(f"#{rank}", ST["cell_b"]),
            Paragraph(f"<b>{kw}</b>", ST["cell_b"]),
            Paragraph(f"{cnt}건", ST["cell"]),
        ])

    if rows:
        kw_table = Table(rows, colWidths=[15*mm, 50*mm, 20*mm])
        kw_table.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [C_WHITE, C_LIGHT]),
            ("GRID", (0,0), (-1,-1), 0.3, C_BORDER),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
        ]))
        elems.append(kw_table)
    elems.append(Spacer(1, 4*mm))
    return elems


def _build_stock_cards(ST: dict, scores: list[StockScore]) -> list:
    """
    정책 관전 종목 카드 테이블
    컬럼: 시장, 종목명, 시총, 외인10일, 기관10일, RSI, 단기스토, 중기스토, 점수, 기술지표
    """
    elems = []
    elems.append(Paragraph("🎯 정책 관전 종목 (점수 상위)", ST["section"]))
    elems.append(_hr())

    # 헤더
    headers = ["시장", "종목명", "외인\n10일", "기관\n10일", "RSI",
               "단기스토", "중기스토", "점수", "등급"]
    col_w = [14*mm, 34*mm, 18*mm, 18*mm, 12*mm, 22*mm, 22*mm, 14*mm, 18*mm]

    table_data = [headers]
    for s in scores:
        f_txt, f_sty = _supply_fmt(s.foreign_10d)
        i_txt, i_sty = _supply_fmt(s.institution_10d)

        row = [
            Paragraph(getattr(s, "market", "KOSPI"), ST["cell"]),
            Paragraph(f"<b>{s.name}</b>", ST["stock_n"]),
            Paragraph(f_txt, ST[f_sty]),
            Paragraph(i_txt, ST[i_sty]),
            Paragraph(f"{s.rsi:.0f}", ST["cell_b"]),
            Paragraph(
                f"<font color='#{_stoch_color(s.stoch_short_signal).hexval()[1:]}'>"
                f"{s.stoch_k_short:.0f} {s.stoch_short_signal}</font>",
                ST["cell"]
            ),
            Paragraph(
                f"<font color='#{_stoch_color(s.stoch_mid_signal).hexval()[1:]}'>"
                f"{s.stoch_k_mid:.0f} {s.stoch_mid_signal}</font>",
                ST["cell"]
            ),
            Paragraph(
                f"<font color='#{_score_color(s.total).hexval()[1:]}'>"
                f"<b>{s.total}점</b></font>",
                ST["cell_b"]
            ),
            Paragraph(s.grade(), ST["cell"]),
        ]
        table_data.append(row)

    card_table = Table(table_data, colWidths=col_w, repeatRows=1)
    card_table.setStyle(TableStyle([
        # 헤더
        ("BACKGROUND",   (0,0), (-1,0), C_ORANGE),
        ("TEXTCOLOR",    (0,0), (-1,0), C_WHITE),
        ("FONTNAME",     (0,0), (-1,0), FONT_BOLD),
        ("FONTSIZE",     (0,0), (-1,0), 8),
        ("ALIGN",        (0,0), (-1,0), "CENTER"),
        # 데이터 행
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_WHITE, C_CARD_BG]),
        ("GRID",         (0,0), (-1,-1), 0.3, C_BORDER),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        # 점수 컬럼 (7번) 가운데 정렬
        ("ALIGN",        (7,0), (7,-1), "CENTER"),
    ]))
    elems.append(card_table)
    elems.append(Spacer(1, 4*mm))
    return elems


def _build_score_breakdown(ST: dict, scores: list[StockScore], top_n: int = 5) -> list:
    """상위 5종목 점수 상세 분해"""
    elems = []
    elems.append(Paragraph("🔍 점수 상세 분석 (TOP 5)", ST["section"]))
    elems.append(_hr())

    breakdown_headers = ["항목", "배점", "점수", "비율"]
    for s in scores[:top_n]:
        elems.append(Paragraph(f"▶ {s.name} ({s.code})  총점 {s.total}점  {s.grade()}", ST["theme_h"]))
        rows = [
            breakdown_headers,
            ["RSI",        "20", str(s.rsi_score),         _pct(s.rsi_score,        20)],
            ["스토캐스틱", "20", str(s.stoch_score),        _pct(s.stoch_score,       20)],
            ["MACD",       "15", str(s.macd_score),         _pct(s.macd_score,        15)],
            ["외인수급",   "20", str(s.foreign_score),      _pct(s.foreign_score,     20)],
            ["기관수급",   "20", str(s.institution_score),  _pct(s.institution_score, 20)],
            ["뉴스감성",   "25", str(s.news_score),         _pct(s.news_score,        25)],
            ["테마이슈",   "10", str(s.theme_score),        _pct(s.theme_score,       10)],
            ["가격모멘텀", "20", str(s.price_score),        _pct(s.price_score,       20)],
            ["합계",      "150", str(s.total),              _pct(s.total,            150)],
        ]
        t = Table(rows, colWidths=[40*mm, 20*mm, 20*mm, 30*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0), C_LIGHT),
            ("FONTNAME",     (0,0), (-1,0), FONT_BOLD),
            ("FONTSIZE",     (0,0), (-1,-1), 8),
            ("GRID",         (0,0), (-1,-1), 0.3, C_BORDER),
            ("ALIGN",        (1,0), (-1,-1), "CENTER"),
            ("BACKGROUND",   (0,-1), (-1,-1), C_HEADER_BG),
            ("FONTNAME",     (0,-1), (-1,-1), FONT_BOLD),
            ("TOPPADDING",   (0,0), (-1,-1), 2),
            ("BOTTOMPADDING",(0,0), (-1,-1), 2),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 4*mm))

    return elems


def _pct(score: int, max_score: int) -> str:
    return f"{score/max_score*100:.0f}%"


# ────────────────────────────────────────────────
# 메인 생성 함수
# ────────────────────────────────────────────────

def generate_report(
    themes: list[ThemeIssue],
    scores: list[StockScore],
    news_texts: list[str],
    news_count: int = 0,
    output_path: str = "오늘의종목.pdf",
) -> str:
    """
    PDF 리포트 생성 후 파일 경로 반환
    """
    collected_at = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    ST = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    story = []

    # 1. 헤더
    story += _build_header(ST, collected_at, news_count)
    story.append(Spacer(1, 5*mm))

    # 2. 매크로 이슈
    story += _build_theme_section(ST, themes)
    story.append(PageBreak())

    # 3. 핫 키워드
    hot_kw = count_hot_keywords(news_texts)
    story += _build_hot_keywords(ST, hot_kw)
    story.append(Spacer(1, 4*mm))

    # 4. 종목 카드 테이블
    story += _build_stock_cards(ST, scores)
    story.append(PageBreak())

    # 5. 점수 상세
    story += _build_score_breakdown(ST, scores)

    # 6. 푸터
    story.append(_hr(thickness=0.5))
    story.append(Paragraph(
        f"오늘의 이슈 리포트 · 자동 생성 · {collected_at}",
        ParagraphStyle("footer", fontName=FONT_REGULAR, fontSize=7,
                       textColor=C_GRAY, alignment=1)
    ))

    doc.build(story)
    return output_path


# ────────────────────────────────────────────────
# 텔레그램 전송용 텍스트 요약
# ────────────────────────────────────────────────

def build_telegram_summary(
    themes: list[ThemeIssue],
    scores: list[StockScore],
    top_n: int = 10,
) -> str:
    """
    텔레그램 메시지용 짧은 요약 텍스트 생성
    """
    lines = []
    now = datetime.now().strftime("%m/%d %H:%M")
    lines.append(f"📋 *오늘의 이슈 리포트* — {now}\n")

    # 매크로 이슈
    if themes:
        lines.append("🔥 *매크로 이슈*")
        for i, t in enumerate(themes[:5], 1):
            lines.append(f"  {i}. {t.direction} {t.theme_name}  ({t.news_count}건)")
        lines.append("")

    # 상위 종목
    if scores:
        lines.append("🎯 *점수 상위 종목*")
        lines.append("`종목명       점수  RSI  외인   기관`")
        for s in scores[:top_n]:
            f_sign = "+" if s.foreign_10d >= 0 else ""
            i_sign = "+" if s.institution_10d >= 0 else ""
            lines.append(
                f"`{s.name[:8]:<8} {s.total:>4}점  "
                f"{s.rsi:>3.0f}  "
                f"{f_sign}{s.foreign_10d:>5.1f}만  "
                f"{i_sign}{s.institution_10d:>5.1f}만`"
            )

    return "\n".join(lines)
