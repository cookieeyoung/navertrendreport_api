"""
쇼핑 검색 API
docs/api guide.md 1절 기준으로 구현

요청 URL (docs 1절):
  GET https://openapi.naver.com/v1/search/shop.json

요청 파라미터 (docs 1절):
  query    String  Y  UTF-8 인코딩 검색어
  display  Integer N  1~100, default 10
  start    Integer N  1~1000, default 1
  sort     String  N  sim / date / asc / dsc  (asc = 가격 오름차순)
  filter   String  N  naverpay
  exclude  String  N  used / rental / cbshop (콜론 구분 중복 설정 가능)

응답 필드 (docs 1절):
  channel.total     전체 검색 결과 개수
  items[].title     상품명 (<b> 태그 포함, 제거 필요)
  items[].link      상품 상세 URL
  items[].image     섬네일 이미지 URL
  items[].lprice    최저가 (정보 없으면 0)
  items[].hprice    최고가 (정보 없거나 비교 데이터 없으면 0)
  items[].mallName  판매 쇼핑몰명 (없으면 '네이버')
  items[].productId 네이버쇼핑 고유 상품 ID
  items[].productType 상품 타입 번호 (docs 1절 타입 매핑 표 참고)
  items[].brand     브랜드 명칭
  items[].maker     제조사 명칭
  items[].category1~4 카테고리 계층

헤더 (docs 0절):
  X-Naver-Client-Id
  X-Naver-Client-Secret
"""

import hashlib
import json
import os
import re
import datetime
import streamlit as st
import pandas as pd
import requests

from config import SHOPPING_ID, SHOPPING_SECRET

CACHE_DIR = "data/cache"
_SEARCH_URL = "https://openapi.naver.com/v1/search/shop.json"


def _headers() -> dict:
    """docs 0절 — X-Naver-Client-Id / X-Naver-Client-Secret"""
    return {
        "X-Naver-Client-Id": SHOPPING_ID,
        "X-Naver-Client-Secret": SHOPPING_SECRET,
    }


def _strip_html(text: str) -> str:
    """docs 1절: title 필드는 <b> 태그로 강조됨 → 제거"""
    return re.sub(r"<[^>]+>", "", text)


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
def search_products(
    keyword: str,
    display: int = 100,
    sort: str = "asc",
) -> pd.DataFrame:
    """
    docs 1절 — 쇼핑 검색 API

    Parameters
    ----------
    keyword : str  검색어
    display : int  한 번에 표시할 결과 수. 허용 범위 1~100 (docs 1절)
    sort    : str  asc = 가격 오름차순 (docs 1절: sim/date/asc/dsc)

    Returns
    -------
    DataFrame: columns = [
        "title", "brand", "lprice", "hprice",
        "mallName", "image", "link", "productType"
    ]
      - title   : HTML 태그 제거 (docs 1절 명시)
      - lprice  : int 변환 (docs 1절: 정보 없으면 0)
      - hprice  : int 변환 (docs 1절: 정보 없거나 비교 데이터 없으면 0)
    """
    params_key = {"func": "search_products", "keyword": keyword, "display": display, "sort": sort}
    cache_file = _cache_path("search_products", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        df = pd.DataFrame(cached)
        df["lprice"] = df["lprice"].astype(int)
        df["hprice"] = df["hprice"].astype(int)
        return df

    params = {"query": keyword, "display": display, "sort": sort}

    try:
        resp = requests.get(_SEARCH_URL, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        rows = []
        for item in items:
            rows.append({
                "title":       _strip_html(item.get("title", "")),
                "brand":       item.get("brand", ""),
                "lprice":      int(item.get("lprice", 0) or 0),
                "hprice":      int(item.get("hprice", 0) or 0),
                "mallName":    item.get("mallName", ""),
                "image":       item.get("image", ""),
                "link":        item.get("link", ""),
                "productType": item.get("productType", ""),
            })
        df = pd.DataFrame(rows, columns=[
            "title", "brand", "lprice", "hprice",
            "mallName", "image", "link", "productType"
        ])
        _save_cache(cache_file, df.to_dict(orient="records"))
        return df
    except Exception as e:
        st.error(f"[search_products] API 호출 실패: {e}")
        return pd.DataFrame(columns=[
            "title", "brand", "lprice", "hprice",
            "mallName", "image", "link", "productType"
        ])


@st.cache_data(ttl=3600)
def search_products_tab3(
    keyword: str,
    max_items: int = 300,
) -> pd.DataFrame:
    """
    docs 1절 — Tab3 전용 쇼핑 검색 (페이지네이션, 전체 필드)

    Parameters
    ----------
    keyword   : str  검색어
    max_items : int  최대 수집 건수 (기본 300, display 100 × 3페이지)

    고정 옵션
    ---------
    sort    = date      (최신순)
    exclude = used:rental:cbshop  (중고·렌탈·해외직구 제외)

    Returns
    -------
    DataFrame: columns = [
        "title", "brand", "lprice", "hprice",
        "mallName", "image", "link",
        "productType", "productId", "maker",
        "category1", "category2", "category3", "category4",
        "display_subcat",
    ]
      - title        : HTML 태그 제거
      - lprice/hprice: int
      - display_subcat: category4 if non-empty else category3
    """
    params_key = {"func": "search_products_tab3", "keyword": keyword, "max_items": max_items}
    cache_file = _cache_path("search_products_tab3", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        df = pd.DataFrame(cached)
        df["lprice"] = df["lprice"].astype(int)
        df["hprice"] = df["hprice"].astype(int)
        return df

    rows = []
    per_page = 100
    pages = min(5, -(-max_items // per_page))  # ceil division

    try:
        for page in range(pages):
            start = page * per_page + 1
            params = {
                "query":   keyword,
                "display": per_page,
                "start":   start,
                "sort":    "date",
                "exclude": "used:rental:cbshop",
            }
            resp = requests.get(_SEARCH_URL, headers=_headers(), params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                break

            for item in items:
                cat3 = item.get("category3", "")
                cat4 = item.get("category4", "")
                display_subcat = cat4 if cat4 else cat3
                rows.append({
                    "title":        _strip_html(item.get("title", "")),
                    "brand":        item.get("brand", ""),
                    "lprice":       int(item.get("lprice", 0) or 0),
                    "hprice":       int(item.get("hprice", 0) or 0),
                    "mallName":     item.get("mallName", ""),
                    "image":        item.get("image", ""),
                    "link":         item.get("link", ""),
                    "productType":  item.get("productType", ""),
                    "productId":    item.get("productId", ""),
                    "maker":        item.get("maker", ""),
                    "category1":    item.get("category1", ""),
                    "category2":    item.get("category2", ""),
                    "category3":    cat3,
                    "category4":    cat4,
                    "display_subcat": display_subcat,
                })
            if len(rows) >= max_items:
                break

    except Exception as e:
        st.warning(f"[search_products_tab3] API 호출 실패: {e}")
        return pd.DataFrame(columns=[
            "title", "brand", "lprice", "hprice", "mallName", "image", "link",
            "productType", "productId", "maker",
            "category1", "category2", "category3", "category4", "display_subcat",
        ])

    rows = rows[:max_items]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    _save_cache(cache_file, df.to_dict(orient="records"))
    return df


@st.cache_data(ttl=3600)
def get_product_count(keyword: str) -> int:
    """
    docs 1절 — channel.total 필드 반환
    응답 channel.total: 전체 검색 결과 개수 (docs 1절)

    Returns
    -------
    int  전체 상품 수. 에러 시 0
    """
    params_key = {"func": "get_product_count", "keyword": keyword}
    cache_file = _cache_path("get_product_count", params_key)
    cached = _load_cache(cache_file)
    if cached is not None:
        return cached.get("total", 0)

    params = {"query": keyword, "display": 1}

    try:
        resp = requests.get(_SEARCH_URL, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        total = int(data.get("total", 0))
        _save_cache(cache_file, {"total": total})
        return total
    except Exception as e:
        st.error(f"[get_product_count] API 호출 실패: {e}")
        return 0
