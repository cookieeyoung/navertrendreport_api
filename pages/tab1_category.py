"""
Tab 1 — 카테고리별 판매 트렌드 추이 (판매 PLC OVERVIEW)

쇼핑인사이트 API 클릭량 기반 카테고리 구매 행동 시계열 분석.
참조: docs/current/prd_tab1.md

1그룹 (3행 1열 전체 너비):
  ① 주차별 시계열 — 당해 vs 전년 비교 라인차트
  ② 전년 PLC 시계열 — 선택연도 전년 1년치 + 피크시점 annotation
  ③ 전년 PLC 분석 테이블 — 시즌구분/피크/성장/쇠퇴/핵심판매주간

2그룹 (1열 or 2열):
  시즌별 피크시점 주간 인기 키워드 Top 10
"""

import json
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.shopping_insight import get_category_trend, get_keyword_ranking
from config import SUBCATEGORY_CID, FEMALE_ONLY_CATEGORIES

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
_LAYOUT_BASE = dict(
    font_family="Noto Sans KR, sans-serif",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

_PLC_CRITERIA_HELP = (
    "📌 PLC 기준\n"
    "\n"
    "● 피크: S/S·F/W 시즌별 최대 클릭지수 지점\n"
    "   S/S = 2~10월 / F/W = 11·12·1월\n"
    "\n"
    "↑ 성장시점: 저점(valley) 이후 2주 연속 상승 시작\n"
    "↓ 하락시점: 피크 이후 2주 연속 하락 시작\n"
    "■ 핵심판매주간: 피크값 × 70% 이상 연속 구간\n"
)


# ════════════════════════════════════════════════════════════════════
# 유틸 함수
# ════════════════════════════════════════════════════════════════════

def _fmt_dow(date_str: str) -> str:
    """'2026-04-06' → '2026-04-06(월)'"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
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


def _iso_weeks_in_year(year: int) -> int:
    """해당 연도의 ISO 주차 수 (52 or 53)"""
    return date(year, 12, 28).isocalendar()[1]


def _get_cid(f: dict) -> str | None:
    """
    필터(f)에서 현재 선택된 단일 CID 반환.
    중분류(여성의류/남성의류) 기준으로 소분류 CID 결정.
    """
    main_cat = f.get("main_cat", "패션의류")
    mid_cat  = f.get("mid_cat", "여성의류")
    sub_cat  = f.get("sub_cat", "전체")

    if main_cat != "패션의류":
        return f.get("mid_cat_cid")

    gender_key = "여성" if "여성" in mid_cat else "남성"
    cid_dict = SUBCATEGORY_CID.get(sub_cat, SUBCATEGORY_CID.get("전체", {}))
    return cid_dict.get(gender_key)


def _age_param(f: dict) -> str:
    """연령 필터 → API 단일 age 문자열 (복수·전체 시 '')"""
    ages = f.get("ages", [])
    return str(ages[0]) if len(ages) == 1 else ""


# ════════════════════════════════════════════════════════════════════
# 피크 감지 & PLC 알고리즘
# ════════════════════════════════════════════════════════════════════

def _find_main_peaks(ratios: np.ndarray, periods: np.ndarray) -> list[int]:
    """
    S/S · F/W 시즌별 최대값 피크 인덱스 반환 (최대 2개).

    - S/S 기간: 2~10월  /  F/W 기간: 11·12·1월
    - 각 시즌에서 최대값 1개 (동일 시즌 내 중복 피크 없음)
    - 시즌 내 최대값 < 전체 최대 × 0.35 이면 해당 시즌 피크 제외
    - 유효 시즌 2개 → 피크 2개(S/S, F/W) / 1개 → 피크 1개("전체")
    """
    n = len(ratios)
    if n < 3:
        return [int(np.argmax(ratios))]

    global_max = float(ratios.max())
    if global_max == 0:
        return [0]

    min_height = global_max * 0.35

    ss_indices: list[int] = []
    fw_indices: list[int] = []
    for i, p in enumerate(periods):
        month = datetime.strptime(str(p), "%Y-%m-%d").month
        if month in (11, 12, 1):
            fw_indices.append(i)
        else:
            ss_indices.append(i)

    peaks: list[int] = []
    for indices in (ss_indices, fw_indices):
        if not indices:
            continue
        best_local  = int(np.argmax(ratios[indices]))
        best_global = indices[best_local]
        if ratios[best_global] >= min_height:
            peaks.append(best_global)

    if not peaks:
        peaks = [int(np.argmax(ratios))]

    return sorted(peaks)


def _find_growth_start(ratios: np.ndarray, peak_idx: int) -> int:
    """
    피크 이전 성장 시작 인덱스.

    - 피크 이전 구간의 최솟값(valley) 탐색
    - valley 이후 처음으로 2주 연속 상승하는 시점 반환
    - 연속 상승 없으면 valley 인덱스 반환
    - edge: peak_idx ≤ 1 → 0 반환 (연초 끊김)
    """
    if peak_idx <= 1:
        return 0
    pre        = ratios[: peak_idx + 1]
    valley_idx = int(np.argmin(pre))
    for i in range(valley_idx, peak_idx - 1):
        if ratios[i + 1] > ratios[i] and ratios[i + 2] > ratios[i + 1]:
            return i
    return valley_idx


def _find_decline_start(ratios: np.ndarray, peak_idx: int) -> int:
    """
    피크 이후 쇠퇴 시작 인덱스.

    - 피크 이후 처음으로 2주 연속 하락하는 시점 반환
    - 끝까지 연속 하락 없으면 마지막 인덱스 반환 (연말 끊김 처리)
    """
    n = len(ratios)
    for i in range(peak_idx, n - 2):
        if ratios[i + 1] < ratios[i] and ratios[i + 2] < ratios[i + 1]:
            return i + 1
    return n - 1


def _find_core_period(ratios: np.ndarray, peak_idx: int, threshold: float = 0.70) -> tuple[int, int]:
    """핵심판매 구간 인덱스 — peak 기준 threshold 이상인 연속 구간"""
    peak_val = float(ratios[peak_idx])
    min_val  = peak_val * threshold
    n        = len(ratios)

    start = peak_idx
    while start > 0 and ratios[start - 1] >= min_val:
        start -= 1

    end = peak_idx
    while end < n - 1 and ratios[end + 1] >= min_val:
        end += 1

    return start, end


def _classify_season(period_str: str) -> str:
    """피크 날짜 월 → 시즌: 11·12·1월 = 'F/W', 그 외 = 'S/S'"""
    month = datetime.strptime(period_str, "%Y-%m-%d").month
    return "F/W" if month in (11, 12, 1) else "S/S"


def _build_plc_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    전년 1년치 시계열 DataFrame → PLC 분석 테이블 DataFrame.

    Columns: 시즌구분, 피크시점, 성장시작, 쇠퇴시작, 핵심판매주간, 평균지수, 핵심판매주차수
    - 피크·성장시작·쇠퇴시작: 날짜 뒤에 해당 시점 클릭지수 표기
    - 핵심판매주간: 연초/연말 끊김 시 ↑/↓ 표시
    - 평균지수: 핵심판매 구간 평균 클릭지수
    """
    if df.empty or len(df) < 5:
        return pd.DataFrame()

    ratios  = df["ratio"].values.astype(float)
    periods = df["period"].values
    peaks   = _find_main_peaks(ratios, periods)
    n_total = len(ratios)

    rows = []
    for p_idx in peaks:
        season_label = (
            "전체"
            if len(peaks) == 1
            else _classify_season(str(periods[p_idx]))
        )
        growth_idx  = _find_growth_start(ratios, p_idx)
        decline_idx = _find_decline_start(ratios, p_idx)
        core_s, core_e = _find_core_period(ratios, p_idx)

        core_start_dt = datetime.strptime(str(periods[core_s]), "%Y-%m-%d")
        core_end_dt   = datetime.strptime(str(periods[core_e]), "%Y-%m-%d") + timedelta(days=6)
        n_weeks       = core_e - core_s + 1
        avg_ratio     = round(float(ratios[core_s : core_e + 1].mean()), 1)

        # 연초·연말 끊김 표시 (↑ = 이전 연도에서 이어짐, ↓ = 다음 연도로 이어짐)
        core_start_str = core_start_dt.strftime("%m/%d")
        core_end_str   = core_end_dt.strftime("%m/%d")
        if core_s == 0:
            core_start_str = "↑" + core_start_str
        if core_e == n_total - 1:
            core_end_str = core_end_str + "↓"

        rows.append({
            "시즌구분":       season_label,
            "평균지수":       f"{float(ratios[core_s : core_e + 1].mean()):.2f}",
            "피크시점":       str(periods[p_idx]),
            "피크지수":       f"{float(ratios[p_idx]):.2f}",
            "성장시점":       str(periods[growth_idx]),
            "성장지수":       f"{float(ratios[growth_idx]):.2f}",
            "하락시점":       str(periods[decline_idx]),
            "하락지수":       f"{float(ratios[decline_idx]):.2f}",
            "핵심판매주간":   f"{core_start_str} ~ {core_end_str}",
            "핵심판매주차수": f"{n_weeks}주간",
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        _order = {"S/S": 0, "F/W": 1, "전체": 0}
        result = (
            result.assign(_sort=result["시즌구분"].map(_order))
            .sort_values("_sort")
            .drop(columns="_sort")
            .reset_index(drop=True)
        )
    return result


# ════════════════════════════════════════════════════════════════════
# AI 코멘트 (Claude API / 규칙 기반 fallback)
# ════════════════════════════════════════════════════════════════════

# @st.cache_data(ttl=3600)
# def _get_ai_comment(
#     cur_json:  str,
#     prev_json: str,
#     sub_cat:   str,
#     year:      int,
#     mid_cat:   str,
# ) -> str:
#     """
#     당해 vs 전년 데이터를 Claude API에 전달해 1줄 코멘트 생성.
#     ANTHROPIC_API_KEY 미설정 시 규칙 기반 fallback.
#     """
#     def _rule_based(df_c: pd.DataFrame, df_p: pd.DataFrame) -> str:
#         if df_c.empty or df_p.empty:
#             return "데이터 부족으로 분석이 어렵습니다."
#         diff     = df_c["ratio"].mean() - df_p["ratio"].mean()
#         sign     = "강세" if diff > 0 else "약세"
#         cur_pk   = int(df_c["ratio"].idxmax()) + 1
#         prev_pk  = int(df_p["ratio"].idxmax()) + 1
#         wn_diff  = cur_pk - prev_pk
#         if wn_diff < 0:
#             wn_msg = f"피크 시점은 {abs(wn_diff)}주 빠름."
#         elif wn_diff > 0:
#             wn_msg = f"피크 시점은 {wn_diff}주 늦음."
#         else:
#             wn_msg = "피크 시점은 전년과 동일."
#         return f"전년 대비 평균 클릭지수 {abs(diff):.1f} {sign}이며, {wn_msg}"

#     try:
#         df_c = pd.DataFrame(json.loads(cur_json))
#         df_p = pd.DataFrame(json.loads(prev_json))
#     except Exception:
#         return "코멘트 생성 실패: 데이터 파싱 오류"

#     try:
#         import anthropic
#         api_key = os.getenv("ANTHROPIC_API_KEY")
#         if not api_key:
#             return _rule_based(df_c, df_p)

#         n        = min(len(df_c), len(df_p))
#         cur_avg  = round(float(df_c["ratio"].mean()), 1)
#         prev_avg = round(float(df_p["ratio"].mean()), 1)
#         cur_pk   = int(df_c["ratio"].idxmax()) + 1
#         prev_pk  = int(df_p.iloc[:n]["ratio"].idxmax()) + 1
#         diff_avg = round(cur_avg - prev_avg, 1)
#         diff_wn  = cur_pk - prev_pk

#         prompt = (
#             f"{year}년 {mid_cat} [{sub_cat}] 카테고리 클릭지수 비교 분석.\n"
#             f"- 당해({year}): 평균 {cur_avg}, 피크 W{cur_pk:02d}\n"
#             f"- 전년({year - 1}): 평균 {prev_avg}, 피크 W{prev_pk:02d}\n"
#             f"- 전년 대비 평균 변화 {diff_avg:+.1f}, 피크 {diff_wn:+d}주\n"
#             f"위 데이터를 바탕으로 전년 대비 올해 판매 추이를 "
#             f"한 문장(30자 이내, 숫자 포함, 판단적 표현)으로 요약해줘."
#         )

#         client = anthropic.Anthropic(api_key=api_key)
#         msg = client.messages.create(
#             model="claude-haiku-4-5-20251001",
#             max_tokens=80,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         return msg.content[0].text.strip()

#     except Exception:
#         return _rule_based(df_c, df_p)


# ════════════════════════════════════════════════════════════════════
# 1그룹 Chart ①: 당해 vs 전년 비교 라인차트
# ════════════════════════════════════════════════════════════════════

def _render_chart1(f: dict, cid: str) -> None:
    year      = f.get("year", date.today().year)
    sub_cat   = f.get("sub_cat", "전체")
    mid_cat   = f.get("mid_cat", "여성의류")
    ages      = f.get("ages", [])
    prev_year = year - 1

    # ── 날짜 범위 계산 ─────────────────────────────────────────────
    cur_w01  = date.fromisocalendar(year, 1, 1)
    cur_end  = date.fromisoformat(f["week_end"])

    ws_dt    = date.fromisoformat(f["week_start"])
    _, iso_wn, _ = ws_dt.isocalendar()

    prev_max_wn = _iso_weeks_in_year(prev_year)
    eff_wn      = min(iso_wn, prev_max_wn)
    prev_w01    = date.fromisocalendar(prev_year, 1, 1)
    prev_end    = date.fromisocalendar(prev_year, eff_wn, 7)

    # ── API 호출 ──────────────────────────────────────────────────
    df_cur  = get_category_trend(
        cid,
        cur_w01.strftime("%Y-%m-%d"), cur_end.strftime("%Y-%m-%d"),
        time_unit="week", ages=ages,
    )
    df_prev = get_category_trend(
        cid,
        prev_w01.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d"),
        time_unit="week", ages=ages,
    )

    if df_cur.empty:
        st.caption("당해 데이터 없음")
        return

    # ── x축 정렬: 당해 날짜 기준, 전년을 같은 주 번호로 매핑 ──────
    x_cur    = df_cur["period"].tolist()
    y_cur    = df_cur["ratio"].tolist()
    n_prev   = min(len(x_cur), len(df_prev))
    x_prev   = x_cur[:n_prev]
    y_prev   = df_prev["ratio"].tolist()[:n_prev]

    # ── 차트 ─────────────────────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_cur, y=y_cur,
        mode="lines+markers",
        name=f"{year}년 (당해)",
        line=dict(color="#4a86e8", width=2.5),
        marker=dict(size=5),
    ))
    if y_prev:
        fig.add_trace(go.Scatter(
            x=x_prev, y=y_prev,
            mode="lines+markers",
            name=f"{prev_year}년 (전년)",
            line=dict(color="#e8954a", width=2, dash="dot"),
            marker=dict(size=4),
            opacity=0.85,
        ))

    fig.update_layout(
        yaxis=dict(
            range=[0, 100], title="클릭 지수",
            showgrid=True, gridcolor="#f0f0f0",
        ),
        xaxis=dict(showgrid=False, tickformat="%Y-%m-%d", tickfont=dict(size=10)),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=12),
        ),
        height=400,
        margin=dict(l=20, r=20, t=50, b=40),
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True, key="chart1_yoy")

    # ── AI 코멘트 ─────────────────────────────────────────────────
    # if not df_cur.empty and not df_prev.empty:
    #     comment = _get_ai_comment(
    #         df_cur[["period", "ratio"]].to_json(orient="records"),
    #         df_prev[["period", "ratio"]].to_json(orient="records"),
    #         sub_cat, year, mid_cat,
    #     )
    #     st.markdown(
    #         f"<div style='background:#f8f9fa;border-left:3px solid #4a86e8;"
    #         f"padding:8px 14px;border-radius:4px;font-size:13px;color:#333;"
    #         f"margin-top:2px'>🤖 {comment}</div>",
    #         unsafe_allow_html=True,
    #     )


# ════════════════════════════════════════════════════════════════════
# 1그룹 Chart ②: 전년 PLC 시계열 (1년 전체)
# ════════════════════════════════════════════════════════════════════

def _render_chart2(f: dict, cid: str) -> tuple[pd.DataFrame, list[int]]:
    """
    전년 1년치 PLC 시계열 차트 렌더링.
    반환: (df_prev_full, peak_indices)
    """
    year     = f.get("year", date.today().year)
    prev_year = year - 1
    ages     = f.get("ages", [])

    prev_w01      = date.fromisocalendar(prev_year, 1, 1)
    prev_max_wn   = _iso_weeks_in_year(prev_year)
    prev_last_sun = date.fromisocalendar(prev_year, prev_max_wn, 7)

    df = get_category_trend(
        cid,
        prev_w01.strftime("%Y-%m-%d"),
        prev_last_sun.strftime("%Y-%m-%d"),
        time_unit="week",
        ages=ages,
    )

    if df.empty:
        st.caption("전년 데이터 없음")
        return pd.DataFrame(), []

    ratios  = df["ratio"].values.astype(float)
    periods = df["period"].values
    peaks   = _find_main_peaks(ratios, periods)

    # ── 차트 ─────────────────────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(periods), y=list(ratios),
        mode="lines+markers",
        line=dict(color="#27ae60", width=2.5),
        marker=dict(size=5),
        showlegend=False,
    ))

    # S/S → 빨강, F/W → 파랑, 전체 → 빨강
    _SEASON_COLOR = {"S/S": "#e74c3c", "F/W": "#2980b9", "전체": "#e74c3c"}
    for p_idx in peaks:
        p_date  = str(periods[p_idx])
        p_val   = float(ratios[p_idx])
        season  = _classify_season(p_date) if len(peaks) > 1 else "전체"
        color   = _SEASON_COLOR.get(season, "#e74c3c")
        ay      = 55 if p_val > 72 else -65

        fig.add_trace(go.Scatter(
            x=[p_date], y=[p_val],
            mode="markers",
            marker=dict(symbol="circle", color=color, size=12),
            showlegend=False,
        ))
        fig.add_annotation(
            x=p_date, y=p_val,
            text=f"<b>피크({season})</b><br>{p_date}<br>지수: {p_val:.2f}",
            showarrow=True, arrowhead=2, arrowcolor=color,
            ax=0, ay=ay,
            font=dict(color=color, size=11),
        )

    # ── 핵심판매 구간 음영 (light pink vrect) ────────────────────
    for p_idx in peaks:
        cs, ce = _find_core_period(ratios, p_idx)
        x0_shade = str(periods[cs])
        x1_shade = (
            datetime.strptime(str(periods[ce]), "%Y-%m-%d") + timedelta(days=6)
        ).strftime("%Y-%m-%d")
        fig.add_vrect(
            x0=x0_shade, x1=x1_shade,
            fillcolor="#ffb3c6", opacity=0.18,
            layer="below", line_width=0,
        )

    fig.update_layout(
        yaxis=dict(
            range=[0, 100], title="클릭 지수",
            showgrid=True, gridcolor="#f0f0f0",
        ),
        xaxis=dict(
            showgrid=False,
            type="date",
            tickvals=[f"{prev_year}-{m:02d}-01" for m in range(1, 13)],
            ticktext=[f"{m:02d}월" for m in range(1, 13)],
            tickfont=dict(size=10),
        ),
        height=420,
        margin=dict(l=20, r=20, t=60, b=40),
        **_LAYOUT_BASE,
    )
    st.plotly_chart(fig, use_container_width=True, key="chart2_plc")

    return df, peaks


# ════════════════════════════════════════════════════════════════════
# 1그룹 Chart ③: 전년 PLC 분석 테이블
# ════════════════════════════════════════════════════════════════════

def _render_chart3(df_prev_full: pd.DataFrame) -> None:
    if df_prev_full.empty:
        st.caption("분석 데이터 없음")
        return

    tbl = _build_plc_table(df_prev_full)
    if tbl.empty:
        st.caption("PLC 분석 결과 없음")
        return

    def _row_style(row):
        s = row.get("시즌구분", "")
        if s == "F/W":
            return ["background-color:#e8f4fd"] * len(row)
        if s == "S/S":
            return ["background-color:#fef9e7"] * len(row)
        return [""] * len(row)

    styled = (
        tbl.style
        .apply(_row_style, axis=1)
        .set_properties(**{"text-align": "center", "font-size": "13px"})
        .set_table_styles([
            {"selector": "th", "props": [
                ("text-align", "center"),
                ("font-size", "13px"),
                ("font-weight", "700"),
            ]},
        ])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, key="plc_tbl")


# ════════════════════════════════════════════════════════════════════
# 2그룹: 시즌별 피크시점 인기 키워드 Top 20
# ════════════════════════════════════════════════════════════════════

def _render_group2(
    df_prev_full: pd.DataFrame,
    peaks:        list[int],
    cid:          str,
    f:            dict,
) -> None:
    if df_prev_full.empty or not peaks:
        st.caption("키워드 분석 데이터 없음")
        return

    periods   = df_prev_full["period"].values
    age_param = _age_param(f)

    # 시즌 레이블 결정 후 S/S → F/W 순으로 정렬
    season_labels = [
        ("전체" if len(peaks) == 1 else _classify_season(str(periods[p])))
        for p in peaks
    ]
    _season_order = {"S/S": 0, "F/W": 1, "전체": 0}
    _paired = sorted(zip(peaks, season_labels), key=lambda x: _season_order.get(x[1], 0))
    peaks         = [p for p, _ in _paired]
    season_labels = [s for _, s in _paired]

    cols = st.columns(len(peaks))

    for col, p_idx, season in zip(cols, peaks, season_labels):
        with col:
            peak_date_str = str(periods[p_idx])
            peak_dt = datetime.strptime(peak_date_str, "%Y-%m-%d")

            # 피크 해당 주 월~일
            peak_mon = peak_dt - timedelta(days=peak_dt.weekday())
            peak_sun = peak_mon + timedelta(days=6)
            # 전주 (순위 변동 비교)
            prev_mon = peak_mon - timedelta(days=7)
            prev_sun = peak_sun - timedelta(days=7)

            tag = f"[{season}] " if season != "전체" else ""
            st.markdown(
                f"<div style='font-size:15px;font-weight:700;margin-bottom:4px'>"
                f"🔑 {tag}피크주간 인기 키워드 랭킹</div>"
                f"<div style='font-size:12px;color:#666;margin-bottom:8px'>"
                f"📅 {peak_mon.strftime('%Y-%m-%d')} ~ {peak_sun.strftime('%Y-%m-%d')}</div>",
                unsafe_allow_html=True,
            )
            sort_opt = st.radio(
                "정렬 기준",
                ["순위", "상승순", "하락순"],
                horizontal=True,
                index=0,
                key=f"sort_{season}_{p_idx}",
                label_visibility="collapsed",
            )

            df_now = get_keyword_ranking(
                cid,
                peak_mon.strftime("%Y-%m-%d"),
                peak_sun.strftime("%Y-%m-%d"),
                age=age_param,
                count=20,
            )
            df_pw = get_keyword_ranking(
                cid,
                prev_mon.strftime("%Y-%m-%d"),
                prev_sun.strftime("%Y-%m-%d"),
                age=age_param,
                count=40,
            )

            if df_now.empty:
                st.caption("키워드 데이터 없음")
                continue

            prev_d: dict = (
                dict(zip(df_pw["keyword"], df_pw["rank"]))
                if not df_pw.empty else {}
            )

            def _change(row, _p=prev_d):
                p = _p.get(row["keyword"])
                if p is None:
                    return "NEW"
                d = p - row["rank"]
                return f"▲{d}" if d > 0 else (f"▼{abs(d)}" if d < 0 else "-")

            df_now = df_now.copy()
            df_now["전주대비 순위변화"] = df_now.apply(_change, axis=1)

            display_df = df_now[["rank", "keyword", "전주대비 순위변화"]].rename(
                columns={"rank": "순위", "keyword": "키워드"}
            )

            def _chg_num(val: str) -> float:
                if val == "NEW":
                    return float("inf")
                if val.startswith("▲"):
                    try: return float(val[1:])
                    except: return 0.0
                if val.startswith("▼"):
                    try: return -float(val[1:])
                    except: return 0.0
                return 0.0

            if sort_opt == "순위":
                display_df = display_df.sort_values("순위").reset_index(drop=True)
            elif sort_opt == "상승순":
                display_df = display_df.assign(
                    _s=display_df["전주대비 순위변화"].map(_chg_num)
                ).sort_values("_s", ascending=False).drop(columns="_s").reset_index(drop=True)
            elif sort_opt == "하락순":
                display_df = display_df.assign(
                    _s=display_df["전주대비 순위변화"].map(_chg_num)
                ).sort_values("_s", ascending=True).drop(columns="_s").reset_index(drop=True)
            def _style_chg(val):
                if isinstance(val, str) and val.startswith("▲"):
                    return "color: #2ecc71; font-weight: bold"
                if isinstance(val, str) and val.startswith("▼"):
                    return "color: #e74c3c; font-weight: bold"
                if isinstance(val, str) and val == "NEW":
                    return "color: #f39c12; font-weight: bold"
                return ""

            styled = (
                display_df.style
                .map(_style_chg, subset=["전주대비 순위변화"])
                .set_properties(**{"text-align": "center", "font-size": "14px"})
                .set_table_styles([{
                    "selector": "th",
                    "props": [("text-align", "center"), ("font-size", "14px")],
                }])
            )
            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=True,
                height=390,
                key=f"kw_tbl_{season}_{p_idx}",
            )


# ════════════════════════════════════════════════════════════════════
# 메인 진입점
# ════════════════════════════════════════════════════════════════════

def render() -> None:
    f = st.session_state.get("filter", {})
    if not f or "week_end" not in f:
        st.warning("사이드바에서 필터를 설정해 주세요.")
        return

    cid      = _get_cid(f)
    main_cat = f.get("main_cat", "패션의류")
    sub_cat  = f.get("sub_cat", "전체")
    mid_cat  = f.get("mid_cat", "여성의류")
    year     = f.get("year", date.today().year)
    prev_year = year - 1

    # 패션잡화는 소분류 없이 중분류를 표시 기준으로 사용
    display_cat = sub_cat if main_cat == "패션의류" else mid_cat

    # ── 타이틀 ────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:22px;font-weight:800;margin-bottom:2px'>"
        "카테고리별 쇼핑 트렌드 추이 "
        "<span style='font-size:14px;color:#6680aa;font-weight:500'>"
        "(쇼핑검색 PLC OVERVIEW)</span></h2>",
        unsafe_allow_html=True,
    )
    if main_cat == "패션의류":
        st.caption(f"📌 {main_cat} > {mid_cat} > {sub_cat} | {year}년")
    else:
        st.caption(f"📌 {main_cat} > {mid_cat} | {year}년")
    st.divider()

    # ── CID 없는 경우 ─────────────────────────────────────────────
    if cid is None:
        st.info(
            f"선택하신 카테고리 [{sub_cat}]는 {mid_cat}에 해당하는 데이터가 없습니다."
        )
        return

    # ════════════════════════════════════════════════════════════
    # 그룹
    # ════════════════════════════════════════════════════════════

    # ① 당해 vs 전년 비교
    _section_header(f"① {display_cat} 주차별 시계열 추이 — {year}년 vs {prev_year}년 비교")
    cur_w01_str = date.fromisocalendar(year, 1, 1).strftime("%Y-%m-%d")
    _period_badge(cur_w01_str, f["week_end"], f"{year}년 1주차 ~ 선택주차")
    _render_chart1(f, cid)

    st.divider()

    # ② 전년 PLC 시계열
    prev_w01_str  = date.fromisocalendar(prev_year, 1, 1).strftime("%Y-%m-%d")
    prev_max_wn   = _iso_weeks_in_year(prev_year)
    prev_last_str = date.fromisocalendar(prev_year, prev_max_wn, 7).strftime("%Y-%m-%d")

    _section_header(f"② {display_cat} 전년도 쇼핑검색 PLC (1년 전체)", help_text=_PLC_CRITERIA_HELP)
    _period_badge(prev_w01_str, prev_last_str)
    df_prev_full, peaks = _render_chart2(f, cid)

    # ③ PLC 분석 테이블
    _render_chart3(df_prev_full)

    st.divider()

    # st.markdown(
    #     "<div style='font-size:17px;font-weight:800;color:#1a3a6b;"
    #     "margin:4px 0 12px'>🔑 2그룹 — 피크시점 주간 인기 키워드 Top 20</div>",
    #     unsafe_allow_html=True,
    # )
    _section_header(f"③ {display_cat} 전년 피크주간 인기 키워드 Top20")
    _render_group2(df_prev_full, peaks, cid, f)
