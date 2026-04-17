"""
Tab 2 — 키워드 트렌드 분석

쇼핑인사이트 API 기반 카테고리별 주간 인기 키워드 순위 + 시계열 비교.
참조: docs/current/prd_tab2.md

레이아웃 (3행 × 2열):
  [1행 Left/Right]  여성/남성 키워드 Top20 랭킹 테이블 (체크박스 선택)
  [2행 Left/Right]  여성/남성 키워드 시계열 라인차트
  [3행 Full]        키워드 비교 분석 테이블 (여성/남성 각각)

API:
  get_keyword_ranking   → [1행] 주간 인기 키워드 Top20
  get_keyword_trend     → [2행] 선택 키워드 시계열 (최대 3개)
"""

import datetime
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.shopping_insight import get_keyword_ranking, get_keyword_trend

# ── 상수 ──────────────────────────────────────────────────────────
_MAX_KW = 3  # 키워드 최대 선택/조회 수

_LAYOUT_BASE = dict(
    font_family="Noto Sans KR, sans-serif",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 키워드별 차트 색상 (최대 3개)
_KW_COLORS = ["#4a86e8", "#e74c3c", "#2ecc71"]


# ════════════════════════════════════════════════════════════════════
# 유틸 함수
# ════════════════════════════════════════════════════════════════════

def _fmt_dow(date_str: str) -> str:
    """'2026-04-06' → '2026-04-06(월)'"""
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


def _section_header(text: str, help_text: str = "") -> None:
    tooltip_html = ""
    if help_text:
        escaped = (
            help_text
            .replace("&", "&amp;")
            .replace("'", "&#39;")
            .replace('"', "&quot;")
            .replace("\n", "&#10;")
        )
        tooltip_html = (
            f"&nbsp;<span title='{escaped}' "
            f"style='cursor:help;color:#888;font-size:14px;"
            f"font-weight:400;vertical-align:middle'>ⓘ</span>"
        )
    st.markdown(
        f"<div style='font-size:20px;font-weight:700;margin:18px 0 8px;color:#222;"
        f"border-left:4px solid #4a86e8;padding-left:10px'>"
        f"{text}{tooltip_html}</div>",
        unsafe_allow_html=True,
    )


def _get_tab2_cids(f: dict) -> tuple[str | None, str | None]:
    """필터에서 female_cid, male_cid 추출. 패션잡화는 mid_cat_cid 단일 CID 사용."""
    main_cat = f.get("main_cat", "패션의류")
    if main_cat != "패션의류":
        return f.get("mid_cat_cid"), None
    return f.get("female_cid"), f.get("male_cid")


def _age_param(f: dict) -> str:
    """연령 필터 → API 단일 age 문자열 (복수·전체 시 '')"""
    ages = f.get("ages", [])
    return str(ages[0]) if len(ages) == 1 else ""


def _parse_extra_keywords(raw: str) -> list[str]:
    """쉼표 구분 문자열 → 키워드 리스트"""
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


def _chg_num(val: str) -> float:
    """전주대비 변동 문자열 → 정렬용 숫자"""
    if val == "NEW":
        return float("inf")
    if val.startswith("▲"):
        try:
            return float(val[1:])
        except ValueError:
            return 0.0
    if val.startswith("▼"):
        try:
            return -float(val[1:])
        except ValueError:
            return 0.0
    return 0.0


# ════════════════════════════════════════════════════════════════════
# [1행] 카테고리별 주간 키워드 Top20 랭킹 테이블
# ════════════════════════════════════════════════════════════════════

def _render_ranking_table(
    cid: str,
    gender_label: str,
    state_key: str,
    f: dict,
) -> None:
    """
    키워드 랭킹 테이블 (체크박스 선택, 최대 _MAX_KW개).

    - 기본 선택: 순위 1~3위 키워드
    - 정렬 변경 또는 카테고리 변경 시 선택 유지하며 테이블 재렌더
    - 선택값 → session_state[state_key]
    """
    week_start = f["week_start"]
    week_end   = f["week_end"]
    age_param  = _age_param(f)

    # 전주 날짜 (순위 변동 비교용)
    ws_dt   = date.fromisoformat(week_start)
    we_dt   = date.fromisoformat(week_end)
    prev_ws = (ws_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_we = (we_dt - timedelta(days=7)).strftime("%Y-%m-%d")

    df_now = get_keyword_ranking(cid, week_start, week_end, age=age_param, count=20)
    df_pw  = get_keyword_ranking(cid, prev_ws, prev_we, age=age_param, count=40)

    if df_now.empty:
        st.warning(f"{gender_label} 키워드 데이터를 불러올 수 없습니다.")
        return

    prev_d: dict = (
        dict(zip(df_pw["keyword"], df_pw["rank"])) if not df_pw.empty else {}
    )

    def _change(row, _p=prev_d):
        p = _p.get(row["keyword"])
        if p is None:
            return "NEW"
        d = p - row["rank"]
        return f"▲{d}" if d > 0 else (f"▼{abs(d)}" if d < 0 else "-")

    df_now = df_now.copy()
    df_now["전주대비"] = df_now.apply(_change, axis=1)
    base_df = df_now[["rank", "keyword", "전주대비"]].rename(
        columns={"rank": "순위", "keyword": "키워드"}
    )

    # 정렬 옵션 라디오
    sort_opt = st.radio(
        "정렬 기준",
        ["순위", "상승순", "하락순"],
        horizontal=True,
        index=0,
        key=f"sort_{state_key}",
        label_visibility="collapsed",
    )

    if sort_opt == "순위":
        display_df = base_df.sort_values("순위").reset_index(drop=True)
    elif sort_opt == "상승순":
        display_df = (
            base_df
            .assign(_s=base_df["전주대비"].map(_chg_num))
            .sort_values("_s", ascending=False)
            .drop(columns="_s")
            .reset_index(drop=True)
        )
    else:  # 하락순
        display_df = (
            base_df
            .assign(_s=base_df["전주대비"].map(_chg_num))
            .sort_values("_s", ascending=True)
            .drop(columns="_s")
            .reset_index(drop=True)
        )

    # ── 전주대비 컬러 스타일 적용 ──────────────────────────────
    all_kws = display_df["키워드"].tolist()
    styled = (
        display_df.style
        .map(
            lambda v: (
                "color: #f39c12; font-weight: bold" if v == "NEW"
                else "color: #2ecc71; font-weight: bold" if str(v).startswith("▲")
                else "color: #e74c3c; font-weight: bold" if str(v).startswith("▼")
                else "color: #999999"
            ),
            subset=["전주대비"],
        )
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
    st.dataframe(styled, use_container_width=True, hide_index=True, height=370)

    # ── 키워드 선택 (multiselect) ───────────────────────────────
    # cid 변경 시 key 교체 → default(top3) 자동 적용
    top3 = df_now.nsmallest(min(_MAX_KW, len(df_now)), "rank")["keyword"].tolist()
    new_sel = st.multiselect(
        "키워드 선택 (최대 3개)",
        options=all_kws,
        default=top3,
        key=f"ms_{state_key}_{cid}",
        label_visibility="collapsed",
    )
    if len(new_sel) > _MAX_KW:
        st.warning(f"최대 {_MAX_KW}개까지 선택 가능합니다. 앞 {_MAX_KW}개만 사용합니다.")
        new_sel = new_sel[:_MAX_KW]

    st.session_state[state_key] = new_sel


# ════════════════════════════════════════════════════════════════════
# [2행] 선택 키워드 시계열 라인차트
# ════════════════════════════════════════════════════════════════════

def _render_trend_chart(
    cid: str,
    keywords: list[str],
    date_range: tuple[str, str],
    gender_label: str,
    chart_key: str,
    ages: list,
) -> pd.DataFrame:
    """
    키워드 시계열 라인차트 렌더링.
    반환: trend DataFrame (3행 비교 테이블 재사용)
    """
    if not keywords:
        st.info("1행에서 키워드를 선택해 주세요.")
        return pd.DataFrame(columns=["period", "keyword", "ratio"])

    start_str, end_str = date_range

    df = get_keyword_trend(
        keywords,
        cid,
        start_str,
        end_str,
        time_unit="week",
        gender="",
        ages=ages,
    )

    if df.empty:
        st.warning(f"{gender_label} 키워드 트렌드 데이터를 불러올 수 없습니다.")
        return pd.DataFrame(columns=["period", "keyword", "ratio"])

    # ── 차트 ─────────────────────────────────────────────────────
    fig = go.Figure()

    for i, kw in enumerate(keywords):
        df_kw = df[df["keyword"] == kw].sort_values("period").copy()
        if df_kw.empty:
            continue

        x_vals = df_kw["period"].tolist()
        y_vals = df_kw["ratio"].astype(float).tolist()
        color  = _KW_COLORS[i % len(_KW_COLORS)]

        fig.add_trace(go.Scatter(
            x=x_vals, y=y_vals,
            mode="lines+markers",
            name=kw,
            line=dict(color=color, width=2.5),
            marker=dict(size=5),
        ))

        # 피크 마커 + annotation (포인트 하단, 지수값 생략)
        if y_vals:
            peak_idx = int(np.argmax(y_vals))
            px_val   = float(y_vals[peak_idx])
            px_date  = x_vals[peak_idx]

            fig.add_trace(go.Scatter(
                x=[px_date], y=[px_val],
                mode="markers",
                marker=dict(symbol="circle", color=color, size=12),
                showlegend=False,
            ))
            fig.add_annotation(
                x=px_date, y=px_val,
                text=f"<b>{kw}</b><br>{px_date}",
                showarrow=True, arrowhead=2, arrowcolor=color,
                ax=0, ay=40,
                font=dict(color=color, size=11),
            )

    fig.update_layout(
        yaxis=dict(
            range=[0, 100], title="클릭 지수",
            showgrid=True, gridcolor="#f0f0f0",
        ),
        xaxis=dict(
            showgrid=False,
            tickformat="%m/%d",
            tickfont=dict(size=10),
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=11),
        ),
        height=360,
        margin=dict(l=20, r=20, t=50, b=40),
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"trend_{chart_key}")
    return df


# ════════════════════════════════════════════════════════════════════
# [3행] 키워드 비교 분석 테이블
# ════════════════════════════════════════════════════════════════════

def _comment(recent7_avg: float, total_avg: float) -> str:
    """규칙 기반 코멘트 (LLM 호출 없음)"""
    if total_avg == 0:
        return "➡️ 보합"
    ratio = recent7_avg / total_avg
    if ratio > 1.3:
        return "🔺 급등세"
    if ratio > 1.1:
        return "📈 상승세"
    if ratio < 0.7:
        return "📉 하락세"
    return "➡️ 보합"


def _build_stats_df(df: pd.DataFrame, show_cv: bool) -> pd.DataFrame:
    """trend DataFrame → 비교 분석 통계 DataFrame"""
    if df.empty:
        return pd.DataFrame()

    rows = []
    for kw in df["keyword"].unique():
        df_kw  = df[df["keyword"] == kw].sort_values("period").copy()
        ratios = df_kw["ratio"].astype(float).values

        if len(ratios) == 0:
            continue

        total_avg = float(ratios.mean())
        peak_idx  = int(np.argmax(ratios))
        peak_date = str(df_kw["period"].iloc[peak_idx])
        peak_val  = float(ratios[peak_idx])

        # 최근 7일(1주) / 30일(4주) 평균 — week 단위 데이터 기준
        n_7d  = 1
        n_30d = min(4, len(ratios))
        recent_7d_avg  = float(ratios[-n_7d:].mean())
        recent_30d_avg = float(ratios[-n_30d:].mean())

        row: dict = {
            "키워드":          kw,
            "피크 시점":       peak_date,
            "피크 지수":       f"{peak_val:.2f}",
            "평균 지수":       f"{total_avg:.2f}",
            "최근 7일 평균":   f"{recent_7d_avg:.2f}",
            "최근 30일 평균":  f"{recent_30d_avg:.2f}",
            "코멘트":          _comment(recent_7d_avg, total_avg),
        }

        if show_cv:
            std_val = float(ratios.std()) if len(ratios) > 1 else 0.0
            cv_val  = (std_val / total_avg) if total_avg > 0 else 0.0
            row["표준편차"]      = f"{std_val:.2f}"
            row["변동계수(CV)"] = f"{cv_val:.2f}"

        rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _show_stats_table(
    df_stats: pd.DataFrame,
    gender_label: str,
    table_key: str,
) -> None:
    """단일 성별 통계 테이블 렌더링"""
    st.markdown(
        f"<div style='font-size:15px;font-weight:700;margin:8px 0 6px;color:#333'>"
        f"{gender_label} 키워드 통계</div>",
        unsafe_allow_html=True,
    )
    if df_stats.empty:
        st.info("1행에서 키워드를 선택해 주세요.")
        return

    styled = (
        df_stats.style
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
    st.dataframe(styled, use_container_width=True, hide_index=True, key=table_key)


def _render_comparison_table(
    df_women: pd.DataFrame,
    df_men: pd.DataFrame,
    date_range: tuple[str, str],
    unified_mode: bool = False,
) -> None:
    """여성 / 남성 키워드 비교 분석 테이블 (각각 별도 표시).
    unified_mode=True 시 단일 테이블 전체 너비로 표시 (패션잡화용).
    """
    if df_women.empty and df_men.empty:
        st.info("비교 분석할 데이터가 없습니다. 1행에서 키워드를 선택해 주세요.")
        return

    end_dt      = date.fromisoformat(date_range[1])
    start_dt    = date.fromisoformat(date_range[0])
    period_days = (end_dt - start_dt).days + 1
    # date_range 기간이 28일(4주) 이상일 때만 표준편차·CV 컬럼 표시
    show_cv = period_days >= 28

    if unified_mode:
        # 패션잡화: df_women에 통합 데이터가 담김, 단일 전체 너비 테이블
        df_u_stats = _build_stats_df(df_women, show_cv)
        _show_stats_table(df_u_stats, "📊 통합", "cmp_tbl_u")
    else:
        df_w_stats = _build_stats_df(df_women, show_cv)
        df_m_stats = _build_stats_df(df_men,   show_cv)

        col_l, col_r = st.columns(2)

        with col_l:
            _show_stats_table(df_w_stats, "👩 여성", "cmp_tbl_w")

        with col_r:
            _show_stats_table(df_m_stats, "👨 남성", "cmp_tbl_m")


# ════════════════════════════════════════════════════════════════════
# 메인 진입점
# ════════════════════════════════════════════════════════════════════

def render() -> None:
    f = st.session_state.get("filter", {})
    if not f or "week_end" not in f:
        st.warning("사이드바에서 필터를 설정해 주세요.")
        return

    female_cid, male_cid = _get_tab2_cids(f)
    week_end   = f["week_end"]
    week_start = f["week_start"]
    ages       = f.get("ages", [])
    sub_cat    = f.get("sub_cat", "전체")
    mid_cat    = f.get("mid_cat", "여성의류")
    main_cat   = f.get("main_cat", "패션의류")

    # 패션잡화는 소분류 없이 중분류를 표시 기준으로 사용
    is_fashion  = (main_cat == "패션의류")
    display_cat = sub_cat if is_fashion else mid_cat

    # ── session_state 초기화 ─────────────────────────────────────
    if "tab2_extra_keywords_women" not in st.session_state:
        st.session_state["tab2_extra_keywords_women"] = ""
    if "tab2_extra_keywords_men" not in st.session_state:
        st.session_state["tab2_extra_keywords_men"] = ""
    if "tab2_extra_keywords_unified" not in st.session_state:
        st.session_state["tab2_extra_keywords_unified"] = ""

    # 조회 기간: 최근 28일 고정 (UI 필터 없음)
    date_range: tuple[str, str] = (
        (date.fromisoformat(week_end) - timedelta(days=28)).strftime("%Y-%m-%d"),
        week_end,
    )

    # ── 타이틀 ────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:22px;font-weight:800;margin-bottom:2px'>"
        "키워드 트렌드 분석</h2>",
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

    # ════════════════════════════════════════════════════════════
    # [1행] 주간 키워드 Top20 랭킹 (체크박스 선택)
    # ════════════════════════════════════════════════════════════
    _section_header(f"① {display_cat} 카테고리 주간 인기 키워드 Top 20")
    _period_badge(week_start, week_end, "선택 주간")

    if is_fashion:
        # 패션의류: 여성/남성 2열 구성
        col1_l, col1_r = st.columns(2)

        with col1_l:
            st.markdown(
                "<div style='font-size:16px;font-weight:700;margin-bottom:6px;color:#333'>"
                "👩 여성 키워드 랭킹</div>",
                unsafe_allow_html=True,
            )
            if female_cid:
                _render_ranking_table(
                    female_cid, "여성", "tab2_selected_keywords_women", f
                )
            else:
                st.info("여성 카테고리 데이터가 없습니다.")

        with col1_r:
            st.markdown(
                "<div style='font-size:16px;font-weight:700;margin-bottom:6px;color:#333'>"
                "👨 남성 키워드 랭킹</div>",
                unsafe_allow_html=True,
            )
            if male_cid:
                _render_ranking_table(
                    male_cid, "남성", "tab2_selected_keywords_men", f
                )
            else:
                st.info("해당없음 — 선택 카테고리에 남성 CID가 없습니다.")
    else:
        # 패션잡화: 단일 열, 통합 키워드 랭킹
        st.markdown(
            "<div style='font-size:16px;font-weight:700;margin-bottom:6px;color:#333'>"
            "📊 통합 키워드 랭킹</div>",
            unsafe_allow_html=True,
        )
        if female_cid:
            _render_ranking_table(
                female_cid, "통합", "tab2_selected_keywords_unified", f
            )
        else:
            st.info("카테고리 데이터가 없습니다.")

    st.divider()

    # ════════════════════════════════════════════════════════════
    # [2행] 선택 키워드 시계열 라인차트
    # ════════════════════════════════════════════════════════════
    _section_header(f"② {display_cat} 카테고리 키워드 트렌드 (4주)")

    if is_fashion:
        # 패션의류: 여성/남성 2열 구성
        col2_l, col2_r = st.columns(2)

        # ── 여성 차트 ──────────────────────────────────────────
        with col2_l:
            st.markdown(
                "<div style='font-size:15px;font-weight:700;margin-bottom:4px;color:#333'>"
                "👩 여성 키워드 트렌드</div>",
                unsafe_allow_html=True,
            )
            extra_raw_w = st.text_input(
                "키워드 직접 추가 (쉼표 구분)",
                value=st.session_state.get("tab2_extra_keywords_women", ""),
                key="tab2_extra_w",
                placeholder="예: 코트, 패딩",
            )
            st.session_state["tab2_extra_keywords_women"] = extra_raw_w
            extra_kws_w = _parse_extra_keywords(extra_raw_w)

            sel_w = st.session_state.get("tab2_selected_keywords_women", [])
            if extra_kws_w:
                merged_w = extra_kws_w[:_MAX_KW]
                if len(extra_kws_w) > _MAX_KW:
                    st.warning(
                        f"키워드는 최대 {_MAX_KW}개까지 조회됩니다. "
                        f"앞 {_MAX_KW}개만 사용합니다."
                    )
            else:
                merged_w = list(sel_w)[:_MAX_KW]

            if female_cid:
                df_trend_w = _render_trend_chart(
                    female_cid, merged_w, date_range, "여성", "women", ages
                )
            else:
                st.info("여성 카테고리 데이터가 없습니다.")
                df_trend_w = pd.DataFrame(columns=["period", "keyword", "ratio"])

        # ── 남성 차트 ──────────────────────────────────────────
        with col2_r:
            st.markdown(
                "<div style='font-size:15px;font-weight:700;margin-bottom:4px;color:#333'>"
                "👨 남성 키워드 트렌드</div>",
                unsafe_allow_html=True,
            )
            extra_raw_m = st.text_input(
                "키워드 직접 추가 (쉼표 구분)",
                value=st.session_state.get("tab2_extra_keywords_men", ""),
                key="tab2_extra_m",
                placeholder="예: 코트, 패딩",
            )
            st.session_state["tab2_extra_keywords_men"] = extra_raw_m
            extra_kws_m = _parse_extra_keywords(extra_raw_m)

            sel_m = st.session_state.get("tab2_selected_keywords_men", [])
            if extra_kws_m:
                merged_m = extra_kws_m[:_MAX_KW]
                if len(extra_kws_m) > _MAX_KW:
                    st.warning(
                        f"키워드는 최대 {_MAX_KW}개까지 조회됩니다. "
                        f"앞 {_MAX_KW}개만 사용합니다."
                    )
            else:
                merged_m = list(sel_m)[:_MAX_KW]

            if male_cid:
                df_trend_m = _render_trend_chart(
                    male_cid, merged_m, date_range, "남성", "men", ages
                )
            else:
                st.info("해당없음 — 선택 카테고리에 남성 CID가 없습니다.")
                df_trend_m = pd.DataFrame(columns=["period", "keyword", "ratio"])

        _render_comparison_table(df_trend_w, df_trend_m, date_range)

    else:
        # 패션잡화: 단일 열 통합 차트
        st.markdown(
            "<div style='font-size:15px;font-weight:700;margin-bottom:4px;color:#333'>"
            "📊 통합 키워드 트렌드</div>",
            unsafe_allow_html=True,
        )
        extra_raw_u = st.text_input(
            "키워드 직접 추가 (쉼표 구분)",
            value=st.session_state.get("tab2_extra_keywords_unified", ""),
            key="tab2_extra_u",
            placeholder="예: 운동화, 슬리퍼",
        )
        st.session_state["tab2_extra_keywords_unified"] = extra_raw_u
        extra_kws_u = _parse_extra_keywords(extra_raw_u)

        sel_u = st.session_state.get("tab2_selected_keywords_unified", [])
        if extra_kws_u:
            merged_u = extra_kws_u[:_MAX_KW]
            if len(extra_kws_u) > _MAX_KW:
                st.warning(
                    f"키워드는 최대 {_MAX_KW}개까지 조회됩니다. "
                    f"앞 {_MAX_KW}개만 사용합니다."
                )
        else:
            merged_u = list(sel_u)[:_MAX_KW]

        if female_cid:
            df_trend_u = _render_trend_chart(
                female_cid, merged_u, date_range, "통합", "unified", ages
            )
        else:
            st.info("카테고리 데이터가 없습니다.")
            df_trend_u = pd.DataFrame(columns=["period", "keyword", "ratio"])

        _render_comparison_table(df_trend_u, pd.DataFrame(), date_range, unified_mode=True)
