"""
PDF 리포트 생성기
SECTION 1: 기술적 스캔
SECTION 2: 뉴스 이슈 (긍정/부정)
SECTION 3: 오늘의 종목 (기술적 + 긍정뉴스 교집합, 부정뉴스 제외)
"""

import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

FONT_DIR     = "/usr/share/fonts/truetype/nanum"
FONT_REGULAR = os.path.join(FONT_DIR, "NanumGothic.ttf")
FONT_BOLD    = os.path.join(FONT_DIR, "NanumGothicBold.ttf")

COLOR_PRIMARY  = colors.HexColor("#1A237E")
COLOR_POSITIVE = colors.HexColor("#1B5E20")
COLOR_NEGATIVE = colors.HexColor("#B71C1C")
COLOR_GOLD     = colors.HexColor("#E65100")
COLOR_ACCENT   = colors.HexColor("#E3F2FD")
COLOR_POS_BG   = colors.HexColor("#E8F5E9")
COLOR_NEG_BG   = colors.HexColor("#FFEBEE")
COLOR_GOLD_BG  = colors.HexColor("#FFF8E1")
COLOR_GRAY     = colors.HexColor("#607D8B")
COLOR_DIVIDER  = colors.HexColor("#CFD8DC")


def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("NanumGothic", FONT_REGULAR))
        pdfmetrics.registerFont(TTFont("NanumGothicBold", FONT_BOLD))
        return True
    except Exception as e:
        logger.warning("나눔폰트 로드 실패: %s", str(e))
        return False


def get_styles(has_font):
    f  = "NanumGothic"     if has_font else "Helvetica"
    fb = "NanumGothicBold" if has_font else "Helvetica-Bold"
    return {
        "title":      ParagraphStyle("title",      fontName=fb, fontSize=22, textColor=COLOR_PRIMARY, spaceAfter=4, leading=28),
        "subtitle":   ParagraphStyle("subtitle",   fontName=f,  fontSize=10, textColor=COLOR_GRAY, spaceAfter=2),
        "section":    ParagraphStyle("section",    fontName=fb, fontSize=13, textColor=colors.white, spaceAfter=4, leading=18),
        "stock_name": ParagraphStyle("stock_name", fontName=fb, fontSize=11, textColor=COLOR_PRIMARY, spaceAfter=1),
        "gold_name":  ParagraphStyle("gold_name",  fontName=fb, fontSize=11, textColor=COLOR_GOLD, spaceAfter=1),
        "body":       ParagraphStyle("body",       fontName=f,  fontSize=9,  textColor=colors.HexColor("#333"), spaceAfter=2, leading=13),
        "indicator":  ParagraphStyle("indicator",  fontName=f,  fontSize=8,  textColor=COLOR_GRAY, spaceAfter=1, leading=12),
        "kw_pos":     ParagraphStyle("kw_pos",     fontName=fb, fontSize=9,  textColor=COLOR_POSITIVE),
        "kw_neg":     ParagraphStyle("kw_neg",     fontName=fb, fontSize=9,  textColor=COLOR_NEGATIVE),
        "news_item":  ParagraphStyle("news_item",  fontName=f,  fontSize=8,  textColor=COLOR_GRAY, spaceAfter=1, leading=11),
        "footer":     ParagraphStyle("footer",     fontName=f,  fontSize=8,  textColor=COLOR_GRAY, alignment=1),
    }


def section_header(text, bg_color, styles):
    tbl = Table([[Paragraph(text, styles["section"])]], colWidths=[170*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), bg_color),
        ("TOPPADDING",   (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING",  (0,0), (-1,-1), 12),
    ]))
    return tbl


# ────────────────────────────────────────────
# RSI / MACD 참고 지표 텍스트 생성
# ────────────────────────────────────────────
def indicator_text(r: dict) -> str:
    # RSI
    rsi_val    = r.get("rsi", "-")
    rsi_status = r.get("rsi_status", "")
    divergence = r.get("divergence", "없음")

    if divergence == "상승":
        div_str = "🔺 상승다이버전스 (저점↓ RSI저점↑)"
    elif divergence == "하락":
        div_str = "🔻 하락다이버전스 (고점↑ RSI고점↓)"
    else:
        div_str = "— 다이버전스 없음"

    rsi_str = f"RSI {rsi_val} ({rsi_status})  {div_str}"

    # MACD
    gc   = "골든크로스 ✅" if r.get("golden_cross") else "골든크로스 없음"
    hist = "히스토그램 양전환 ✅" if r.get("hist_positive") else ""
    macd_str = f"MACD {gc}" + (f"  |  {hist}" if hist else "")

    return rsi_str + "\n" + macd_str


# ────────────────────────────────────────────
# SECTION 1: 기술적 스캔 테이블
# ────────────────────────────────────────────
def build_stock_section(stock_results, styles):
    elements = []
    if not stock_results:
        elements.append(Paragraph("조건을 만족하는 종목이 없습니다.", styles["body"]))
        return elements

    f  = "NanumGothic"     if "NanumGothic"     in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica"
    fb = "NanumGothicBold" if "NanumGothicBold"  in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica-Bold"

    header = ["종목명", "코드", "현재가", "등락률", "거래량비율", "200일선", "RSI", "다이버전스", "MACD"]
    col_w  = [30*mm, 16*mm, 20*mm, 16*mm, 20*mm, 18*mm, 14*mm, 22*mm, 18*mm]

    table_data = [header]
    for r in stock_results:
        div = r.get("divergence", "없음")
        div_label = "🔺상승" if div == "상승" else ("🔻하락" if div == "하락" else "—")
        gc_label  = "GC✅" if r.get("golden_cross") else ("H+✅" if r.get("hist_positive") else "—")
        table_data.append([
            r["name"],
            r["code"],
            f"{r['close']:,}",
            f"{r['change_pct']:+.1f}%",
            f"{r['volume_ratio']:.1f}배",
            f"+{r['ma200_gap']:.1f}%",
            f"{r.get('rsi', '-')}",
            div_label,
            gc_label,
        ])

    tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), COLOR_PRIMARY),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), fb),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("FONTNAME",     (0,1), (-1,-1), f),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("ALIGN",        (0,1), (0,-1), "LEFT"),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,1), (0,-1), 4),
        *[("BACKGROUND", (0,i), (-1,i), COLOR_ACCENT) for i in range(2, len(table_data), 2)],
        ("GRID",         (0,0), (-1,-1), 0.5, COLOR_DIVIDER),
        ("LINEBELOW",    (0,0), (-1,0), 1.5, COLOR_PRIMARY),
    ]))
    elements.append(tbl)
    return elements


# ────────────────────────────────────────────
# SECTION 2: 뉴스 이슈 블록
# ────────────────────────────────────────────
def build_news_block(news_results, is_positive, styles):
    elements = []
    bg       = COLOR_POS_BG if is_positive else COLOR_NEG_BG
    kw_style = styles["kw_pos"] if is_positive else styles["kw_neg"]
    icon     = "▲" if is_positive else "▼"

    if not news_results:
        elements.append(Paragraph("해당 이슈 종목 없음", styles["body"]))
        return elements

    for r in news_results:
        rows = [
            [Paragraph(f"{icon} {r['name']}  ({r['code']})", styles["stock_name"])],
            [Paragraph("키워드: " + "  |  ".join(r["keywords"]), kw_style)],
        ]
        for n in r["news"]:
            title = n["title"][:55] + ("..." if len(n["title"]) > 55 else "")
            rows.append([Paragraph(f"• {title}  [{n['source']}]", styles["news_item"])])

        inner = Table(rows, colWidths=[166*mm])
        inner.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), bg),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 3),
            ("LEFTPADDING",  (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("LINEBELOW",    (0,-1), (-1,-1), 0.5, COLOR_DIVIDER),
        ]))
        elements.append(inner)
        elements.append(Spacer(1, 3))
    return elements


# ────────────────────────────────────────────
# SECTION 3: 오늘의 종목
# ────────────────────────────────────────────
def build_top_picks(stock_results, positive_news, negative_news, styles):
    """기술적 조건 ∩ 긍정뉴스, 부정뉴스 제외"""
    elements = []

    # 긍정 뉴스 종목명 셋
    pos_names = {r["name"] for r in positive_news}
    # 부정 뉴스 종목명 셋 (제외 대상)
    neg_names = {r["name"] for r in negative_news}
    # 뉴스 데이터 딕셔너리
    pos_news_map = {r["name"]: r for r in positive_news}

    picks = [
        r for r in stock_results
        if r["name"] in pos_names and r["name"] not in neg_names
    ]

    if not picks:
        elements.append(Paragraph("오늘은 기술적 조건과 긍정 뉴스가 동시에 해당하는 종목이 없습니다.", styles["body"]))
        return elements

    for r in picks:
        news_data = pos_news_map.get(r["name"], {})
        keywords  = news_data.get("keywords", [])
        news_list = news_data.get("news", [])

        # 지표 한 줄 요약
        div = r.get("divergence", "없음")
        div_label = "🔺상승다이버전스" if div == "상승" else ("🔻하락다이버전스" if div == "하락" else "")
        gc_label  = "MACD 골든크로스✅" if r.get("golden_cross") else ""
        indicators = f"RSI {r.get('rsi','-')} ({r.get('rsi_status','')})  {div_label}  {gc_label}".strip()

        rows = [
            [Paragraph(f"★ {r['name']}  ({r['code']})", styles["gold_name"])],
            [Paragraph(
                f"📊 거래량 {r['volume_ratio']:.1f}배  |  {r['change_pct']:+.1f}%  |  200일선 +{r['ma200_gap']:.1f}%  |  현재가 {r['close']:,}원",
                styles["body"]
            )],
            [Paragraph(f"📈 {indicators}", styles["indicator"])],
        ]
        if keywords:
            rows.append([Paragraph("📰 뉴스키워드: " + "  |  ".join(keywords), styles["kw_pos"])])
        for n in news_list:
            title = n["title"][:55] + ("..." if len(n["title"]) > 55 else "")
            rows.append([Paragraph(f"  • {title}  [{n['source']}]", styles["news_item"])])

        inner = Table(rows, colWidths=[166*mm])
        inner.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), COLOR_GOLD_BG),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("LEFTPADDING",  (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("LINEBELOW",    (0,-1), (-1,-1), 1, COLOR_GOLD),
        ]))
        elements.append(inner)
        elements.append(Spacer(1, 5))

    return elements


# ────────────────────────────────────────────
# PDF 생성 메인
# ────────────────────────────────────────────
def generate_report(stock_results, positive_news, negative_news, trading_day,
                    output_path="/tmp/stock_report.pdf"):
    has_font = register_fonts()
    styles   = get_styles(has_font)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )

    date_str  = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    try:
        base_date = datetime.strptime(trading_day, "%Y%m%d").strftime("%Y년 %m월 %d일")
    except Exception:
        base_date = date_str

    # 오늘의 종목 수 계산
    pos_names = {r["name"] for r in positive_news}
    neg_names = {r["name"] for r in negative_news}
    picks_count = len([r for r in stock_results if r["name"] in pos_names and r["name"] not in neg_names])

    story = []

    # ── 헤더 ──────────────────────────────────
    story.append(Paragraph("KRX 주식 스캔 리포트", styles["title"]))
    story.append(Paragraph(f"생성: {date_str}  |  기준 거래일: {base_date}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY, spaceAfter=8))

    # ── 요약 박스 ─────────────────────────────
    summary_data = [[
        Paragraph(f"기술적 조건\n{len(stock_results)}종목",  styles["body"]),
        Paragraph(f"긍정 뉴스\n{len(positive_news)}종목",    styles["body"]),
        Paragraph(f"부정 뉴스\n{len(negative_news)}종목",    styles["body"]),
        Paragraph(f"⭐ 오늘의 종목\n{picks_count}종목",       styles["body"]),
    ]]
    s_tbl = Table(summary_data, colWidths=[42*mm]*4)
    s_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,0), COLOR_ACCENT),
        ("BACKGROUND",   (1,0), (1,0), COLOR_POS_BG),
        ("BACKGROUND",   (2,0), (2,0), COLOR_NEG_BG),
        ("BACKGROUND",   (3,0), (3,0), COLOR_GOLD_BG),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("GRID",         (0,0), (-1,-1), 0.5, COLOR_DIVIDER),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1, 14))

    # ══ SECTION 1: 기술적 스캔 ════════════════
    story.append(section_header("📊  SECTION 1  |  기술적 스캔 결과", COLOR_PRIMARY, styles))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "필터 조건: ① 거래량 2배↑  ② 전일대비 2%↑  ③ 200일선 +3% (5일연속)  ④ 윗꼬리<몸통&아랫꼬리  |  RSI·MACD는 참고용",
        styles["indicator"]
    ))
    story.append(Spacer(1, 4))
    for el in build_stock_section(stock_results, styles):
        story.append(el)
    story.append(Spacer(1, 14))

    # ══ SECTION 2: 뉴스 이슈 ═════════════════
    story.append(section_header("📰  SECTION 2  |  뉴스 이슈", COLOR_GRAY, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("🟢 긍정 이슈", styles["body"]))
    story.append(Spacer(1, 3))
    for el in build_news_block(positive_news, True, styles):
        story.append(el)
    story.append(Spacer(1, 8))

    story.append(Paragraph("🔴 부정 이슈", styles["body"]))
    story.append(Spacer(1, 3))
    for el in build_news_block(negative_news, False, styles):
        story.append(el)
    story.append(Spacer(1, 14))

    # ══ SECTION 3: 오늘의 종목 ═══════════════
    story.append(section_header("⭐  SECTION 3  |  오늘의 종목  (기술적 조건 ∩ 긍정뉴스, 부정뉴스 제외)", COLOR_GOLD, styles))
    story.append(Spacer(1, 4))
    for el in build_top_picks(stock_results, positive_news, negative_news, styles):
        story.append(el)

    # ── 푸터 ──────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_DIVIDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"본 리포트는 자동 생성된 참고용 자료입니다.  |  {date_str}  |  KRX 주식 스캐너 봇",
        styles["footer"]
    ))

    doc.build(story)
    logger.info("PDF 생성 완료: %s", output_path)
    return output_path
