"""
Tab3 — 네이버쇼핑 마켓 현황
docs/current/prd_tab3.md 기준 구현
"""

from __future__ import annotations

import re
import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

from api.shopping_search import search_products_tab3, get_product_count

# ── 레이아웃 공통 설정 (tab1/tab2 동일) ────────────────────────────
_LAYOUT_BASE = dict(
    font_family="Noto Sans KR, sans-serif",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

_GENDER_TOKENS: set[str] = {
    "남성", "여성", "남자", "여자", "남", "여",
    "men", "women", "man", "woman", "unisex", "male", "female",
}

from utils.text_parser import get_font_path as _get_font_path
_KOREAN_FONT = _get_font_path()   # OS별 자동 감지 (Windows/macOS/Linux)


# ════════════════════════════════════════════════════════════════════
# 유틸 함수 (tab1/tab2 서식 통일)
# ════════════════════════════════════════════════════════════════════

def _fmt_dow(date_str: str) -> str:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return f"{date_str}({_WEEKDAY_KO[dt.weekday()]})"


def _period_badge(start: str, end: str, label: str = "") -> None:
    suffix = (
        f"&nbsp;&nbsp;<span style='color:#5a7ab5'>({label})</span>"
        if label else ""
    )
    st.markdown(
        f"<div style='display:inline-block;background:#e8f0fe;"
        f"border-left:4px solid #4a86e8;padding:7px 14px;"
        f"border-radius:4px;font-size:14px;font-weight:700;"
        f"color:#1a3a6b;margin-bottom:10px'>"
        f"📅&nbsp;{_fmt_dow(start)}&nbsp;~&nbsp;{_fmt_dow(end)}{suffix}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _section_header(text: str) -> None:
    st.markdown(
        f"<div style='font-size:20px;font-weight:700;margin:18px 0 8px;color:#222;"
        f"border-left:4px solid #4a86e8;padding-left:10px'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 전처리 함수
# ════════════════════════════════════════════════════════════════════

def _remove_outliers_iqr(series: pd.Series) -> pd.Series:
    s = series[series > 0]
    if len(s) < 4:
        return s
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)]


def _extract_title_tokens(title: str, brand: str) -> list[str]:
    text = re.sub(r"[/_\-]", " ", title)
    text = re.sub(r"<[^>]+>", "", text)

    brand_tokens: set[str] = set()
    if brand:
        for t in brand.split():
            brand_tokens.add(t.lower())

    result = []
    for t in text.split():
        t_clean = re.sub(r"[^\w가-힣a-zA-Z0-9]", "", t)
        if len(t_clean) < 2:
            continue
        if re.fullmatch(r"\d+", t_clean):
            continue
        if t_clean.lower() in _GENDER_TOKENS:
            continue
        if t_clean.lower() in brand_tokens:
            continue
        result.append(t_clean)
    return result


# ════════════════════════════════════════════════════════════════════
# [1행] 스코어카드 (헤더 없음)
# ════════════════════════════════════════════════════════════════════

def _render_scorecard(df: pd.DataFrame, total_count: int) -> None:
    c1, c2, c3, c4 = st.columns(4)

    collected = df["productId"].nunique() if not df.empty else 0

    if not df.empty:
        clean_prices = _remove_outliers_iqr(df["lprice"])
        avg_price    = int(clean_prices.mean())   if not clean_prices.empty else 0
        median_price = int(clean_prices.median()) if not clean_prices.empty else 0
    else:
        avg_price = median_price = 0

    # c1: 만 단위 정수 스케일링 (10,000,000 → 1,000만개)
    if total_count >= 10000:
        total_display = f"{total_count // 10000:,}만개"
    else:
        total_display = f"{total_count:,}개"

    with c1:
        st.metric("등록된 전체 상품", total_display, help="네이버쇼핑 channel.total 기준, 중복 등록건 존재")
    with c2:
        st.metric("수집된 전체 상품", f"{collected:,}개", help="productId 중복 제거 (최대 300)")
    with c3:
        st.metric("평균 판매가", f"{avg_price:,}원", help="IQR 이상치 제거 후 평균")
    with c4:
        st.metric("중앙값 판매가", f"{median_price:,}원", help="IQR 이상치 제거 후 중앙값")


# ════════════════════════════════════════════════════════════════════
# [2행] 워드클라우드 (2열: 좌=유형별, 우=브랜드별)
# ════════════════════════════════════════════════════════════════════

def _draw_wc(freq: dict, colormap: str = "Blues") -> None:
    if not freq:
        st.info("표시할 데이터가 없습니다.")
        return
    try:
        from wordcloud import WordCloud
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        try:
            wc = WordCloud(
                font_path=_KOREAN_FONT,
                width=600, height=300,
                background_color="white",
                max_words=30,
                colormap=colormap,
                prefer_horizontal=0.9,
            ).generate_from_frequencies(freq)
        except Exception:
            wc = WordCloud(
                width=600, height=300,
                background_color="white",
                max_words=30,
                colormap=colormap,
                prefer_horizontal=0.9,
            ).generate_from_frequencies(freq)

        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig)
        plt.close(fig)
    except ImportError:
        st.warning("wordcloud 라이브러리가 설치되어 있지 않습니다.")


def _render_wordcloud(df_filtered: pd.DataFrame, query: str) -> None:
    if df_filtered.empty:
        st.info("데이터가 없습니다.")
        return

    col_wc_l, col_wc_r = st.columns(2)

    with col_wc_l:
        st.markdown(
            "<div style='font-size:15px;font-weight:700;margin-bottom:4px;color:#333'>"
            "상품 키워드</div>",
            unsafe_allow_html=True,
        )
        freq: dict[str, int] = {}
        for _, row in df_filtered.iterrows():
            for tok in _extract_title_tokens(row["title"], row["brand"]):
                freq[tok] = freq.get(tok, 0) + 1
        _draw_wc(freq, colormap="tab10")

    with col_wc_r:
        st.markdown(
            "<div style='font-size:15px;font-weight:700;margin-bottom:4px;color:#333'>"
            "브랜드 키워드</div>",
            unsafe_allow_html=True,
        )
        brand_counts: dict[str, int] = (
            df_filtered[df_filtered["brand"].str.strip() != ""]["brand"]
            .str.strip()
            .value_counts()
            .head(50)
            .to_dict()
        )
        _draw_wc(brand_counts, colormap="Set1")


# ════════════════════════════════════════════════════════════════════
# [3행] 가격 분석
# ════════════════════════════════════════════════════════════════════

def _render_price_analysis(
    df_filtered: pd.DataFrame,
    subcat_col: str,
    selected_subcats: list[str],
) -> None:
    _section_header("③ 키워드별 가격 분포 현황")

    df_p = df_filtered[df_filtered["lprice"] > 0].copy()
    if df_p.empty:
        st.info("가격 데이터가 없습니다.")
        return

    df_p["lprice_k"] = df_p["lprice"] / 1000.0
    multi_mode = len(selected_subcats) >= 2

    col_box, col_hist = st.columns(2)

    _MULTI_COLORS = px.colors.qualitative.Plotly  # 10색 이상 완전 구분 컬러

    with col_box:
        if multi_mode:
            fig_box = px.box(
                df_p, x=subcat_col, y="lprice_k",
                color=subcat_col,
                points="outliers",
                labels={subcat_col: "키워드", "lprice_k": "판매가 (천원)"},
                title="키워드별 가격 분포(box plot)",
                category_orders={subcat_col: selected_subcats},
                color_discrete_sequence=_MULTI_COLORS,
            )
            fig_box.update_layout(
                showlegend=True,
                legend_title_text="키워드",
            )
        else:
            fig_box = px.box(
                df_p, y="lprice_k",
                points="outliers",
                labels={"lprice_k": "판매가 (천원)"},
                title="가격 분포(box plot)",
                color_discrete_sequence=["#4a86e8"],
            )
            fig_box.update_layout(showlegend=False)

        fig_box.update_layout(
            yaxis=dict(title="판매가 (천원)", showgrid=True, gridcolor="#f0f0f0"),
            xaxis=dict(title="키워드", showgrid=False),
            height=400,
            margin=dict(l=20, r=20, t=40, b=60),
            **_LAYOUT_BASE,
        )
        st.plotly_chart(fig_box, use_container_width=True, key="tab3_boxplot")

    with col_hist:
        if multi_mode:
            fig_hist = px.histogram(
                df_p, x="lprice_k",
                color=subcat_col,
                nbins=10,
                barmode="overlay",
                opacity=0.65,
                labels={"lprice_k": "판매가 (천원)", "count": "상품 수"},
                title="키워드별 가격 분포(histogram)",
                category_orders={subcat_col: selected_subcats},
                color_discrete_sequence=_MULTI_COLORS,
            )
            fig_hist.update_layout(
                showlegend=True,
                legend_title_text="키워드",
            )
        else:
            fig_hist = px.histogram(
                df_p, x="lprice_k",
                nbins=10,
                labels={"lprice_k": "판매가 (천원)", "count": "상품 수"},
                title="가격 분포(histogram)",
                color_discrete_sequence=["#4a86e8"],
            )
            fig_hist.update_layout(showlegend=False)

        fig_hist.update_layout(
            bargap=0.05,
            yaxis=dict(title="상품 수", showgrid=True, gridcolor="#f0f0f0"),
            xaxis=dict(title="판매가 (천원)", showgrid=False),
            height=400,
            margin=dict(l=20, r=20, t=40, b=60),
            **_LAYOUT_BASE,
        )
        st.plotly_chart(fig_hist, use_container_width=True, key="tab3_histogram")

    # 기술통계 테이블
    if multi_mode:
        groups_iter = list(df_p.groupby(subcat_col)["lprice"])
    else:
        groups_iter = [("전체", df_p["lprice"])]

    stat_rows = []
    for name, grp in groups_iter:
        raw   = grp[grp > 0]
        clean = _remove_outliers_iqr(raw)
        if raw.empty:
            continue
        stat_rows.append({
            "키워드":         name,
            "등록 상품수":    len(raw),
            "평균가격":       f"{int(clean.mean()):,}원"   if not clean.empty else "-",
            "중앙가격(50%)":  f"{int(clean.median()):,}원" if not clean.empty else "-",
            "최저가격":       f"{int(raw.min()):,}원",
            "최고가격":       f"{int(raw.max()):,}원",
        })

    if stat_rows:
        df_stat = pd.DataFrame(stat_rows)
        styled = (
            df_stat.style
            .set_properties(**{"text-align": "center", "font-size": "13px"})
            .set_table_styles([{
                "selector": "th",
                "props": [
                    ("text-align", "center"),
                    ("font-size", "13px"),
                    ("font-weight", "700"),
                ],
            }])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True, key="tab3_stat_tbl")


# ════════════════════════════════════════════════════════════════════
# [4행] 상품 목록
# ════════════════════════════════════════════════════════════════════

def _render_product_list(
    df: pd.DataFrame,
    query: str,
    subcat_col: str,
    selected_subcats: list[str],
) -> None:
    _section_header("④ 키워드별 상품 리스트")

    if df.empty:
        st.info("데이터가 없습니다.")
        return

    # 단일선택 드롭다운 (2행 선택값 기반)
    filter_options = ["전체"] + (selected_subcats if selected_subcats else [])
    list_subcat = st.selectbox("키워드", options=filter_options, key="tab3_list_subcat")

    df_list = (
        df[df[subcat_col] == list_subcat].copy()
        if list_subcat != "전체"
        else df.copy()
    )

    if df_list.empty:
        st.info("선택된 카테고리에 해당하는 상품이 없습니다.")
        return

    total_items = len(df_list)
    per_page    = 20
    total_pages = max(1, -(-total_items // per_page))

    page_num: int = st.session_state.get("tab3_list_page", 1)

    if st.session_state.get("tab3_list_prev_subcat") != list_subcat:
        page_num = 1
        st.session_state["tab3_list_page"] = 1
        st.session_state["tab3_list_prev_subcat"] = list_subcat

    page_num = max(1, min(page_num, total_pages))

    # ── 1행: 뷰 토글(좌) + 페이지 정보(우측 정렬) ─────────────────
    col_toggle, col_info = st.columns([4, 6])

    with col_toggle:
        view_mode = st.radio(
            "표시 방식",
            ["리스트형", "썸네일 목록형"],
            horizontal=True,
            key="tab3_view_mode",
            label_visibility="collapsed",
        )

    with col_info:
        st.markdown(
            f"<div style='text-align:right;padding-top:8px;font-size:13px;color:#666'>"
            f"총 {total_items:,}개 상품 &nbsp;|&nbsp; {page_num}/{total_pages} 페이지"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 2행: 이전(좌) + 다음(우) ────────────────────────────────────
    col_prev, _, col_next = st.columns([1, 8, 1])

    with col_prev:
        if st.button("◀ 이전", key="tab3_prev_btn", disabled=(page_num <= 1)):
            st.session_state["tab3_list_page"] = page_num - 1
            st.rerun()

    with col_next:
        if st.button("다음 ▶", key="tab3_next_btn", disabled=(page_num >= total_pages)):
            st.session_state["tab3_list_page"] = page_num + 1
            st.rerun()

    page_df = df_list.iloc[(page_num - 1) * per_page: page_num * per_page]

    # ── 리스트형 ────────────────────────────────────────────────────
    if view_mode == "리스트형":
        items_html = []
        for _, row in page_df.iterrows():
            thumb_url = row.get("image", "")
            thumb_html = (
                f'<img src="{thumb_url}" '
                f'style="width:200px;height:200px;object-fit:cover;'
                f'border-radius:6px;flex-shrink:0">'
                if thumb_url
                else (
                    "<div style='width:200px;height:200px;background:#f0f0f0;"
                    "border-radius:6px;flex-shrink:0;display:flex;"
                    "align-items:center;justify-content:center;"
                    "color:#ccc;font-size:11px'>NO IMG</div>"
                )
            )
            link   = row.get("link", "")
            title  = row.get("title", "")
            brand  = row.get("brand", "")    or "-"
            mall   = row.get("mallName", "") or "-"
            subcat = row.get(subcat_col, "") or "-"
            lprice = row.get("lprice", 0)
            price_str = f"{int(lprice):,}원" if lprice else "-"

            title_html = (
                f'<a href="{link}" target="_blank" '
                f'style="font-size:25px;font-weight:700;color:#1a1a2e;'
                f'text-decoration:none;line-height:1.4">{title}</a>'
                f'&nbsp;<a href="{link}" target="_blank" '
                f'style="font-size:25px;color:#4a86e8;text-decoration:none">↗ 바로가기</a>'
                if link else
                f'<span style="font-size:25px;font-weight:700;color:#1a1a2e">{title}</span>'
            )

            items_html.append(
                f"<div style='display:flex;align-items:flex-start;gap:25px;"
                f"padding:25px 0;border-bottom:1px solid #f0f0f0'>"
                f"{thumb_html}"
                f"<div style='flex:1;min-width:0'>"
                f"<div style='margin-bottom:8px'>{title_html}</div>"
                f"<div style='font-size:13px;color:#555;line-height:1.8'>"
                f"📂&nbsp;<b>카테고리</b>&nbsp;{subcat}<br>"
                f"🏷️&nbsp;<b>브랜드</b>&nbsp;{brand}<br>"
                f"💰&nbsp;<b>판매가</b>&nbsp;{price_str}<br>"
                f"🏪&nbsp;<b>판매처</b>&nbsp;{mall}"
                f"</div>"
                f"</div></div>"
            )

        st.markdown(
            "<div style='margin-top:8px'>" + "".join(items_html) + "</div>",
            unsafe_allow_html=True,
        )

    # ── 썸네일 목록형 ───────────────────────────────────────────────
    else:
        cards_html = []
        for _, row in page_df.iterrows():
            thumb_url = row.get("image", "")
            thumb_html = (
                f'<img src="{thumb_url}" '
                f'style="width:100%;aspect-ratio:1/1;object-fit:cover">'
                if thumb_url
                else "<div style='width:100%;aspect-ratio:1/1;background:#f0f0f0;"
                     "display:flex;align-items:center;justify-content:center;"
                     "color:#ccc;font-size:11px'>NO IMG</div>"
            )
            link   = row.get("link", "")
            title  = row.get("title", "")
            brand  = row.get("brand", "")    or "-"
            mall   = row.get("mallName", "") or "-"
            subcat = row.get(subcat_col, "") or "-"
            lprice = row.get("lprice", 0)
            price_str = f"{int(lprice):,}원" if lprice else "-"

            # 썸네일형 상품명 truncate (2줄 ellipsis)
            title_html = (
                f'<a href="{link}" target="_blank" '
                f'style="font-size:13px;font-weight:700;color:#1a1a2e;'
                f'text-decoration:none;display:-webkit-box;'
                f'-webkit-line-clamp:2;-webkit-box-orient:vertical;'
                f'overflow:hidden;line-height:1.4">{title}</a>'
                f'&nbsp;<a href="{link}" target="_blank" '
                f'style="font-size:11px;color:#4a86e8;text-decoration:none">↗</a>'
                if link else
                f'<span style="font-size:13px;font-weight:700;color:#1a1a2e;'
                f'display:-webkit-box;-webkit-line-clamp:2;'
                f'-webkit-box-orient:vertical;overflow:hidden">{title}</span>'
            )

            cards_html.append(
                f"<div style='border:1px solid #e8e8e8;border-radius:8px;"
                f"overflow:hidden;background:#fff'>"
                f"{thumb_html}"
                f"<div style='padding:10px'>"
                f"<div style='margin-bottom:6px'>{title_html}</div>"
                f"<div style='font-size:11px;color:#666;line-height:1.8'>"
                f"📂&nbsp;<b>카테고리</b>&nbsp;{subcat}<br>"
                f"🏷️&nbsp;<b>브랜드</b>&nbsp;{brand}<br>"
                f"💰&nbsp;<b>판매가</b>&nbsp;{price_str}<br>"
                f"🏪&nbsp;<b>판매처</b>&nbsp;{mall}"
                f"</div></div></div>"
            )

        # 4열 그리드
        grid_html = (
            "<div style='display:grid;grid-template-columns:repeat(4,1fr);"
            "gap:12px;margin-top:8px'>"
            + "".join(cards_html)
            + "</div>"
        )
        st.markdown(grid_html, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 메인 진입점
# ════════════════════════════════════════════════════════════════════

def render() -> None:
    f = st.session_state.get("filter", {})
    if not f or "week_end" not in f:
        st.warning("사이드바에서 필터를 설정해 주세요.")
        return

    main_cat   = f.get("main_cat",  "패션의류")
    mid_cat    = f.get("mid_cat",   "여성의류")
    sub_cat    = f.get("sub_cat",   "전체")
    week_start = f["week_start"]
    week_end   = f["week_end"]
    year       = f.get("year", datetime.date.today().year)

    is_fashion = (main_cat == "패션의류")

    if is_fashion:
        gender = "여성" if "여성" in mid_cat else "남성"
        query  = f"{gender} {sub_cat}" if sub_cat != "전체" else mid_cat
    else:
        query = mid_cat
    subcat_col = "category3" if is_fashion else "category3"

    # ── 타이틀 ────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:22px;font-weight:800;margin-bottom:2px'>"
        "네이버쇼핑 마켓 현황</h2>",
        unsafe_allow_html=True,
    )
    if is_fashion:
        st.caption(
            f"📌 {main_cat} > {mid_cat} > {sub_cat} | "
            f"기준 주차: {week_start} ~ {week_end}"
        )
    else:
        st.caption(
            f"📌 {main_cat} > {mid_cat} | "
            f"기준 주차: {week_start} ~ {week_end}"
        )

    st.divider()

    # ── 데이터 수집 ────────────────────────────────────────────────
    with st.spinner(f"'{query}' 상품 데이터 수집 중…"):
        df_raw      = search_products_tab3(query)
        total_count = get_product_count(query)

    if df_raw.empty:
        st.warning("수집된 상품 데이터가 없습니다. 사이드바 카테고리를 확인해 주세요.")
        return

    # ════════════════════════════════════════════════════════════
    # [1행] 스코어카드 (헤더 없이 최상단)
    # ════════════════════════════════════════════════════════════
    _render_scorecard(df_raw, total_count)
    st.divider()

    # ════════════════════════════════════════════════════════════
    # [2행] 세부 카테고리 필터 + 워드클라우드
    # ════════════════════════════════════════════════════════════
    _section_header("① 카테고리별 상품 구성 현황")

    # 빈도수 기준 정렬 (많은 순)
    subcat_options: list[str] = (
        df_raw[df_raw[subcat_col].str.strip() != ""][subcat_col]
        .dropna()
        .value_counts()
        .index.tolist()
    )

    selected_subcats: list[str] = []
    if subcat_options:
        selected_subcats = st.multiselect(
            "세부 키워드 선택 (최대 3개)",
            options=subcat_options,
            default=[],
            max_selections=3,
            key=f"tab3_subcat_filter_{query}",
        )

    df_filtered = (
        df_raw[df_raw[subcat_col].isin(selected_subcats)].copy()
        if selected_subcats
        else df_raw.copy()
    )

    _render_wordcloud(df_filtered, query)
    st.divider()

    # ════════════════════════════════════════════════════════════
    # [3행] 가격 분석
    # ════════════════════════════════════════════════════════════
    _render_price_analysis(df_filtered, subcat_col, selected_subcats)
    st.divider()

    # ════════════════════════════════════════════════════════════
    # [4행] 상품 목록
    # ════════════════════════════════════════════════════════════
    _render_product_list(df_raw, query, subcat_col, selected_subcats)
