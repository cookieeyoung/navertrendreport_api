"""
쇼핑인사이트 Datalab API
docs/api guide.md 4절 기준으로 구현

엔드포인트 (docs 4절):
  4.1  POST /v1/datalab/shopping/categories          — 분야별 트렌드
  4.5  POST /v1/datalab/shopping/category/keywords   — 키워드별 트렌드
  *    키워드 랭킹 엔드포인트는 docs에 명시되지 않음 → TODO 표시

공통 요청 파라미터 (docs 4절):
  startDate  string  Y   yyyy-mm-dd
  endDate    string  Y   yyyy-mm-dd
  timeUnit   string  Y   date / week / month
  category   array   Y/N 엔드포인트별 단일 string 또는 array(JSON)
  device     string  N   pc / mo  (미설정 시 전체)
  gender     string  N   m / f    (미설정 시 전체)
  ages       array   N   [10, 20, 30, 40, 50, 60]

헤더 (docs 0절):
  X-Naver-Client-Id
  X-Naver-Client-Secret
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

# ── 내부 유틸 ─────────────────────────────────────────────────────

def _headers() -> dict:
    """docs 0절 — X-Naver-Client-Id / X-Naver-Client-Secret 헤더"""
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


# ── 공개 함수 ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_category_trend(
    category_code,          # str 또는 list[str] — 다중 코드 시 합산 트렌드
    start_date: str,
    end_date: str,
    time_unit: str = "week",
    gender: str = "",
    ages: list = [],
) -> pd.DataFrame:
    """
    docs 4.1 — 쇼핑인사이트 분야별 트렌드 조회
    URL: POST https://openapi.naver.com/v1/datalab/shopping/categories

    category 파라미터: name + param(배열) 쌍의 JSON 배열 (docs 4.1)
    category_code: str 또는 list[str]. 리스트 전달 시 param 배열에 모두 포함 → 합산 트렌드
    응답: results[].data[].{period, ratio}  (docs 4.1)

    Returns
    -------
    DataFrame: columns = ["period", "ratio"]
    """
    codes = category_code if isinstance(category_code, list) else [category_code]

    url = "https://openapi.naver.com/v1/datalab/shopping/categories"
    params = {
        "func": "get_category_trend",
        "category_code": sorted(codes),   # 정렬 후 캐시 키 일관성 보장
        "start_date": start_date,
        "end_date": end_date,
        "time_unit": time_unit,
        "gender": gender,
        "ages": ages,
    }
    cache_file = _cache_path("get_category_trend", params)
    cached = _load_cache(cache_file)
    if cached is not None:
        return pd.DataFrame(cached)

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "category": [{"name": "category", "param": codes}],
    }
    if gender:
        body["gender"] = gender
    if ages:
        body["ages"] = ages

    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("results", [{}])[0].get("data", [])
        if not rows:
            return pd.DataFrame(columns=["period", "ratio"])
        df_raw = pd.DataFrame(rows)
        if not {"period", "ratio"}.issubset(df_raw.columns):
            return pd.DataFrame(columns=["period", "ratio"])
        df = df_raw[["period", "ratio"]]
        _save_cache(cache_file, df.to_dict(orient="records"))
        return df
    except Exception as e:
        st.error(f"[get_category_trend] API 호출 실패: {e}")
        return pd.DataFrame(columns=["period", "ratio"])


@st.cache_data(ttl=3600)
def get_keyword_ranking(
    category_code: str,
    start_date: str,
    end_date: str,
    gender: str = "",
    age: str = "",
    count: int = 20,
) -> pd.DataFrame:
    """
    네이버 데이터랩 쇼핑인사이트 — 분야 내 인기 검색어 순위 조회

    URL: POST https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver
    (브라우저 네트워크 탭에서 확인된 내부 엔드포인트)

    요청 형식: application/x-www-form-urlencoded
    요청 파라미터:
      cid       str  카테고리 코드 (config.py CATEGORY_MAP cat_id)
      timeUnit  str  "date" (고정)
      startDate str  "YYYY-MM-DD"
      endDate   str  "YYYY-MM-DD"
      age       str  "" / "10" / "20" / "30" / "40" / "50" / "60"
      gender    str  "" / "m" / "f"
      device    str  "" / "pc" / "mo"
      page      int  페이지 번호 (1부터)
      count     int  페이지당 결과 수 (최대 20)

    응답 필드 (확인됨):
      ranks[].rank     int  순위
      ranks[].keyword  str  키워드
      ranks[].linkId   str  (내부 링크용, 미사용)

    인증: X-Requested-With: XMLHttpRequest 헤더로 세션 쿠키 없이 호출 가능

    Returns
    -------
    DataFrame: columns = ["rank", "keyword"]
    """
    url = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"

    params_key = {
        "func": "get_keyword_ranking",
        "category_code": category_code,
        "start_date": start_date,
        "end_date": end_date,
        "gender": gender,
        "age": age,
        "count": count,
    }
    cache_file = _cache_path("get_keyword_ranking", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return pd.DataFrame(cached)

    req_headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://datalab.naver.com/shoppingInsight/siteKeyword.naver",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    form_data = {
        "cid":       category_code,
        "timeUnit":  "date",
        "startDate": start_date,
        "endDate":   end_date,
        "age":       age,
        "gender":    gender,
        "device":    "",
        "page":      "1",
        "count":     str(count),
    }

    try:
        resp = requests.post(url, headers=req_headers, data=form_data, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        ranks = data.get("ranks", [])
        df = pd.DataFrame(ranks)[["rank", "keyword"]] if ranks else pd.DataFrame(columns=["rank", "keyword"])
        _save_cache(cache_file, df.to_dict(orient="records"))
        return df
    except Exception as e:
        st.error(f"[get_keyword_ranking] API 호출 실패: {e}")
        return pd.DataFrame(columns=["rank", "keyword"])


@st.cache_data(ttl=3600)
def get_keyword_trend(
    keywords: list,
    category_code: str,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
    gender: str = "",
    ages: list = [],
) -> pd.DataFrame:
    """
    docs 4.5 — 쇼핑인사이트 키워드별 트렌드 조회
    URL: POST https://openapi.naver.com/v1/datalab/shopping/category/keywords

    category 파라미터: 단일 string (docs 4.5 특이사항)
    keyword 파라미터: name + param(1개) 쌍의 배열. 최대 5개 (docs 4.5)
    응답: results[].{title, data[].{period, ratio}}  (docs 4.5)

    Parameters
    ----------
    keywords : list of str  (최대 5개, docs 4.5)

    Returns
    -------
    DataFrame: columns = ["period", "keyword", "ratio"]
    """
    url = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"
    params = {
        "func": "get_keyword_trend",
        "keywords": sorted(keywords),
        "category_code": category_code,
        "start_date": start_date,
        "end_date": end_date,
        "time_unit": time_unit,
        "gender": gender,
        "ages": ages,
    }
    cache_file = _cache_path("get_keyword_trend", params)
    cached = _load_cache(cache_file)
    if cached is not None:
        return pd.DataFrame(cached)

    # docs 4.5: keyword.param은 1개만 설정 가능
    keyword_list = [{"name": kw, "param": [kw]} for kw in keywords]

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "category": category_code,
        "keyword": keyword_list,
    }
    if gender:
        body["gender"] = gender
    if ages:
        body["ages"] = ages

    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for result in data.get("results", []):
            kw_name = result["title"]
            for point in result.get("data", []):
                rows.append({
                    "period": point["period"],
                    "keyword": kw_name,
                    "ratio": point["ratio"],
                })
        df = pd.DataFrame(rows, columns=["period", "keyword", "ratio"])
        _save_cache(cache_file, df.to_dict(orient="records"))
        return df
    except Exception as e:
        st.error(f"[get_keyword_trend] API 호출 실패: {e}")
        return pd.DataFrame(columns=["period", "keyword", "ratio"])


# ── 성별·연령 비중 함수 ───────────────────────────────────────────

def _avg_by_group(data_list: list) -> dict:
    """results[0].data [{period, ratio, group}] → {group: avg_ratio}"""
    from collections import defaultdict
    sums, counts = defaultdict(float), defaultdict(int)
    for pt in data_list:
        g = str(pt["group"])
        sums[g] += pt["ratio"]
        counts[g] += 1
    return {g: sums[g] / counts[g] for g in sums}


@st.cache_data(ttl=3600)
def get_category_gender(
    category_code: str,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
) -> dict:
    """
    docs 4.3 — 쇼핑인사이트 분야 내 성별 트렌드
    URL: POST https://openapi.naver.com/v1/datalab/shopping/category/gender
    응답: results[0].data[].{period, ratio, group}  group = "m" / "f"

    Returns
    -------
    dict  {"m": avg_ratio, "f": avg_ratio}  (기간 평균, 합계 != 100)
    """
    url = "https://openapi.naver.com/v1/datalab/shopping/category/gender"
    params_key = {"func": "get_category_gender", "code": category_code,
                  "s": start_date, "e": end_date, "tu": time_unit}
    cache_file = _cache_path("get_category_gender", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return cached

    body = {"startDate": start_date, "endDate": end_date,
            "timeUnit": time_unit, "category": category_code}
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data_pts = resp.json().get("results", [{}])[0].get("data", [])
        result = _avg_by_group(data_pts) if data_pts else {}
        _save_cache(cache_file, result)
        return result
    except Exception as e:
        st.error(f"[get_category_gender] API 호출 실패: {e}")
        return {}


@st.cache_data(ttl=3600)
def get_category_age(
    category_code: str,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
) -> dict:
    """
    docs 4.4 — 쇼핑인사이트 분야 내 연령별 트렌드
    URL: POST https://openapi.naver.com/v1/datalab/shopping/category/age
    응답: results[0].data[].{period, ratio, group}  group = "10"/"20"/"30"/"40"/"50"/"60"

    Returns
    -------
    dict  {"10": avg, "20": avg, ..., "60": avg}
    """
    url = "https://openapi.naver.com/v1/datalab/shopping/category/age"
    params_key = {"func": "get_category_age", "code": category_code,
                  "s": start_date, "e": end_date, "tu": time_unit}
    cache_file = _cache_path("get_category_age", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return cached

    body = {"startDate": start_date, "endDate": end_date,
            "timeUnit": time_unit, "category": category_code}
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data_pts = resp.json().get("results", [{}])[0].get("data", [])
        result = _avg_by_group(data_pts) if data_pts else {}
        _save_cache(cache_file, result)
        return result
    except Exception as e:
        st.error(f"[get_category_age] API 호출 실패: {e}")
        return {}


@st.cache_data(ttl=3600)
def get_keyword_gender(
    keyword: str,
    category_code: str,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
) -> dict:
    """
    docs 4.7 — 쇼핑인사이트 키워드 성별 트렌드
    URL: POST https://openapi.naver.com/v1/datalab/shopping/category/keyword/gender
    keyword 파라미터: 단일 string (docs 확인값)

    Returns
    -------
    dict  {"m": avg_ratio, "f": avg_ratio}
    """
    url = "https://openapi.naver.com/v1/datalab/shopping/category/keyword/gender"
    params_key = {"func": "get_keyword_gender", "kw": keyword, "code": category_code,
                  "s": start_date, "e": end_date}
    cache_file = _cache_path("get_keyword_gender", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return cached

    body = {"startDate": start_date, "endDate": end_date,
            "timeUnit": time_unit, "category": category_code, "keyword": keyword}
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data_pts = resp.json().get("results", [{}])[0].get("data", [])
        result = _avg_by_group(data_pts) if data_pts else {}
        _save_cache(cache_file, result)
        return result
    except Exception as e:
        st.error(f"[get_keyword_gender] API 호출 실패: {e}")
        return {}


@st.cache_data(ttl=3600)
def get_keyword_age(
    keyword: str,
    category_code: str,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
) -> dict:
    """
    docs 4.8 — 쇼핑인사이트 키워드 연령별 트렌드
    URL: POST https://openapi.naver.com/v1/datalab/shopping/category/keyword/age
    keyword 파라미터: 단일 string (docs 확인값)

    Returns
    -------
    dict  {"10": avg, "20": avg, ..., "60": avg}
    """
    url = "https://openapi.naver.com/v1/datalab/shopping/category/keyword/age"
    params_key = {"func": "get_keyword_age", "kw": keyword, "code": category_code,
                  "s": start_date, "e": end_date}
    cache_file = _cache_path("get_keyword_age", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return cached

    body = {"startDate": start_date, "endDate": end_date,
            "timeUnit": time_unit, "category": category_code, "keyword": keyword}
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=10)
        resp.raise_for_status()
        data_pts = resp.json().get("results", [{}])[0].get("data", [])
        result = _avg_by_group(data_pts) if data_pts else {}
        _save_cache(cache_file, result)
        return result
    except Exception as e:
        st.error(f"[get_keyword_age] API 호출 실패: {e}")
        return {}
