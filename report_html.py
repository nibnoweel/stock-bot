"""
report_html.py
토스 스타일 HTML → PDF 리포트 (weasyprint)
"""

import logging
from datetime import datetime
from weasyprint import HTML

logger = logging.getLogger(__name__)

# 테마별 파스텔 색상
THEME_COLORS = {
    "반도체":     "#3182F6",   # 토스 블루
    "원전":       "#00C896",   # 그린
    "전력":       "#F5A623",   # 오렌지
    "로봇":       "#8B5CF6",   # 퍼플
    "데이터센터": "#FF6B6B",   # 레드
}

CSS = """
@page {
    size: A4;
    margin: 0;
}
* {
    margin: 0; padding: 0; box-sizing: border-box;
    font-family: 'NanumGothic', sans-serif;
}
body {
    background: #F2F4F6;
    color: #191F28;
    padding: 32px 28px;
    -weasy-font-feature-settings: "tnum";
}
.header {
    margin-bottom: 24px;
}
.header h1 {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
}
.header .date {
    font-size: 13px;
    color: #8B95A1;
    margin-top: 4px;
}
.summary {
    display: flex;
    gap: 12px;
    margin-bottom: 28px;
}
.summary-card {
    flex: 1;
    background: #fff;
    border-radius: 16px;
    padding: 18px 20px;
}
.summary-card .num {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -1px;
}
.summary-card .label {
    font-size: 12px;
    color: #8B95A1;
    margin-top: 2px;
}
.section-title {
    font-size: 17px;
    font-weight: 700;
    margin: 24px 0 12px 2px;
    letter-spacing: -0.3px;
}
.pick-card {
    background: #fff;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 10px;
    position: relative;
}
.pick-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}
.pick-name {
    font-size: 17px;
    font-weight: 700;
}
.pick-code {
    font-size: 12px;
    color: #B0B8C1;
    font-weight: 500;
    margin-left: 6px;
}
.theme-badge {
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    padding: 4px 10px;
    border-radius: 8px;
}
.pick-body {
    display: flex;
    gap: 24px;
}
.pick-metric .v {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.5px;
}
.pick-metric .k {
    font-size: 11px;
    color: #8B95A1;
    margin-top: 1px;
}
.up { color: #F04452; }   /* 한국식: 상승 빨강 */
.down { color: #3182F6; } /* 하락 파랑 */
.empty {
    background: #fff;
    border-radius: 16px;
    padding: 32px;
    text-align: center;
    color: #8B95A1;
    font-size: 14px;
}
.news-card {
    background: #fff;
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 10px;
}
.news-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.news-name { font-size: 15px; font-weight: 700; }
.news-kw {
    font-size: 11px; color: #8B95A1; font-weight: 500;
}
.news-item {
    font-size: 12px; color: #4E5968;
    padding: 3px 0; line-height: 1.5;
}
.dot-pos { color: #00C896; font-weight: 800; }
.dot-neg { color: #F04452; font-weight: 800; }
.footer {
    text-align: center;
    font-size: 11px;
    color: #B0B8C1;
    margin-top: 28px;
}
"""


def _fmt_change(v):
    cls = "up" if v >= 0 else "down"
    return f'<span class="{cls}">{v:+.1f}%</span>'


def generate_html_report(picks, news_pos, news_neg, trading_day,
                         output_path="/tmp/report.pdf"):
    now = datetime.now()
    try:
        base = datetime.strptime(trading_day, "%Y%m%d").strftime("%Y.%m.%d")
    except Exception:
        base = now.strftime("%Y.%m.%d")

    # ── 눌림목 카드 ──
    if picks:
        pick_html = ""
        for r in picks:
            color = THEME_COLORS.get(r.get("theme", ""), "#3182F6")
            pick_html += f"""
            <div class="pick-card">
                <div class="pick-top">
                    <div>
                        <span class="pick-name">{r['name']}</span>
                        <span class="pick-code">{r['code']}</span>
                    </div>
                    <span class="theme-badge" style="background:{color}">{r.get('theme','-')}</span>
                </div>
                <div class="pick-body">
                    <div class="pick-metric">
                        <div class="v">{r['close']:,}원</div>
                        <div class="k">현재가</div>
                    </div>
                    <div class="pick-metric">
                        <div class="v">{_fmt_change(r['change_pct'])}</div>
                        <div class="k">전일대비</div>
                    </div>
                    <div class="pick-metric">
                        <div class="v down">{r['drop_from_high']:.1f}%</div>
                        <div class="k">고점대비</div>
                    </div>
                    <div class="pick-metric">
                        <div class="v">{r.get('rsi','-')}</div>
                        <div class="k">RSI</div>
                    </div>
                </div>
            </div>"""
    else:
        pick_html = '<div class="empty">오늘 눌림목 신호가 없습니다</div>'

    # ── 뉴스 카드 ──
    def news_block(items, is_pos):
        if not items:
            return ""
        dot = "dot-pos" if is_pos else "dot-neg"
        html = ""
        for r in items:
            kw = " · ".join(r.get("keywords", []))
            lines = ""
            for n in r.get("news", [])[:2]:
                t = n["title"][:45] + ("…" if len(n["title"]) > 45 else "")
                lines += f'<div class="news-item">· {t}</div>'
            html += f"""
            <div class="news-card">
                <div class="news-head">
                    <span class="{dot}">●</span>
                    <span class="news-name">{r['name']}</span>
                    <span class="news-kw">{kw}</span>
                </div>
                {lines}
            </div>"""
        return html

    pos_html = news_block(news_pos, True)
    neg_html = news_block(news_neg, False)
    news_section = ""
    if pos_html:
        news_section += f'<div class="section-title">🟢 긍정 뉴스</div>{pos_html}'
    if neg_html:
        news_section += f'<div class="section-title">🔴 부정 뉴스</div>{neg_html}'
    if not news_section:
        news_section = '<div class="section-title">뉴스</div><div class="empty">관련 뉴스 없음</div>'

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{CSS}</style></head><body>
        <div class="header">
            <h1>AI 밸류체인 눌림목</h1>
            <div class="date">{base} 기준 · {now.strftime('%H:%M')} 생성</div>
        </div>
        <div class="summary">
            <div class="summary-card">
                <div class="num">{len(picks)}</div>
                <div class="label">눌림목 포착</div>
            </div>
            <div class="summary-card">
                <div class="num">50</div>
                <div class="label">관심 종목</div>
            </div>
            <div class="summary-card">
                <div class="num">{len(news_pos)}</div>
                <div class="label">긍정 뉴스</div>
            </div>
        </div>
        <div class="section-title">📈 오늘의 눌림목</div>
        {pick_html}
        {news_section}
        <div class="footer">자동 생성 참고 자료 · KRX 스캐너</div>
    </body></html>
    """

    HTML(string=html).write_pdf(output_path)
    logger.info("HTML PDF 생성 완료: %s", output_path)
    return output_path