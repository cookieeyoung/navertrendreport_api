"""
Tab4 — 종합 트렌드 인사이트
docs/current/prd_tab4.md 기준 구현

현재 상태:
  - 데이터 요약 섹션 (Tab 1·2·3 기반): 활성
  - AI 리포트 생성 버튼: 비활성 (추후 지원 예정)
"""
from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from api.shopping_insight import get_category_trend, get_keyword_ranking
from api.shopping_search import get_product_count, search_products_tab3

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


# ════════════════════════════════════════════════════════════════════
# 공통 UI (tab1/tab2/tab3 서식 통일)
# ════════════════════════════════════════════════════════════════════

def _fmt_dow(date_str: str) -> str:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return f"{date_str}({_WEEKDAY_KO[dt.weekday()]})"


def _period_badge(start: str, end: str, label: str = "") -> None:
    suffix = (
        f"&nbsp;&nbsp;<span style='color:#5a7ab5'>({label})</span>" if label else ""
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


def _sub_header(text: str) -> None:
    st.markdown(
        f"<div style='font-size:15px;font-weight:700;margin:12px 0 6px;color:#444'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def _ai_placeholder() -> None:
    st.markdown(
        "<div style='background:#f8f9fa;border:1px dashed #bbb;border-radius:6px;"
        "padding:12px 16px;color:#999;font-size:13px;margin-top:6px'>"
        "🔒&nbsp;AI 인사이트 — 추후 지원 예정</div>",
        unsafe_allow_html=True,
    )


def _chip_list(items: list[str], color: str = "#4a86e8") -> None:
    if not items:
        st.caption("데이터 없음")
        return
    chips = "".join(
        f"<span style='display:inline-block;background:{color}18;"
        f"color:{color};border:1px solid {color}44;"
        f"border-radius:12px;padding:3px 10px;margin:3px 4px 3px 0;"
        f"font-size:13px;font-weight:600'>{item}</span>"
        for item in items
    )
    st.markdown(f"<div style='line-height:2'>{chips}</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 데이터 수집 유틸
# ════════════════════════════════════════════════════════════════════

def _safe_df(fn, *args, **kwargs) -> pd.DataFrame:
    try:
        result = fn(*args, **kwargs)
        return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _safe_count(query: str) -> int:
    try:
        return get_product_count(query)
    except Exception:
        return 0


def _remove_outliers_iqr(series: pd.Series) -> pd.Series:
    s = series[series > 0]
    if len(s) < 4:
        return s
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)]


# ════════════════════════════════════════════════════════════════════
# [2행] 카테고리 트렌드 추이 분석 (Tab 1 기반)
# ════════════════════════════════════════════════════════════════════

def _render_trend_section(f: dict, cid: str) -> None:
    _section_header("📈 카테고리 트렌드 추이 분석")

    if not cid:
        st.warning("해당 조건의 카테고리 데이터가 없습니다.")
        return

    year       = int(f.get("year", datetime.date.today().year))
    week_end   = f["week_end"]
    ages       = f.get("ages", [])

    df_curr = _safe_df(get_category_trend, cid, f"{year}-01-01", week_end, "week", ages=ages)

    week_end_dt   = datetime.datetime.strptime(week_end, "%Y-%m-%d").date()
    prev_week_end = (week_end_dt - datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")
    df_prev = _safe_df(
        get_category_trend, cid, f"{year - 1}-01-01", prev_week_end, "week", ages=ages
    )

    # ── ① 당해 vs 전년 시계열 비교 ─────────────────────────────────
    _sub_header("① 당해 vs 전년 시계열 비교")

    if df_curr.empty:
        st.caption("트렌드 데이터를 불러올 수 없습니다.")
    else:
        curr_ratio = round(float(df_curr["ratio"].iloc[-1]), 1)
        last4      = df_curr["ratio"].tail(4).tolist()
        trend_dir  = (
            "📈 상승" if len(last4) >= 2 and last4[-1] - last4[0] > 2 else
            ("📉 하락" if len(last4) >= 2 and last4[-1] - last4[0] < -2 else "➡️ 보합")
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("선택주차 지수 (올해)", f"{curr_ratio}")
        with c2:
            if not df_prev.empty:
                prev_ratio = round(float(df_prev["ratio"].iloc[-1]), 1)
                yoy = round((curr_ratio - prev_ratio) / prev_ratio * 100, 1) if prev_ratio > 0 else None
                st.metric("전년 동기 지수", f"{prev_ratio}",
                          delta=f"{yoy:+.1f}%" if yoy is not None else None)
            else:
                st.metric("전년 동기 지수", "-")
        with c3:
            st.metric("최근 4주 추이", trend_dir)

        if len(last4) >= 2:
            st.caption("최근 4주: " + " → ".join(str(round(v, 1)) for v in last4))

    # ── ② 판매 피크 및 핵심 판매주간 ───────────────────────────────
    _sub_header("② 판매 피크 및 핵심 판매주간")

    peak_rows = []
    for label, df in [("올해", df_curr), ("전년도", df_prev)]:
        if df.empty:
            continue
        peak_idx   = df["ratio"].idxmax()
        peak_per   = df.loc[peak_idx, "period"]
        peak_ratio = round(float(df.loc[peak_idx, "ratio"]), 1)

        threshold  = peak_ratio * 0.70
        core_df    = df[df["ratio"] >= threshold]
        core_start = core_df["period"].iloc[0]  if not core_df.empty else peak_per
        core_end   = core_df["period"].iloc[-1] if not core_df.empty else peak_per
        peak_rows.append({
            "구분":           label,
            "피크 주차":      peak_per,
            "피크 지수":      peak_ratio,
            "핵심 판매 구간": f"{core_start} ~ {core_end}",
            "핵심 판매 기간": f"{len(core_df)}주",
        })

    if peak_rows:
        st.dataframe(pd.DataFrame(peak_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("피크 데이터를 불러올 수 없습니다.")

    # ── ③ AI 인사이트 ───────────────────────────────────────────────
    _sub_header("③ AI 인사이트: 판매 사이클 변화 및 대응 제안")
    _ai_placeholder()


# ════════════════════════════════════════════════════════════════════
# [3행] 고객 수요 및 키워드 트렌드 (Tab 2 기반)
# ════════════════════════════════════════════════════════════════════

def _render_keyword_section(f: dict, cid: str) -> None:
    _section_header("🎯 고객 수요 및 키워드 트렌드")

    if not cid:
        st.warning("해당 조건의 키워드 데이터가 없습니다.")
        return

    df_kw = _safe_df(get_keyword_ranking, cid, f["week_start"], f["week_end"])

    # ── ① 인기 키워드 Top10 ────────────────────────────────────────
    _sub_header("① 인기 키워드 Top 10")

    if df_kw.empty:
        st.caption("키워드 데이터를 불러올 수 없습니다.")
    else:
        top10  = df_kw["keyword"].head(10).tolist()
        colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
        chips = "".join(
            f"<span style='display:inline-block;background:{colors[i % len(colors)]}15;"
            f"color:{colors[i % len(colors)]};border:1px solid {colors[i % len(colors)]}55;"
            f"border-radius:12px;padding:3px 12px;margin:3px 4px 3px 0;"
            f"font-size:13px;font-weight:600'>"
            f"<span style='font-size:11px;opacity:0.7'>#{i+1}&nbsp;</span>{kw}</span>"
            for i, kw in enumerate(top10)
        )
        st.markdown(f"<div style='line-height:2.2'>{chips}</div>", unsafe_allow_html=True)

    # ── ② AI 인사이트 ───────────────────────────────────────────────
    _sub_header("② AI 인사이트: 키워드 흐름 및 대응 제안")
    _ai_placeholder()


# ════════════════════════════════════════════════════════════════════
# [4행] 시장 가격 및 상품 현황 (Tab 3 기반)
# ════════════════════════════════════════════════════════════════════

def _render_market_section(query: str, is_fashion: bool) -> None:
    _section_header("🛒 시장 가격 및 상품 현황")

    df_market   = _safe_df(search_products_tab3, query)
    total_count = _safe_count(query)
    subcat_col  = "category4" if is_fashion else "category3"

    total_display = (
        f"{total_count // 10000:,}만개" if total_count >= 10000 else f"{total_count:,}개"
    )

    # ── ① 메인 타겟 가격대 ─────────────────────────────────────────
    _sub_header("① 메인 타겟 가격대")

    if df_market.empty:
        st.caption("마켓 데이터를 불러올 수 없습니다.")
    else:
        prices = df_market[df_market["lprice"] > 0]["lprice"]
        if not prices.empty:
            clean      = _remove_outliers_iqr(prices)
            avg_p      = int(clean.mean())   if not clean.empty else 0
            median_p   = int(clean.median()) if not clean.empty else 0
            bins       = pd.cut(clean, bins=10)
            top_bin    = bins.value_counts().idxmax()
            main_range = (
                f"{int(top_bin.left):,}~{int(top_bin.right):,}원"
                if hasattr(top_bin, "left") else "-"
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("등록 상품수", total_display)
            with c2:
                st.metric("메인 가격대", main_range)
            with c3:
                st.metric("평균가", f"{avg_p:,}원")
            with c4:
                st.metric("중앙가", f"{median_p:,}원")
        else:
            st.metric("등록 상품수", total_display)

    # ── ② 상품 유형 및 인기 브랜드 ─────────────────────────────────
    _sub_header("② 주요 상품 유형 및 인기 브랜드")

    if not df_market.empty:
        col_l, col_r = st.columns(2)
        with col_l:
            st.caption("주요 상품 유형 Top 5")
            top_subcat = (
                df_market[df_market[subcat_col].str.strip() != ""][subcat_col]
                .dropna().value_counts().head(5).index.tolist()
            )
            _chip_list(top_subcat, color="#4a86e8")
        with col_r:
            st.caption("인기 브랜드 Top 5")
            top_brands = (
                df_market[df_market["brand"].str.strip() != ""]["brand"]
                .str.strip().value_counts().head(5).index.tolist()
            )
            _chip_list(top_brands, color="#e8734a")
    else:
        st.caption("데이터를 불러올 수 없습니다.")

    # ── ③ AI 인사이트 ───────────────────────────────────────────────
    _sub_header("③ AI 인사이트: 가격대·상품·브랜드 대응 제안")
    _ai_placeholder()


# ════════════════════════════════════════════════════════════════════
# [5행] 종합 리포트 텍스트 + 다운로드
# ════════════════════════════════════════════════════════════════════

def _build_report_text(f: dict, cid: str, query: str, is_fashion: bool) -> str:
    """Tab 1·2·3 캐시 함수 재호출 → 텍스트 리포트 생성 (LLM 없음)"""
    main_cat   = f.get("main_cat",  "패션의류")
    mid_cat    = f.get("mid_cat",   "여성의류")
    sub_cat    = f.get("sub_cat",   "전체")
    week_start = f.get("week_start", "")
    week_end   = f.get("week_end",   "")
    year       = int(f.get("year", datetime.date.today().year))
    ages       = f.get("ages", [])

    target_label = (
        f"{main_cat} > {mid_cat} > {sub_cat}"
        if is_fashion
        else f"{main_cat} > {mid_cat}"
    )

    lines: list[str] = [
        "=" * 52,
        "📝 자동 생성 요약 리포트",
        "=" * 52,
        f"분석 대상: {target_label}",
        f"분석 기간: {week_start} ~ {week_end}",
        f"생성 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # ── 1. 카테고리 트렌드 분석 ──────────────────────────────────────
    lines.append("1. 카테고리 트렌드 분석")
    lines.append("-" * 40)
    try:
        df_curr = _safe_df(
            get_category_trend, cid, f"{year}-01-01", week_end, "week", ages=ages
        )
        if not df_curr.empty:
            curr_ratio = round(float(df_curr["ratio"].iloc[-1]), 1)
            last4 = df_curr["ratio"].tail(4).tolist()
            trend_dir = (
                "📈 상승세" if len(last4) >= 2 and last4[-1] - last4[0] > 2 else
                ("📉 하락세" if len(last4) >= 2 and last4[-1] - last4[0] < -2 else "➡️ 보합")
            )
            lines.append(
                f"- 선택 주차 검색 지수는 {curr_ratio}로, 최근 4주 추이는 {trend_dir}입니다."
            )

            # 전년 동기
            week_end_dt   = datetime.datetime.strptime(week_end, "%Y-%m-%d").date()
            prev_week_end = (week_end_dt - datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")
            df_prev = _safe_df(
                get_category_trend, cid, f"{year - 1}-01-01", prev_week_end, "week", ages=ages
            )
            if not df_prev.empty:
                prev_ratio = round(float(df_prev["ratio"].iloc[-1]), 1)
                yoy = round((curr_ratio - prev_ratio) / prev_ratio * 100, 1) if prev_ratio > 0 else None
                yoy_str = f"{yoy:+.1f}%" if yoy is not None else "N/A"
                lines.append(
                    f"- 전년 동기 지수는 {prev_ratio}로, 전년 대비 {yoy_str} 변동했습니다."
                )

            # 피크
            peak_idx   = df_curr["ratio"].idxmax()
            peak_per   = df_curr.loc[peak_idx, "period"]
            peak_ratio = round(float(df_curr.loc[peak_idx, "ratio"]), 1)
            lines.append(
                f"- 올해 검색 지수가 가장 높았던 시점은 {peak_per} (지수 {peak_ratio})입니다."
            )
            threshold = peak_ratio * 0.70
            core_df   = df_curr[df_curr["ratio"] >= threshold]
            if not core_df.empty:
                lines.append(
                    f"- 핵심 판매 구간: {core_df['period'].iloc[0]} ~ {core_df['period'].iloc[-1]}"
                    f" ({len(core_df)}주)"
                )
        else:
            lines.append("- 트렌드 데이터를 불러올 수 없습니다.")
    except Exception:
        lines.append("- 트렌드 데이터를 불러올 수 없습니다.")
    lines.append("")

    # ── 2. 키워드 트렌드 ─────────────────────────────────────────────
    lines.append("2. 키워드 트렌드")
    lines.append("-" * 40)
    try:
        df_kw = _safe_df(get_keyword_ranking, cid, week_start, week_end)
        if not df_kw.empty:
            top10 = df_kw["keyword"].head(10).tolist()
            lines.append(
                "- 이번 주 인기 키워드 Top 10: " + ", ".join(
                    f"#{i+1} {kw}" for i, kw in enumerate(top10)
                )
            )
        else:
            lines.append("- 키워드 데이터를 불러올 수 없습니다.")
    except Exception:
        lines.append("- 키워드 데이터를 불러올 수 없습니다.")
    lines.append("")

    # ── 3. 쇼핑 마켓 트렌드 ─────────────────────────────────────────
    lines.append("3. 쇼핑 마켓 트렌드 (수집 상위 300개 기준)")
    lines.append("-" * 40)
    try:
        df_market   = _safe_df(search_products_tab3, query)
        total_count = _safe_count(query)
        total_display = (
            f"{total_count // 10000:,}만개" if total_count >= 10000 else f"{total_count:,}개"
        )
        lines.append(f"- 네이버쇼핑 등록 상품수는 {total_display}입니다.")

        if not df_market.empty:
            prices = df_market[df_market["lprice"] > 0]["lprice"]
            if not prices.empty:
                clean    = _remove_outliers_iqr(prices)
                avg_p    = int(clean.mean())   if not clean.empty else 0
                median_p = int(clean.median()) if not clean.empty else 0
                bins     = pd.cut(clean, bins=10)
                top_bin  = bins.value_counts().idxmax()
                main_range = (
                    f"{int(top_bin.left):,}~{int(top_bin.right):,}원"
                    if hasattr(top_bin, "left") else "-"
                )
                lines.append(f"- 주력 가격대: {main_range}")
                lines.append(f"- 평균가: {avg_p:,}원 / 중앙가: {median_p:,}원")

            subcat_col  = "category4" if is_fashion else "category3"
            top_subcat = (
                df_market[df_market[subcat_col].str.strip() != ""][subcat_col]
                .dropna().value_counts().head(5).index.tolist()
            )
            if top_subcat:
                lines.append("- 주요 상품 유형 Top 5: " + ", ".join(top_subcat))

            top_brands = (
                df_market[df_market["brand"].str.strip() != ""]["brand"]
                .str.strip().value_counts().head(5).index.tolist()
            )
            if top_brands:
                lines.append("- 인기 브랜드 Top 5: " + ", ".join(top_brands))
        else:
            lines.append("- 마켓 데이터를 불러올 수 없습니다.")
    except Exception:
        lines.append("- 마켓 데이터를 불러올 수 없습니다.")
    lines.append("")
    lines.append("=" * 52)

    return "\n".join(lines)


def _report_num_header(num: int, text: str) -> None:
    """번호형 섹션 헤더 (1. 카테고리 트렌드 분석 등)"""
    st.markdown(
        f"<div style='font-size:17px;font-weight:700;margin:20px 0 8px;color:#1a3a6b'>"
        f"{num}.&nbsp;{text}</div>",
        unsafe_allow_html=True,
    )


def _report_bullets(items: list[str]) -> None:
    """불릿 라인 렌더링 — 배경/컬러링 없이 일반 텍스트"""
    if not items:
        return
    html = "".join(
        f"<div style='font-size:15px;line-height:1.85;color:#2c3e50;padding:1px 0'>"
        f"&bull;&nbsp;{item}</div>"
        for item in items
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_report_section(f: dict, cid: str, query: str, is_fashion: bool) -> None:
    week_start = f.get("week_start", "")
    week_end   = f.get("week_end",   "")
    year       = int(f.get("year", datetime.date.today().year))
    ages       = f.get("ages", [])

    def _mmdd(d: str) -> str:
        try:
            return datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d")
        except Exception:
            return d

    date_range_str = f"{_mmdd(week_start)}~{_mmdd(week_end)}"
    _section_header(f"📝 Weekly 종합 리포트 | 선택 주차 ({date_range_str})")

    # ── 1. 카테고리 트렌드 분석 ──────────────────────────────────────
    _report_num_header(1, "카테고리 트렌드 분석")
    bullets1: list[str] = []
    try:
        df_curr = _safe_df(
            get_category_trend, cid, f"{year}-01-01", week_end, "week", ages=ages
        )
        if not df_curr.empty:
            curr_ratio = round(float(df_curr["ratio"].iloc[-1]), 1)
            last4      = df_curr["ratio"].tail(4).tolist()
            trend_dir  = (
                "📈 상승세" if len(last4) >= 2 and last4[-1] - last4[0] > 2 else
                ("📉 하락세" if len(last4) >= 2 and last4[-1] - last4[0] < -2 else "➡️ 보합")
            )
            bullets1.append(
                f"선택 주차 검색 지수는 <b>{curr_ratio}</b>로, 최근 4주 추이는 {trend_dir}입니다."
            )

            week_end_dt   = datetime.datetime.strptime(week_end, "%Y-%m-%d").date()
            prev_week_end = (week_end_dt - datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")
            df_prev = _safe_df(
                get_category_trend, cid, f"{year - 1}-01-01", prev_week_end, "week", ages=ages
            )
            if not df_prev.empty:
                prev_ratio = round(float(df_prev["ratio"].iloc[-1]), 1)
                yoy = round((curr_ratio - prev_ratio) / prev_ratio * 100, 1) if prev_ratio > 0 else None
                yoy_str = f"<b>{yoy:+.1f}%</b>" if yoy is not None else "N/A"
                bullets1.append(
                    f"전년 동기 지수는 {prev_ratio}로, 전년 대비 {yoy_str} 변동했습니다."
                )

            peak_idx   = df_curr["ratio"].idxmax()
            peak_per   = df_curr.loc[peak_idx, "period"]
            peak_ratio = round(float(df_curr.loc[peak_idx, "ratio"]), 1)
            bullets1.append(
                f"올해 검색 지수가 가장 높았던 시점은 <b>{peak_per}</b> (지수 {peak_ratio})입니다."
            )
            threshold = peak_ratio * 0.70
            core_df   = df_curr[df_curr["ratio"] >= threshold]
            if not core_df.empty:
                bullets1.append(
                    f"핵심 판매 구간: <b>{core_df['period'].iloc[0]} ~ {core_df['period'].iloc[-1]}</b>"
                    f" ({len(core_df)}주)"
                )
        else:
            bullets1.append("트렌드 데이터를 불러올 수 없습니다.")
    except Exception:
        bullets1.append("트렌드 데이터를 불러올 수 없습니다.")
    _report_bullets(bullets1)

    # ── 2. 키워드 트렌드 ─────────────────────────────────────────────
    _report_num_header(2, "키워드 트렌드")
    bullets2: list[str] = []
    try:
        df_kw = _safe_df(get_keyword_ranking, cid, week_start, week_end)
        if not df_kw.empty:
            top10 = df_kw["keyword"].head(10).tolist()
            bullets2.append(
                "이번 주 인기 키워드 Top 10: <b>"
                + "&nbsp; ".join(f"#{i+1} {kw}" for i, kw in enumerate(top10))
                + "</b>"
            )
        else:
            bullets2.append("키워드 데이터를 불러올 수 없습니다.")
    except Exception:
        bullets2.append("키워드 데이터를 불러올 수 없습니다.")
    _report_bullets(bullets2)

    # ── 3. 쇼핑 마켓 트렌드 ─────────────────────────────────────────
    _report_num_header(3, "쇼핑 마켓 트렌드 (수집 상위 300개 기준)")
    bullets3: list[str] = []
    try:
        df_market   = _safe_df(search_products_tab3, query)
        total_count = _safe_count(query)
        total_display = (
            f"{total_count // 10000:,}만개" if total_count >= 10000 else f"{total_count:,}개"
        )
        bullets3.append(f"네이버쇼핑 등록 상품수는 <b>{total_display}</b>입니다.")

        if not df_market.empty:
            prices = df_market[df_market["lprice"] > 0]["lprice"]
            if not prices.empty:
                clean      = _remove_outliers_iqr(prices)
                avg_p      = int(clean.mean())   if not clean.empty else 0
                median_p   = int(clean.median()) if not clean.empty else 0
                bins       = pd.cut(clean, bins=10)
                top_bin    = bins.value_counts().idxmax()
                main_range = (
                    f"{int(top_bin.left):,}~{int(top_bin.right):,}원"
                    if hasattr(top_bin, "left") else "-"
                )
                bullets3.append(f"주력 가격대: <b>{main_range}</b>")
                bullets3.append(f"평균가: <b>{avg_p:,}원</b> / 중앙가: <b>{median_p:,}원</b>")

            subcat_col = "category4" if is_fashion else "category3"
            top_subcat = (
                df_market[df_market[subcat_col].str.strip() != ""][subcat_col]
                .dropna().value_counts().head(5).index.tolist()
            )
            if top_subcat:
                bullets3.append("주요 상품 유형 Top 5: <b>" + ", ".join(top_subcat) + "</b>")

            top_brands = (
                df_market[df_market["brand"].str.strip() != ""]["brand"]
                .str.strip().value_counts().head(5).index.tolist()
            )
            if top_brands:
                bullets3.append("인기 브랜드 Top 5: <b>" + ", ".join(top_brands) + "</b>")
        else:
            bullets3.append("마켓 데이터를 불러올 수 없습니다.")
    except Exception:
        bullets3.append("마켓 데이터를 불러올 수 없습니다.")
    _report_bullets(bullets3)

    # ── 다운로드 버튼 ────────────────────────────────────────────────
    st.write("")
    report_text = _build_report_text(f, cid, query, is_fashion)
    filename    = f"trend_report_{week_end}.txt"
    st.download_button(
        label="⬇️ 리포트 다운로드 (.txt)",
        data=report_text.encode("utf-8"),
        file_name=filename,
        mime="text/plain",
        use_container_width=False,
    )


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

    # CID 결정
    female_cid = f.get("female_cid", "")
    male_cid   = f.get("male_cid",   "")
    mid_cid    = f.get("mid_cat_cid", "")
    if is_fashion:
        cid = female_cid if "여성" in mid_cat else (male_cid or female_cid or "")
    else:
        cid = mid_cid

    # Tab3 query 결정
    if is_fashion:
        gender_prefix = "여성" if "여성" in mid_cat else "남성"
        query = f"{gender_prefix} {sub_cat}" if sub_cat != "전체" else mid_cat
    else:
        query = mid_cat

    # ── 타이틀 ────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:22px;font-weight:800;margin-bottom:2px'>"
        "Weekly 트렌드 인사이트</h2>",
        unsafe_allow_html=True,
    )
    if is_fashion:
        st.caption(f"📌 {main_cat} > {mid_cat} > {sub_cat} ")
    else:
        st.caption(f"📌 {main_cat} > {mid_cat}")
    _period_badge(week_start, week_end, "선택 주차")

    # ── 설명 텍스트 ──────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:14px;color:#555;line-height:1.7;margin:8px 0 4px'>"
        "💡 각 탭의 데이터를 취합하여 핵심 인사이트를 요약합니다. (규칙 기반 자동 생성)"
        "</div>"
        "<div style='font-size:13px;color:#888;line-height:1.6;margin-bottom:10px'>"
        "⚠️ 주의: 본 리포트는 API에서 제공하는 최대 100건의 상위 노출 데이터만을 기반으로 분석되었습니다. "
        "전체 시장 데이터를 대변하지 않을 수 있으며, 표본 편향이 있을 수 있으므로 참고용으로만 활용해 주세요."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── AI 버튼 (비활성) ─────────────────────────────────────────
    st.button(
        "🤖 AI 리포트 생성",
        type="primary",
        disabled=True,
        help="AI 리포트 기능은 추후 지원 예정입니다.",
    )
    st.divider()

    # ── 섹션 렌더링 ───────────────────────────────────────────────
    _render_trend_section(f, cid)
    st.divider()
    _render_keyword_section(f, cid)
    st.divider()
    _render_market_section(query, is_fashion)
    st.divider()
    _render_report_section(f, cid, query, is_fashion)
