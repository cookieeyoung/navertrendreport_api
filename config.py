import datetime
import os

import streamlit as st

def _secret(key: str) -> str:
    """Streamlit Cloud → st.secrets, 로컬 → .env (python-dotenv) 순으로 조회"""
    try:
        return st.secrets[key]
    except Exception:
        pass
    # 로컬 개발: python-dotenv 가 있으면 .env 로드
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv(key, "")

DATALAB_ID      = _secret("NAVER_DATALAB_CLIENT_ID")
DATALAB_SECRET  = _secret("NAVER_DATALAB_CLIENT_SECRET")
SHOPPING_ID     = _secret("NAVER_SHOPPING_CLIENT_ID")
SHOPPING_SECRET = _secret("NAVER_SHOPPING_CLIENT_SECRET")

_today        = datetime.date.today()
DEFAULT_END   = _today
DEFAULT_START = _today - datetime.timedelta(days=_today.weekday())  # 금주 월요일

# ─────────────────────────────────────────────────────────────────
# 대분류 CID 매핑
# ─────────────────────────────────────────────────────────────────
MAIN_CATEGORY: dict[str, str] = {
    "패션의류": "50000000",
    "패션잡화": "50000001",
}

# ─────────────────────────────────────────────────────────────────
# 중분류 CID 매핑 (대분류별)
# ─────────────────────────────────────────────────────────────────
MID_CATEGORY: dict[str, dict[str, str]] = {
    "패션의류": {
        "여성의류": "50000167",
        "남성의류": "50000169",
    }
    ,"패션잡화": {
        "전체": "50000001",
        "여성신발": "50000173",
        "남성신발": "50000174",
        "여성가방": "50000176",
        "남성가방": "50000177",
        # "여행용가방/소품": "50000178",
        "지갑": "50000179",
        "벨트": "50000180",
        "모자": "50000181",
        "장갑": "50000182",
        "양말": "50000166",
        "선글라스/안경테": "50000183",
        # "헤어액세서리": "50000184",
        # "패션소품": "50000185",
        "시계": "50000186",
        "주얼리": "50000189",
    },
}

# ─────────────────────────────────────────────────────────────────
# 소분류 CID 매핑 (패션의류 기준, 여성/남성 각각)
# None: 해당 성별 카테고리 없음
# ─────────────────────────────────────────────────────────────────
SUBCATEGORY_CID: dict[str, dict[str, str | None]] = {
    "전체":          {"여성": "50000167", "남성": "50000169"},
    "아우터":        {"여성": "50021359", "남성": "50021639"},
    "니트/스웨터":   {"여성": "50021279", "남성": "50021559"},
    "점퍼":          {"여성": "50000814", "남성": "50000837"},
    "블라우스/셔츠": {"여성": "50000804", "남성": "50000833"},
    "티셔츠":        {"여성": "50000803", "남성": "50000830"},
    "바지":          {"여성": "50000810", "남성": "50000836"},
    "청바지":        {"여성": "50000809", "남성": "50000835"},
    "원피스":        {"여성": "50000807", "남성": None},
    "스커트":        {"여성": "50000808", "남성": None},
    "트레이닝복":    {"여성": "50000818", "남성": "50000841"},
    "레깅스":        {"여성": "50000812", "남성": None},
}

# 남성 CID 없는 카테고리
FEMALE_ONLY_CATEGORIES: list[str] = [
    k for k, v in SUBCATEGORY_CID.items() if v["남성"] is None
]
