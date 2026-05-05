import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ─────────────────────────────
# 폰트
# ─────────────────────────────
FONT_DIR     = "/usr/share/fonts/truetype/nanum"
FONT_REGULAR = os.path.join(FONT_DIR, "NanumGothic.ttf")
FONT_BOLD    = os.path.join(FONT_DIR, "NanumGothicBold.ttf")

# ─────────────────────────────
# 🎯 증권사 스타일 색상
# ─────────────────────────────
COLOR_PRIMARY  = colors.HexColor("#0B3C5D")
COLOR_POSITIVE = colors.HexColor("#D32F2F")  # 상승
COLOR_NEGATIVE = colors.HexColor("#1976D2")  # 하락
COLOR_TEXT     = colors.HexColor("#222222")
COLOR_SUBTEXT  = colors.HexColor("#666666")
COLOR_BG_LIGHT = colors.HexColor("#F7F9FB")
COLOR_BORDER   = colors.HexColor("#E0E0E0")
COLOR_DIVIDER  = colors.HexColor("#CFD8DC")

# 기타
COLOR_ACCENT   = colors.HexColor("#E3F2FD")
COLOR_POS_BG   = colors.HexColor("#E8F5E9")
COLOR_NEG_BG   = colors.HexColor("#FFEBEE")
COLOR_GOLD     = colors.HexColor("#E65100")
COLOR_GOLD_BG  = colors.HexColor("#FFF8E1")
COLOR_GRAY     = colors.HexColor("#607D8B")
COLOR_BLUE_BG  = colors.HexColor("#E3F2FD")

# ─────────────────────────────
# 폰트 등록
# ─────────────────────────────
def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("NanumGothic", FONT_REGULAR))
        pdfmetrics.registerFont(TTFont("NanumGothicBold", FONT_BOLD))
        return True
    except Exception as e:
        logger.warning("폰트 로드 실패: %s", str(e))
        return False

# ─────────────────────────────
# 스타일
# ─────────────────────────────
def get_styles(has_font):
    f  = "NanumGothic"     if has_font else "Helvetica"
    fb = "NanumGothicBold" if has_font else "Helvetica-Bold"

    return {
        "title": ParagraphStyle("title", fontName=fb, fontSize=22, textColor=COLOR_PRIMARY),
        "subtitle": ParagraphStyle("subtitle", fontName=f, fontSize=9, textColor=COLOR_SUBTEXT),
        "body": ParagraphStyle("body", fontName=f, fontSize=9, textColor=COLOR_TEXT),
        "footer": ParagraphStyle("footer", fontName=f, fontSize=8, textColor=COLOR_SUBTEXT, alignment=1),
    }

# ─────────────────────────────
# 안전 HEX 변환 (버그 해결 핵심)
# ─────────────────────────────
def safe_hex(color_obj):
    raw = color_obj.hexval()
    if raw.startswith("0x"):
        return "#" + raw[2:]
    if raw.startswith("#"):
        return raw
    return "#" + raw

# ─────────────────────────────
# KPI 카드
# ─────────────────────────────
def build_kpi_card(label, value):
    return Table([
        [Paragraph(f"<b>{value}</b>", ParagraphStyle(
            "kpi_v", fontName="NanumGothicBold", fontSize=16,
            alignment=1, textColor=COLOR_PRIMARY
        ))],
        [Paragraph(label, ParagraphStyle(
            "kpi_l", fontSize=8, alignment=1, textColor=COLOR_SUBTEXT
        ))]
    ], colWidths=[40*mm],
    style=TableStyle([
        ("BOX",(0,0),(-1,-1),0.5,COLOR_BORDER),
        ("BACKGROUND",(0,0),(-1,-1),colors.white),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))

# ─────────────────────────────
# 섹션 헤더 (증권사 스타일)
# ─────────────────────────────
def section_header(text):
    return Table([[
        "",
        Paragraph(text, ParagraphStyle(
            "sec", fontName="NanumGothicBold", fontSize=13, textColor=COLOR_TEXT
        ))
    ]], colWidths=[4*mm, 166*mm],
    style=TableStyle([
        ("BACKGROUND",(0,0),(0,-1), COLOR_PRIMARY),
        ("LEFTPADDING",(1,0),(1,-1),8),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))

# ─────────────────────────────
# 메인 리포트 생성
# ─────────────────────────────
def generate_report(
    stock_results,
    positive_news,
    negative_news,
    trading_day,
    output_path="/tmp/report.pdf",
    scores=None,
    themes=None,
    theme_news_map=None,
    hot_kw_map=None,
    tp_list=None
):
    has_font = register_fonts()
    styles = get_styles(has_font)

    doc = SimpleDocTemplate(output_path, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=20*mm, rightMargin=20*mm)

    story = []

    # 헤더
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph("KRX 주식 리포트", styles["title"]))
    story.append(Paragraph(f"{now}", styles["subtitle"]))
    story.append(Spacer(1,10))

    # KPI
    kpis = [
        build_kpi_card("기술", len(stock_results)),
        build_kpi_card("긍정", len(positive_news)),
        build_kpi_card("부정", len(negative_news)),
    ]
    story.append(Table([kpis], colWidths=[56*mm]*len(kpis)))
    story.append(Spacer(1,12))

    # SECTION 1
    story.append(section_header("📊 기술적 스캔"))
    story.append(Spacer(1,6))
    for r in stock_results[:10]:
        story.append(Paragraph(
            f"{r['name']} {r['change_pct']:+.1f}%",
            styles["body"]
        ))
        story.append(Spacer(1,4))

    # SECTION 2
    story.append(section_header("📰 뉴스"))
    story.append(Spacer(1,6))
    for r in positive_news[:5]:
        story.append(Paragraph(f"▲ {r['name']}", styles["body"]))

    # SECTION 5 (색상 버그 해결 포함)
    if themes:
        story.append(section_header("🔥 테마"))
        story.append(Spacer(1,6))
        for t in themes:
            color = COLOR_POSITIVE if t.is_bullish else COLOR_NEGATIVE
            hex_color = safe_hex(color)

            story.append(Paragraph(
                f"{t.theme_name} <font color='{hex_color}'><b>{t.direction}</b></font>",
                styles["body"]
            ))

    story.append(Spacer(1,20))
    story.append(Paragraph("자동 생성 리포트", styles["footer"]))

    doc.build(story)

    return output_path