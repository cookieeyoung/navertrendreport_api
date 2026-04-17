"""
텍스트 파싱 유틸리티
- 형태소 분석: kiwipiepy (NNG/NNP 명사 추출)
- 워드클라우드: wordcloud + matplotlib
"""
import re
import platform
import matplotlib.pyplot as plt
from wordcloud import WordCloud

try:
    from kiwipiepy import Kiwi
    _kiwi = Kiwi()
    KIWI_OK = True
except Exception:
    _kiwi = None
    KIWI_OK = False

STOPWORDS = {
    "공통": {
        "상품", "판매", "구매", "할인", "무료", "배송", "정품", "신상", "최신",
        "브랜드", "남성", "여성", "남녀", "공용", "국내", "해외", "직구",
        "추천", "인기", "당일", "특가", "세일",
    },
    "패션의류":    {"의류", "옷", "착용", "패션"},
    "패션잡화":    {"잡화", "악세사리"},
    "화장품/미용": {"ml", "g", "oz", "set", "세트", "화장품"},
    "디지털/가전": {"제품", "기기", "전자"},
    "스포츠/레저": {"스포츠", "레저"},
    "생활/건강":   {"생활", "건강"},
    "식품":        {"식품", "음식"},
}


def clean_html(text: str) -> str:
    """HTML 태그 제거 (docs 1절: title 필드 <b> 태그 포함)"""
    return re.sub(r"<[^>]+>", "", text)


def get_font_path() -> str:
    """OS별 한글 폰트 경로"""
    s = platform.system()
    if s == "Darwin":
        return "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    if s == "Windows":
        return "C:/Windows/Fonts/malgun.ttf"
    return "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def extract_keywords(titles: list, category: str = "공통") -> dict:
    """
    상품명 리스트 → {명사: 빈도수}
    - NNG(일반명사) / NNP(고유명사), 2글자 이상, 불용어 제거
    - kiwipiepy 미설치 시 공백 분리로 대체
    """
    stop = STOPWORDS["공통"] | STOPWORDS.get(category, set())
    freq: dict = {}

    for raw in titles:
        text = clean_html(raw)
        if KIWI_OK:
            for token in _kiwi.tokenize(text):
                if token.tag in ("NNG", "NNP") and len(token.form) >= 2:
                    w = token.form
                    if w not in stop:
                        freq[w] = freq.get(w, 0) + 1
        else:
            # fallback: 공백 분리 후 2글자 이상 한글 단어
            for w in re.findall(r"[가-힣]{2,}", text):
                if w not in stop:
                    freq[w] = freq.get(w, 0) + 1
    return freq


def make_wordcloud(freq: dict, font_path: str = None) -> plt.Figure:
    """
    빈도 dict → 워드클라우드 matplotlib Figure 반환
    빈 dict 이면 "데이터 없음" 텍스트 Figure 반환
    """
    if font_path is None:
        font_path = get_font_path()

    fig, ax = plt.subplots(figsize=(6, 3))
    fig.patch.set_alpha(0)

    if not freq:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                fontsize=14, color="#aaaaaa")
        ax.axis("off")
        return fig

    try:
        wc = WordCloud(
            font_path=font_path,
            background_color="white",
            width=600,
            height=300,
            max_words=80,
            colormap="Set2",
        ).generate_from_frequencies(freq)
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
    except Exception:
        # 폰트 오류 시 상위 20개 바차트로 대체
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:20]
        labels, values = zip(*top) if top else ([], [])
        ax.barh(range(len(labels)), values, color="#4A90D9")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.axis("on")

    return fig
