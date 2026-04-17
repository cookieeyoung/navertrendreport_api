import datetime
import streamlit as st
from config import MAIN_CATEGORY, MID_CATEGORY, SUBCATEGORY_CID, FEMALE_ONLY_CATEGORIES
from pages import tab1_category, tab2_keyword, tab3_product, tab4_insight

st.set_page_config(
    page_title="네이버 트렌드 분석",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# pages/ 디렉터리 자동 감지로 생성되는 사이드바 상단 네비게이션 숨김
st.markdown(
    "<style>[data-testid='stSidebarNav']{display:none}</style>",
    unsafe_allow_html=True,
)

# ── 날짜 기준 ─────────────────────────────────────────────────────
_today      = datetime.date.today()
_cur_monday = _today - datetime.timedelta(days=_today.weekday())  # 이번 주 월요일

# ── 연도 목록 (today 기준 올해 ~ 2017, 최신순 내림차순) ──────────
_API_START_YEAR = 2017
_YEARS: list[int] = list(range(_today.year, _API_START_YEAR - 1, -1))


def _build_weeks(year: int) -> list[tuple[str, datetime.date, datetime.date]]:
    """해당 연도의 주차 목록 반환 (월요일 시작, 최신순 내림차순)

    - 현재 연도: 이번 주(미완성) 및 미래 주 제외 → default = 전주
    - 과거 연도: 해당 연도 마지막 주부터 시작
    - 형식: YYYY-WNN (MM/DD(월) ~ MM/DD(일))
    """
    result: list[tuple[str, datetime.date, datetime.date]] = []
    dec31 = datetime.date(year, 12, 31)
    d = dec31 - datetime.timedelta(days=dec31.weekday())  # 해당 연도 마지막 월요일

    while d.year == year:
        # 현재 연도: 이번 주(cur_monday) 포함 이후 제외
        if year == _today.year and d >= _cur_monday:
            d -= datetime.timedelta(weeks=1)
            continue
        we = d + datetime.timedelta(days=6)
        _, wn, _ = d.isocalendar()
        label = f"{year}-{wn}주차({d.strftime('%m/%d')}~{we.strftime('%m/%d')})"
        result.append((label, d, we))
        d -= datetime.timedelta(weeks=1)

    return result  # 이미 최신순 내림차순


_AGE_CODE_MAP: dict[str, int] = {
    "10대": 10, "20대": 20, "30대": 30,
    "40대": 40, "50대": 50, "60대이상": 60,
}

# ── 사이드바 ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("📡 네이버 트렌드 분석")
    st.divider()

    # ── 카테고리 ────────────────────────────────────────────────────

    # 1) 대분류 (단일선택, default 패션의류)
    main_cat: str = st.selectbox(
        "대분류",
        list(MAIN_CATEGORY.keys()),
        index=0,
        key="main_cat_select",
    )

    # 2) 중분류 (단일선택, default 여성의류 / 대분류별 목록)
    _mid_options = list(MID_CATEGORY.get(main_cat, {}).keys())
    if _mid_options:
        mid_cat: str = st.selectbox(
            "중분류",
            _mid_options,
            index=0,
            key="mid_cat_select",
        )
    else:
        mid_cat = ""
        st.caption("ℹ️ 해당 대분류의 중분류는 준비 중입니다.")

    # 3) 소분류 (단일선택, 패션의류 한정 — 현행 유지)
    if main_cat == "패션의류":
        sub_cat: str = st.selectbox(
            "소분류 (카테고리)",
            list(SUBCATEGORY_CID.keys()),
            index=0,
            key="sub_cat_select",
        )
    else:
        sub_cat = "전체"

    st.divider()

    # ── 조회기간 ────────────────────────────────────────────────────

    # 4) 연도 (단일선택, default today 기준 올해, 최신순 내림차순)
    selected_year: int = st.selectbox(
        "연도",
        _YEARS,
        index=0,
        format_func=lambda y: f"{y}년",
        key="year_select",
    )

    # 5) 주차 (단일선택, 선택 연도의 전체 주차 / default 전주)
    #    주차는 월요일~일요일 단위로만 구성됩니다.
    _weeks = _build_weeks(selected_year)
    _week_labels = [w[0] for w in _weeks]
    _week_map    = {w[0]: (w[1], w[2]) for w in _weeks}

    selected_week: str = st.selectbox(
        "주차",
        _week_labels,
        index=0,                              # default: 전주(현재연도) 또는 마지막주(과거연도)
        key=f"week_select_{selected_year}",   # 연도 변경 시 주차 선택 초기화
        help="주차는 월요일~일요일 단위로만 구성됩니다.",
    )
    week_start, week_end = _week_map[selected_week]

    st.divider()

    # ── 연령 (다중선택, default 전체 — 현행 유지) ────────────────
    _age_options = ["전체", "10대", "20대", "30대", "40대", "50대", "60대이상"]
    selected_ages: list[str] = st.multiselect(
        "연령",
        _age_options,
        default=["전체"],
        key="age_select",
    )

    # ── 하단 도장 ─────────────────────────────────────────────────
    st.divider()
    _now = datetime.datetime.now().strftime("%H:%M:%S")
    st.markdown(
        f"<div style='font-size:11px;color:#888;text-align:center'>"
        f"✅ 인증 완료 &nbsp;|&nbsp; 업데이트: {_now}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='text-align:center;margin-top:6px'>"
        "<a href='https://www.linkedin.com/in/chaeyoungkimda/' target='_blank' "
        "style='font-size:12px;color:#0077b5;text-decoration:none;font-weight:600'>"
        "@chaeyoungkim</a></div>",
        unsafe_allow_html=True,
    )

# ── 연령 API 파라미터 변환 ────────────────────────────────────────
if not selected_ages or "전체" in selected_ages:
    ages_api: list[int] = []
else:
    ages_api = [_AGE_CODE_MAP[a] for a in selected_ages if a in _AGE_CODE_MAP]

# ── CID 결정 ──────────────────────────────────────────────────────
_mid_cid: str = MID_CATEGORY.get(main_cat, {}).get(mid_cat, MAIN_CATEGORY[main_cat])

if main_cat == "패션의류":
    female_cid: str | None = SUBCATEGORY_CID[sub_cat]["여성"]
    male_cid:   str | None = SUBCATEGORY_CID[sub_cat]["남성"]
else:
    female_cid = MAIN_CATEGORY[main_cat]
    male_cid   = None

# ── session_state["filter"] ───────────────────────────────────────
st.session_state["filter"] = {
    # 계층형 카테고리
    "main_cat":     main_cat,
    "main_cat_cid": MAIN_CATEGORY[main_cat],
    "mid_cat":      mid_cat,
    "mid_cat_cid":  _mid_cid,
    "sub_cat":      sub_cat,
    # 조회기간
    "year":         selected_year,
    "week_label":   selected_week,
    "week_start":   week_start.strftime("%Y-%m-%d"),
    "week_end":     week_end.strftime("%Y-%m-%d"),
    # 연령
    "ages":         ages_api,
    # CID (탭 렌더링용)
    "female_cid":   female_cid,
    "male_cid":     male_cid,
    # 하위 호환 (tabs 2-4)
    "start_date":           week_start.strftime("%Y-%m-%d"),
    "end_date":             week_end.strftime("%Y-%m-%d"),
    "category":             main_cat,
    "category_code":        MAIN_CATEGORY[main_cat],
    "sub_category":         sub_cat,
    "sub_category_code":    female_cid or "",
    "sub_category_codes":   [c for c in [female_cid, male_cid] if c],
    "gender":               "",
}

# ── 탭 ────────────────────────────────────────────────────────────
t1, t2, t3, t4 = st.tabs([
    "📊 쇼핑 트렌드 분석",
    "🔍 세부 키워드 분석",
    "🛍️ 네이버쇼핑 마켓 분석",
    "💡 종합 리포트",
])
with t1: tab1_category.render()
with t2: tab2_keyword.render()
with t3: tab3_product.render()
with t4: tab4_insight.render()
