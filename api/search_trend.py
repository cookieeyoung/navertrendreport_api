"""
통합검색어 트렌드 API
docs/api guide.md 3절 "통합검색어 트렌드 개요" 기준으로 구현

docs 3절에 기재된 사항:
  - keywordGroups: 여러 검색어를 하나의 주제군으로 묶어 합산 추이 분석
  - 응답: 0~100 상대적 지표 (설정 기간 내 최대 검색량 = 100)
  - 연령: 5세 단위 세분화 (doc 설명용, API ages 파라미터는 10세 단위)

공통 파라미터 (docs 4절 공통 파라미터 준용):
  startDate, endDate, timeUnit, device, gender, ages

TODO: 엔드포인트 URL이 docs에 명시되어 있지 않습니다.
      아래 URL은 관례에 따라 기재했으나 공식 문서에서 확인 필요.
      (docs에서 쇼핑인사이트는 /v1/datalab/shopping/... 임을 확인)
"""

import hashlib
import json
import os
import datetime
import streamlit as st
import pandas as pd
import requests

from config import DATALAB_ID, DATALAB_SECRET

CACHE_DIR = "data/cache"

# TODO: docs에 URL 미기재 — 아래 URL은 네이버 공식 문서 확인 후 교체
_SEARCH_TREND_URL = "https://openapi.naver.com/v1/datalab/search"


def _headers() -> dict:
    """docs 0절 — X-Naver-Client-Id / X-Naver-Client-Secret"""
    return {
        "X-Naver-Client-Id": DATALAB_ID,
        "X-Naver-Client-Secret": DATALAB_SECRET,
        "Content-Type": "application/json",
    }


def _cache_path(func_name: str, params: dict) -> str:
    today = datetime.date.today().isoformat()
    params_hash = hashlib.md5(
        json.dumps(params, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{func_name}_{params_hash}_{today}.json")


def _load_cache(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


@st.cache_data(ttl=3600)
def get_search_trend(
    keyword_groups: list,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
    gender: str = "",
    ages: list = [],
) -> pd.DataFrame:
    """
    통합검색어 트렌드 조회 (docs 3절 기준)

    TODO: URL이 docs에 명시되지 않음 — 확인 후 _SEARCH_TREND_URL 교체

    Parameters
    ----------
    keyword_groups : list of dict
        구조: [{"groupName": "그룹명", "keywords": ["키워드1", ...]}, ...]
        docs 3절 "주제군 설정" 참고

    gender : str
        docs 4절 공통 파라미터 — "m" / "f" / "" (전체)

    ages : list of int
        docs 4절 공통 파라미터 — [10, 20, 30, 40, 50, 60]

    Returns
    -------
    DataFrame: columns = ["period", "group_name", "ratio"]
    """
    params = {
        "func": "get_search_trend",
        "keyword_groups": keyword_groups,
        "start_date": start_date,
        "end_date": end_date,
        "time_unit": time_unit,
        "gender": gender,
        "ages": ages,
    }
    cache_file = _cache_path("get_search_trend", params)
    cached = _load_cache(cache_file)
    if cached is not None:
        return pd.DataFrame(cached)

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": keyword_groups,
    }
    if gender:
        body["gender"] = gender
    if ages:
        body["ages"] = ages

    try:
        resp = requests.post(_SEARCH_TREND_URL, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for result in data.get("results", []):
            group_name = result["title"]
            for point in result.get("data", []):
                rows.append({
                    "period": point["period"],
                    "group_name": group_name,
                    "ratio": point["ratio"],
                })
        df = pd.DataFrame(rows, columns=["period", "group_name", "ratio"])
        _save_cache(cache_file, df.to_dict(orient="records"))
        return df
    except Exception as e:
        st.error(f"[get_search_trend] API 호출 실패: {e}")
        return pd.DataFrame(columns=["period", "group_name", "ratio"])
