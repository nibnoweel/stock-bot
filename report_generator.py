"""
report_generator.py (업그레이드)
기존 SECTION 1~3 완전 유지
+ SECTION 4: 종목 점수 랭킹 (스토캐스틱 / 외인·기관 수급 / 점수)
+ SECTION 5: 테마 이슈 (매크로)
"""

import os
import logging
import glob

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

def _find_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]

FONT_REGULAR = _find_font(REGULAR_CANDIDATES)
FONT_BOLD    = _find_font(BOLD_CANDIDATES)

# 기존 색상 (유지)
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
# 신규 색상
COLOR_SCORE_HI = colors.HexColor("#E65100")   # 120점+
COLOR_SCORE_MD = colors.HexColor("#1A6FB5")   # 90점+
COLOR_BLUE_BG  = colors.HexColor("#E3F2FD")

def register_fonts() -> bool:
    regular = _find_font(REGULAR_CANDIDATES)
    bold    = _find_font(BOLD_CANDIDATES)
    logger.info("폰트 등록 성공 — Regular: %s / Bold: %s", regular, bold)

    if not regular:
        logger.warning("나눔폰트를 찾을 수 없습니다.")
        return False
    try:
        # encoding 명시 — 한글 유니코드 매핑 강제 적용
        pdfmetrics.registerFont(TTFont("NanumGothic",     regular, validate=True))
        pdfmetrics.registerFont(TTFont("NanumGothicBold", bold or regular, validate=True))
        pdfmetrics.registerFontFamily(
            "NanumGothic",
            normal="NanumGothic",
            bold="NanumGothicBold",
            italic="NanumGothic",
            boldItalic="NanumGothicBold",
        )
        return True
    except Exception as e:
        logger.warning("폰트 등록 실패: %s", e)
        return False


def get_styles(has_font):
    f  = "NanumGothic"        if has_font else "HYSMyeongJoStd-Medium"
    fb = "NanumGothicBold"    if has_font else "HYSMyeongJoStd-Medium"
    logger.info("스타일 폰트 적용: has_font=%s, f=%s, fb=%s", has_font, f, fb)
    base = {
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
        # 신규
        "cell":       ParagraphStyle("cell",       fontName=f,  fontSize=8,  textColor=COLOR_GRAY),
        "cell_b":     ParagraphStyle("cell_b",     fontName=fb, fontSize=8,  textColor=colors.black),
        "supply_p":   ParagraphStyle("supply_p",   fontName=f,  fontSize=8,  textColor=COLOR_POSITIVE),
        "supply_n":   ParagraphStyle("supply_n",   fontName=f,  fontSize=8,  textColor=COLOR_NEGATIVE),
        "theme_h":    ParagraphStyle("theme_h",    fontName=fb, fontSize=10, textColor=colors.black, spaceBefore=4),
        "score_hi":   ParagraphStyle("score_hi",   fontName=fb, fontSize=9,  textColor=COLOR_SCORE_HI),
        "score_md":   ParagraphStyle("score_md",   fontName=fb, fontSize=9,  textColor=COLOR_SCORE_MD),
    }
    return base


def section_header(text, bg_color, styles):
    tbl = Table([[Paragraph(text, styles["section"])]], colWidths=[170*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), bg_color),
        ("TOPPADDING",   (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING",  (0,0), (-1,-1), 12),
    ]))
    return tbl


# ── 기존 SECTION 1~3 함수 완전 유지 ─────────────

def indicator_text(r: dict) -> str:
    rsi_val    = r.get("rsi", "-")
    rsi_status = r.get("rsi_status", "")
    divergence = r.get("divergence", "없음")
    div_str = {"상승": "🔺 상승다이버전스", "하락": "🔻 하락다이버전스"}.get(divergence, "— 다이버전스 없음")
    rsi_str  = f"RSI {rsi_val} ({rsi_status})  {div_str}"
    gc   = "골든크로스 ✅" if r.get("golden_cross") else "골든크로스 없음"
    hist = "히스토그램 양전환 ✅" if r.get("hist_positive") else ""
    return rsi_str + "\n" + f"MACD {gc}" + (f"  |  {hist}" if hist else "")


def build_stock_section(stock_results, styles):
    elements = []
    if not stock_results:
        elements.append(Paragraph("오늘 눌림목 신호가 없습니다.", styles["body"]))
        return elements
    f  = "NanumGothic"     if "NanumGothic"    in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica"
    fb = "NanumGothicBold" if "NanumGothicBold" in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica-Bold"
    header = ["종목명","코드","테마","현재가","등락률","고점대비","RSI","다이버전스","MACD"]
    col_w  = [26*mm,16*mm,20*mm,20*mm,16*mm,16*mm,12*mm,20*mm,18*mm]
    table_data = [header]
    for r in stock_results:
        div = r.get("divergence","없음")
        div_label = "🔺상승" if div=="상승" else ("🔻하락" if div=="하락" else "—")
        gc_label  = "GC✅" if r.get("golden_cross") else ("H+✅" if r.get("hist_positive") else "—")
        table_data.append([
            r["name"], r["code"], r.get("theme","-"),
            f"{r['close']:,}",
            f"{r['change_pct']:+.1f}%",
            f"{r['drop_from_high']:.1f}%",
            f"{r.get('rsi','-')}",
            div_label, gc_label,
        ])
    tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), COLOR_PRIMARY),
        ("TEXTCOLOR",    (0,0),(-1,0), colors.white),
        ("FONTNAME",     (0,0),(-1,0), fb), ("FONTSIZE",(0,0),(-1,-1),8),
        ("FONTNAME",     (0,1),(-1,-1),f),  ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("ALIGN",        (0,1),(0,-1),"LEFT"), ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),   ("LEFTPADDING",(0,1),(0,-1),4),
        *[("BACKGROUND",(0,i),(-1,i),COLOR_ACCENT) for i in range(2,len(table_data),2)],
        ("GRID",(0,0),(-1,-1),0.5,COLOR_DIVIDER),
        ("LINEBELOW",(0,0),(-1,0),1.5,COLOR_PRIMARY),
    ]))
    elements.append(tbl)
    return elements

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
            ("BACKGROUND",(0,0),(-1,-1),bg), ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),3), ("LEFTPADDING",(0,0),(-1,-1),10),
            ("RIGHTPADDING",(0,0),(-1,-1),10), ("LINEBELOW",(0,-1),(-1,-1),0.5,COLOR_DIVIDER),
        ]))
        elements.append(inner)
        elements.append(Spacer(1,3))
    return elements


def build_top_picks(stock_results, positive_news, negative_news, styles):
    elements = []
    pos_names   = {r["name"] for r in positive_news}
    neg_names   = {r["name"] for r in negative_news}
    pos_news_map = {r["name"]: r for r in positive_news}
    picks = [r for r in stock_results if r["name"] in pos_names and r["name"] not in neg_names]
    if not picks:
        elements.append(Paragraph("오늘은 기술적 조건과 긍정 뉴스가 동시에 해당하는 종목이 없습니다.", styles["body"]))
        return elements
    for r in picks:
        news_data = pos_news_map.get(r["name"], {})
        keywords  = news_data.get("keywords", [])
        news_list = news_data.get("news", [])
        div = r.get("divergence","없음")
        div_label = "🔺상승다이버전스" if div=="상승" else ("🔻하락다이버전스" if div=="하락" else "")
        gc_label  = "MACD 골든크로스✅" if r.get("golden_cross") else ""
        indicators = f"RSI {r.get('rsi','-')} ({r.get('rsi_status','')})  {div_label}  {gc_label}".strip()
        rows = [
            [Paragraph(f"★ {r['name']}  ({r['code']})", styles["gold_name"])],
            [Paragraph(f"📊 거래량 {r['volume_ratio']:.1f}배  |  {r['change_pct']:+.1f}%  |  200일선 +{r['ma200_gap']:.1f}%  |  현재가 {r['close']:,}원", styles["body"])],
            [Paragraph(f"📈 {indicators}", styles["indicator"])],
        ]
        if keywords:
            rows.append([Paragraph("📰 뉴스키워드: " + "  |  ".join(keywords), styles["kw_pos"])])
        for n in news_list:
            title = n["title"][:55] + ("..." if len(n["title"]) > 55 else "")
            rows.append([Paragraph(f"  • {title}  [{n['source']}]", styles["news_item"])])
        inner = Table(rows, colWidths=[166*mm])
        inner.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),COLOR_GOLD_BG), ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),4), ("LEFTPADDING",(0,0),(-1,-1),10),
            ("RIGHTPADDING",(0,0),(-1,-1),10), ("LINEBELOW",(0,-1),(-1,-1),1,COLOR_GOLD),
        ]))
        elements.append(inner)
        elements.append(Spacer(1,5))
    return elements


# ── 신규 SECTION 4: 점수 랭킹 테이블 ────────────

def _supply_fmt(val: float) -> tuple[str, str]:
    sign  = "+" if val >= 0 else ""
    arrow = "🔥" if val >= 50 else ("▲" if val > 0 else ("▼" if val < -50 else "•"))
    return f"{sign}{val:.1f}만{arrow}", ("supply_p" if val >= 0 else "supply_n")

def _stoch_color(signal: str) -> colors.Color:
    return {"과매수": COLOR_NEGATIVE, "과매도": COLOR_SCORE_MD,
            "상승": COLOR_SCORE_MD, "하락": COLOR_NEGATIVE}.get(signal, COLOR_GRAY)

def _score_color(score: int) -> colors.Color:
    if score >= 120: return COLOR_SCORE_HI
    if score >= 90:  return COLOR_SCORE_MD
    return COLOR_GRAY


def build_score_section(scores: list, styles: dict) -> list:
    """SECTION 4: 점수 랭킹 테이블 (3스토 과열 신호 포함)"""
    elements = []
    if not scores:
        elements.append(Paragraph("점수 산출 종목 없음", styles["body"]))
        return elements

    f  = "NanumGothic"     if "NanumGothic"    in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica"
    fb = "NanumGothicBold" if "NanumGothicBold" in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica-Bold"

    headers = ["종목명", "시총", "섹터", "외인10일", "기관10일", "RSI",
               "단기스토", "중기스토", "점수", "등급", "신호"]
    col_w   = [24*mm, 15*mm, 18*mm, 15*mm, 15*mm, 10*mm, 17*mm, 17*mm, 12*mm, 14*mm, 17*mm]

    table_data = [headers]
    for s in scores:
        f_txt, f_sty = _supply_fmt(s.foreign_10d)
        i_txt, i_sty = _supply_fmt(s.institution_10d)
        sc = s.total

        table_data.append([
            s.name,
            s.cap_label if hasattr(s, "cap_label") else "-",
            s.sector,
            f_txt,
            i_txt,
            f"{s.rsi:.0f}",
            f"{s.stoch_k_short:.0f} {s.stoch_short_signal}",
            f"{s.stoch_k_mid:.0f} {s.stoch_mid_signal}",
            f"{sc}점",
            s.grade.strip(),
            s.stoch_alert if hasattr(s, "stoch_alert") else "",
        ])

    tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), COLOR_PRIMARY),
        ("TEXTCOLOR",    (0,0),(-1,0), colors.white),
        ("FONTNAME",     (0,0),(-1,0), fb), ("FONTSIZE",(0,0),(-1,-1),8),
        ("FONTNAME",     (0,1),(-1,-1),f),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, COLOR_BLUE_BG]),
        ("GRID",         (0,0),(-1,-1),0.3,COLOR_DIVIDER),
        ("ALIGN",        (0,0),(-1,-1),"CENTER"),
        ("ALIGN",        (0,1),(1,-1),"LEFT"),
        ("TOPPADDING",   (0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",  (0,0),(-1,-1),4),
    ]))

    # 3스토 과열/침체 행 배경색 강조 (헤더=0번째 행 제외, 1번째부터)
    for idx, s in enumerate(scores, 1):
        if hasattr(s, "triple_overbought") and s.triple_overbought:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, idx), (-1, idx), COLOR_NEG_BG)]))
        elif hasattr(s, "triple_oversold") and s.triple_oversold:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, idx), (-1, idx), COLOR_POS_BG)]))

    elements.append(tbl)
    return elements

# ── SECTION 5: 테마 이슈 ────────────────────
def build_theme_section(themes: list, styles: dict, theme_news_map: dict = None) -> list:
    elements = []
    if not themes:
        elements.append(Paragraph("감지된 테마 이슈 없음", styles["body"]))
        return elements

    theme_news_map = theme_news_map or {}

    for i, t in enumerate(themes[:8], 1):
        dir_color = COLOR_POSITIVE if t.is_bullish else COLOR_NEGATIVE

        # ❗ 핵심 수정 부분
        dir_hex = safe_hex(dir_color)

        header_row = [[
            Paragraph(f"{i}.  {t.theme_name}", styles["theme_h"]),
            Paragraph(f"<font color='{dir_hex}'>{t.direction}</font>", styles["body"]),
        ]]

        header_tbl = Table(header_row, colWidths=[130*mm, 36*mm])
        header_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),COLOR_ACCENT),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(0,-1),8),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        elements.append(header_tbl)

        # 출처별 건수 집계
        headlines = theme_news_map.get(t.theme_name, [])
        source_counts: dict[str, int] = {}
        for h in headlines:
            src = h.get("source", "")
            source_counts[src] = source_counts.get(src, 0) + 1
        source_str = "  ".join(
            f"{src} {cnt}건" for src, cnt in
            sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
        )

        detail_rows = [
            ["감지 키워드:", "  ".join(t.matched_keywords)],
            ["관련 섹터:",   "  ".join(t.related_sectors)],
            ["뉴스 출처:",   source_str if source_str else f"{t.news_count}건"],
        ]
        d_tbl = Table(detail_rows, colWidths=[25*mm, 141*mm])
        d_tbl.setStyle(TableStyle([
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("FONTNAME",(0,0),(0,-1),"NanumGothic" if "NanumGothic" in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica"),
            ("TEXTCOLOR",(0,0),(0,-1),COLOR_GRAY),
            ("LEFTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING",(0,0),(-1,-1),2),
            ("BOTTOMPADDING",(0,0),(-1,-1),2),
        ]))
        elements.append(d_tbl)

        # 관련 헤드라인 출력
        if headlines:
            elements.append(Spacer(1, 2))
            for h in headlines:
                date   = h.get("date", "")
                source = h.get("source", "")
                title  = h.get("title", "")
                label  = f"[{source}] {date}  {title}"
                if len(label) > 80:
                    label = label[:79] + "…"
                elements.append(Paragraph(f"  • {label}", styles["news_item"]))

        elements.append(Spacer(1, 6))

    return elements

# ── SECTION 6: 핫 키워드 TOP N — 출처 건수 + 헤드라인 ────────────────────
def build_hot_keywords_section(hot_kw_map: list, styles: dict) -> list:
    """SECTION 6: 핫 키워드 TOP N — 출처 건수 + 헤드라인"""
    elements = []
    if not hot_kw_map:
        elements.append(Paragraph("핫 키워드 없음", styles["body"]))
        return elements

    for rank, item in enumerate(hot_kw_map, 1):
        kw      = item["keyword"]
        total   = item["total"]
        by_src  = item["by_source"]
        lines   = item["headlines"]

        # 출처별 건수 문자열
        src_str = "  ".join(
            f"{src} {cnt}건"
            for src, cnt in sorted(by_src.items(), key=lambda x: x[1], reverse=True)
        )

        header_row = [[
            Paragraph(f"#{rank}  {kw}  {total}건", styles["theme_h"]),
            Paragraph(src_str, styles["cell"]),
        ]]
        h_tbl = Table(header_row, colWidths=[50*mm, 116*mm])
        h_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),COLOR_GOLD_BG),
            ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        elements.append(h_tbl)

        for h in lines:
            date   = h.get("date", "")
            source = h.get("source", "")
            title  = h.get("title", "")
            label  = f"[{source}] {date}  {title}"
            if len(label) > 80:
                label = label[:79] + "…"
            elements.append(Paragraph(f"  • {label}", styles["news_item"]))

        elements.append(Spacer(1, 5))

    return elements

def build_target_price_section(tp_list: list, styles: dict) -> list:
    """SECTION 7: 증권사 목표주가 변동"""
    elements = []
    if not tp_list:
        elements.append(Paragraph("수집된 목표주가 변동 없음", styles["body"]))
        return elements

    f  = "NanumGothic"     if "NanumGothic"    in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica"
    fb = "NanumGothicBold" if "NanumGothicBold" in [x[0] for x in pdfmetrics.getRegisteredFontNames()] else "Helvetica-Bold"

    headers = ["방향", "종목명", "목표주가", "증권사", "핵심요약", "날짜"]
    col_w   = [14*mm, 28*mm, 22*mm, 22*mm, 70*mm, 14*mm]

    table_data = [headers]
    for item in tp_list:
        direction = item.get("direction", "유지")
        icon = {"상향": "🔺 상향", "하향": "🔻 하향", "신규": "🆕 신규"}.get(direction, "— 유지")
        target = f"{item['target']:,}원" if item.get("target") else "-"
        gap    = f"+{item['gap_pct']:.1f}%" if item.get("gap_pct") else "-"

        table_data.append([
            icon,
            item.get("name", "-"),
            target,
            item.get("firm", "-"),
            item.get("summary", "-")[:40],
            item.get("date", "-"),
        ])

    tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), COLOR_PRIMARY),
        ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
        ("FONTNAME",      (0,0),(-1,0), fb),
        ("FONTSIZE",      (0,0),(-1,-1), 8),
        ("FONTNAME",      (0,1),(-1,-1), f),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, COLOR_BLUE_BG]),
        ("GRID",          (0,0),(-1,-1), 0.3, COLOR_DIVIDER),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("ALIGN",         (1,1),(1,-1),  "LEFT"),
        ("ALIGN",         (4,1),(4,-1),  "LEFT"),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
    ]))
    elements.append(tbl)
    return elements

# ✅ 추가: 안전한 HEX 변환 함수
def safe_hex(color_obj):
    raw = color_obj.hexval()
    if raw.startswith("0x"):
        return "#" + raw[2:]
    if raw.startswith("#"):
        return raw
    return "#" + raw
    
# ── 메인 generate_report (기존 시그니처 완전 유지) ──

def generate_report(
    stock_results,
    positive_news,
    negative_news,
    trading_day,
    output_path="/tmp/stock_report.pdf",
    scores=None,
    themes=None,
    theme_news_map=None,   # 신규
    hot_kw_map=None,       # 신규
    tp_list=None,       # 신규: 목표주가 변동
):
    has_font = register_fonts()
    styles   = get_styles(has_font)
    logger.info("generate_report has_font=%s", has_font)
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

    pos_names   = {r["name"] for r in positive_news}
    neg_names   = {r["name"] for r in negative_news}
    picks_count = len([r for r in stock_results if r["name"] in pos_names and r["name"] not in neg_names])

    story = []

    # ── 헤더 ─────────────────────────────────────
    story.append(Paragraph("KRX 주식 스캔 리포트", styles["title"]))
    story.append(Paragraph(f"생성: {date_str}  |  기준 거래일: {base_date}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY, spaceAfter=8))

    # ── 요약 박스 ─────────────────────────────────
    summary_items = [
        Paragraph(f"기술적 조건\n{len(stock_results)}종목",  styles["body"]),
        Paragraph(f"긍정 뉴스\n{len(positive_news)}종목",    styles["body"]),
        Paragraph(f"부정 뉴스\n{len(negative_news)}종목",    styles["body"]),
        Paragraph(f"⭐ 오늘의 종목\n{picks_count}종목",       styles["body"]),
    ]
    if scores:
        summary_items.append(Paragraph(f"점수 랭킹\n{len(scores)}종목", styles["body"]))
    if themes:
        summary_items.append(Paragraph(f"테마 이슈\n{len(themes)}개", styles["body"]))

    col_n = len(summary_items)
    col_w_each = 168 / col_n
    s_tbl = Table([summary_items], colWidths=[col_w_each*mm]*col_n)
    bg_list = [COLOR_ACCENT, COLOR_POS_BG, COLOR_NEG_BG, COLOR_GOLD_BG, COLOR_BLUE_BG, COLOR_ACCENT]
    s_tbl.setStyle(TableStyle([
        *[("BACKGROUND",(j,0),(j,0),bg_list[j % len(bg_list)]) for j in range(col_n)],
        ("ALIGN",(0,0),(-1,-1),"CENTER"), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),10),  ("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("GRID",(0,0),(-1,-1),0.5,COLOR_DIVIDER),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1,14))

    # ══ SECTION 1: 기술적 스캔 ═══════════════════
#     story.append(section_header("📊  SECTION 1  |  기술적 스캔 결과", COLOR_PRIMARY, styles))
    story.append(section_header("📊  SECTION 1  |  AI밸류체인 눌림목 포착", COLOR_PRIMARY, styles))
    story.append(Spacer(1,4))
    story.append(Paragraph(
#         "필터 조건: ① 거래량 2배↑  ② 전일대비 2%↑  ③ 200일선 +3% (5일연속)  ④ 윗꼬리<몸통&아랫꼬리  |  RSI·MACD는 참고용",
        "필터 조건: AI밸류체인 ① 최근20일 +15%↑ 선행상승  ② 고점대비 -5~-15% 조정  ③ 20일선 지지  ④ 60일선 위  ⑤ 반등신호",
        styles["indicator"]
    ))
    story.append(Spacer(1,4))
    for el in build_stock_section(stock_results, styles):
        story.append(el)
    story.append(Spacer(1,14))

    # ══ SECTION 2: 뉴스 이슈 ═════════════════════
    story.append(section_header("📰  SECTION 2  |  뉴스 이슈", COLOR_GRAY, styles))
    story.append(Spacer(1,4))
    story.append(Paragraph("🟢 긍정적 이슈", styles["body"]))
    story.append(Spacer(1,3))
    for el in build_news_block(positive_news, True, styles):
        story.append(el)
    story.append(Spacer(1,8))
    story.append(Paragraph("🔴 부정적 이슈", styles["body"]))
    story.append(Spacer(1,3))
    for el in build_news_block(negative_news, False, styles):
        story.append(el)
    story.append(Spacer(1,14))

    # ══ SECTION 3: 오늘의 종목 ═══════════════════
#     story.append(section_header("⭐  SECTION 3  |  오늘의 종목  (기술적 조건 ∩ 긍정뉴스, 부정뉴스 제외)", COLOR_GOLD, styles))
#     story.append(Spacer(1,4))
#     for el in build_top_picks(stock_results, positive_news, negative_news, styles):
#         story.append(el)

    # ══ SECTION 4: 종목 점수 랭킹 (선택) ══════════
    if scores:
        story.append(PageBreak())
        story.append(section_header(
            "🎯  SECTION 4  |  종목 점수 랭킹  (스토캐스틱 · 외인/기관 수급 · 종합점수)",
            COLOR_PRIMARY, styles
        ))
        story.append(Spacer(1,4))
        story.append(Paragraph(
            "점수 구성: RSI(20) + 스토캐스틱(20) + MACD(15) + 외인수급(20) + 기관수급(20) + 뉴스감성(25) + 테마이슈(10) + 가격모멘텀(20) = 150점 만점",
            styles["indicator"]
        ))
        story.append(Spacer(1,4))
        for el in build_score_section(scores, styles):
            story.append(el)
        story.append(Spacer(1,14))

    # ══ SECTION 5: 테마 이슈 (선택) ═══════════════
    if themes:
        story.append(section_header(
            "🔥  SECTION 5  |  오늘의 매크로 테마 이슈",
            COLOR_GRAY, styles
        ))
        story.append(Spacer(1,4))
        for el in build_theme_section(themes, styles, theme_news_map):
            story.append(el)
        story.append(Spacer(1,14))
    # ══ SECTION 6: 핫 키워드 ═══════════════════
    if hot_kw_map:
        story.append(section_header(
            "📊  SECTION 6  |  핫 키워드 TOP 8",
            COLOR_PRIMARY, styles
        ))
        story.append(Spacer(1,4))
        for el in build_hot_keywords_section(hot_kw_map, styles):
            story.append(el)
        story.append(Spacer(1,14))
    # ══ SECTION 7: 목표주가 변동 ═══════════════
    if tp_list:
        story.append(section_header(
            "✨  SECTION 7  |  증권사 목표주가 변동",
            COLOR_GOLD, styles
        ))
        story.append(Spacer(1,4))
        for el in build_target_price_section(tp_list, styles):
            story.append(el)
        story.append(Spacer(1,14))
    # ── 푸터 ─────────────────────────────────────
    story.append(Spacer(1,16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_DIVIDER))
    story.append(Spacer(1,4))
    story.append(Paragraph(
        f"본 리포트는 자동 생성된 참고용 자료입니다.  |  {date_str}  |  KRX 주식 스캐너 봇",
        styles["footer"]
    ))

    doc.build(story)
    logger.info("PDF 생성 완료: %s", output_path)
    return output_path
