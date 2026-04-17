"""
공통 차트 빌더 — Plotly Go 기반
모든 함수는 go.Figure 반환
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

COLORS = ["#4A90D9", "#E85D5D", "#50C878", "#FFB347", "#9B59B6", "#1ABC9C"]
FONT   = "Noto Sans KR, sans-serif"

_LAYOUT = dict(
    font_family=FONT,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=10),
)


def line_chart(df: pd.DataFrame, x: str, y: str, title: str,
               color_col: str = None) -> go.Figure:
    """
    단일 또는 멀티라인 차트.
    color_col 지정 시 해당 컬럼 값별로 별개 라인 생성 (범례 on/off 가능).
    """
    fig = go.Figure()
    if color_col and color_col in df.columns:
        for i, group in enumerate(df[color_col].unique()):
            sub = df[df[color_col] == group]
            fig.add_trace(go.Scatter(
                x=sub[x], y=sub[y], name=str(group), mode="lines",
                line=dict(color=COLORS[i % len(COLORS)], width=2),
            ))
    else:
        fig.add_trace(go.Scatter(
            x=df[x], y=df[y], mode="lines",
            line=dict(color=COLORS[0], width=2),
        ))
    fig.update_layout(
        title=dict(text=title, font_size=14),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.2),
        **_LAYOUT,
    )
    return fig


def donut_chart(labels: list, values: list, title: str) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker_colors=COLORS,
        textinfo="label+percent",
        textfont_size=12,
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13),
        showlegend=False,
        **_LAYOUT,
    )
    return fig


def bar_chart_v(labels: list, values: list, title: str) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=COLORS[:len(labels)] if len(labels) <= len(COLORS) else COLORS * (len(labels)//len(COLORS)+1),
        text=[f"{v:.1f}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0", visible=False),
        **_LAYOUT,
    )
    return fig


def bar_chart_h(labels: list, values: list, title: str) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=COLORS[0],
        text=[f"{v:.1f}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(showgrid=False, autorange="reversed"),
        **_LAYOUT,
    )
    return fig


def histogram_price(prices: list, title: str) -> go.Figure:
    """가격 히스토그램. bin 자동, x축 단위 원."""
    fig = go.Figure(go.Histogram(
        x=prices,
        marker_color=COLORS[0],
        opacity=0.8,
        nbinsx=20,
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13),
        xaxis=dict(title="가격(원)", tickformat=",", showgrid=False),
        yaxis=dict(title="상품 수", showgrid=True, gridcolor="#f0f0f0"),
        bargap=0.1,
        **_LAYOUT,
    )
    return fig


def scatter_2x2(df: pd.DataFrame, x_col: str, y_col: str,
                label_col: str, title: str) -> go.Figure:
    """
    수요×공급 갭 매트릭스
    x = 공급(상품수), y = 수요(검색량)
    중앙값 기준 4사분면 배경색:
      좌상(저공급 고수요) 🟢 #E8F5E9  기획기회
      우상(고공급 고수요) 🔴 #FFEBEE  경쟁과열
      좌하(저공급 저수요) 🟡 #FFFDE7  잠재시장
      우하(고공급 저수요) ⚪ #F5F5F5  쇠퇴징후
    """
    if df.empty:
        return go.Figure()

    x_mid = df[x_col].median()
    y_mid = df[y_col].median()
    x_max = df[x_col].max() * 1.2
    y_max = df[y_col].max() * 1.2

    fig = go.Figure()

    # 사분면 배경
    fig.add_hrect(y0=y_mid, y1=y_max, fillcolor="#E8F5E9", opacity=0.4, line_width=0)  # 좌상
    fig.add_hrect(y0=0, y1=y_mid, fillcolor="#FFFDE7", opacity=0.4, line_width=0)      # 좌하
    fig.add_vrect(x0=x_mid, x1=x_max, y0=0.5, y1=1.0,
                  fillcolor="#FFEBEE", opacity=0.4, line_width=0, yref="paper")         # 우상
    fig.add_vrect(x0=x_mid, x1=x_max, y0=0.0, y1=0.5,
                  fillcolor="#F5F5F5", opacity=0.4, line_width=0, yref="paper")         # 우하

    # 중앙값 기준선
    fig.add_hline(y=y_mid, line_dash="dot", line_color="#aaaaaa", line_width=1)
    fig.add_vline(x=x_mid, line_dash="dot", line_color="#aaaaaa", line_width=1)

    # 사분면 레이블
    fig.add_annotation(x=x_mid * 0.5, y=y_max * 0.92, text="🟢 기획기회",
                       showarrow=False, font=dict(size=11, color="#2e7d32"))
    fig.add_annotation(x=x_max * 0.85, y=y_max * 0.92, text="🔴 경쟁과열",
                       showarrow=False, font=dict(size=11, color="#c62828"))
    fig.add_annotation(x=x_mid * 0.5, y=y_mid * 0.1, text="🟡 잠재시장",
                       showarrow=False, font=dict(size=11, color="#f57f17"))
    fig.add_annotation(x=x_max * 0.85, y=y_mid * 0.1, text="⚪ 쇠퇴징후",
                       showarrow=False, font=dict(size=11, color="#757575"))

    # 산점도
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col],
        mode="markers+text",
        text=df[label_col],
        textposition="top center",
        marker=dict(size=12, color=COLORS[0], opacity=0.8),
    ))

    fig.update_layout(
        title=dict(text=title, font_size=14),
        xaxis=dict(title="공급(상품 수)", showgrid=False, range=[0, x_max]),
        yaxis=dict(title="수요(검색 관심도)", showgrid=False, range=[0, y_max]),
        showlegend=False,
        **_LAYOUT,
    )
    return fig


def heatmap(df: pd.DataFrame, x_col: str, y_col: str,
            value_col: str, title: str) -> go.Figure:
    """연령×키워드 히트맵. 고값=진한색."""
    pivot = df.pivot_table(index=y_col, columns=x_col, values=value_col, aggfunc="mean")
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="Blues",
        showscale=True,
        text=[[f"{v:.1f}" for v in row] for row in pivot.values],
        texttemplate="%{text}",
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13),
        xaxis=dict(title=x_col),
        yaxis=dict(title=y_col, autorange="reversed"),
        **_LAYOUT,
    )
    return fig
