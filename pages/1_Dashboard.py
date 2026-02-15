"""
Page 1 — Dashboard: KPI Cards + Charts (Supabase only)
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Dashboard", page_icon="📊", layout="wide")

import pandas as pd
import plotly.graph_objects as go

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_sidebar_filters,
    render_kpi_cards,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters

inject_css()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

df_all = load_buyers()
opts = get_filter_options(df_all)
selected = render_sidebar_filters(opts, df=df_all)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = apply_filters(df_all, selected["countries"], selected["exporters"])

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📊 Dashboard</div>', unsafe_allow_html=True)
st.markdown("")

# ── KPI Cards ────────────────────────────────────────────────────────────────
render_kpi_cards(filtered)
st.markdown("")

# ── Prepare ──────────────────────────────────────────────────────────────────
chart_df = filtered.copy()
for col in ["total_usd", "total_invoices"]:
    if col not in chart_df.columns:
        chart_df[col] = 0
    chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce").fillna(0)

if "buyer_name" not in chart_df.columns:
    chart_df["buyer_name"] = "Unknown"
if "destination_country" not in chart_df.columns:
    chart_df["destination_country"] = ""

chart_df = chart_df[chart_df["total_usd"] > 0].copy()

# ── Shared layout ────────────────────────────────────────────────────────────
LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(22,27,34,0.6)",
    font=dict(color="#c9d1d9", family="Inter, sans-serif", size=12),
    margin=dict(l=20, r=20, t=50, b=40),
)

NEON = ["#a855f7", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444",
        "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316",
        "#6366f1", "#84cc16"]

if chart_df.empty:
    st.info("No data available. Check your Supabase connection and filters.")
    st.stop()

# ═══════════════════════════ ROW 1 ═══════════════════════════════════════════
r1c1, r1c2 = st.columns(2)

# ── Chart 1: Top 20 Buyers ──────────────────────────────────────────────────
with r1c1:
    top = chart_df.nlargest(20, "total_usd").copy()
    top = top.sort_values("total_usd", ascending=True)  # reversed for horiz bar
    labels = top["buyer_name"].str[:25].tolist()
    values = top["total_usd"].tolist()

    colors = []
    for i, v in enumerate(values):
        t = i / max(len(values) - 1, 1)
        r = int(99 + t * (236 - 99))
        g = int(102 + t * (72 - 102))
        b = int(241 + t * (153 - 241))
        colors.append(f"rgb({r},{g},{b})")

    fig1 = go.Figure(go.Bar(
        y=labels,
        x=values,
        orientation="h",
        marker_color=colors,
        text=[f"${v:,.0f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color="#c9d1d9"),
    ))
    fig1.update_layout(
        **LAYOUT,
        title=dict(text="🏆 Top 20 Buyers by USD", font=dict(size=15)),
        height=500,
        xaxis=dict(showgrid=True, gridcolor="rgba(48,54,61,0.6)", zeroline=False),
        yaxis=dict(tickfont=dict(size=9)),
    )
    st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Country Donut ──────────────────────────────────────────────────
with r1c2:
    country_usd = chart_df.groupby("destination_country", as_index=False)["total_usd"].sum()
    country_usd = country_usd.nlargest(12, "total_usd")

    fig2 = go.Figure(go.Pie(
        labels=country_usd["destination_country"],
        values=country_usd["total_usd"],
        hole=0.45,
        marker=dict(colors=NEON[:len(country_usd)]),
        textinfo="label+percent",
        textfont=dict(size=10),
        hovertemplate="%{label}<br>$%{value:,.0f}<extra></extra>",
    ))
    fig2.update_layout(
        **LAYOUT,
        title=dict(text="🌍 USD by Country", font=dict(size=15)),
        height=500,
        showlegend=True,
        legend=dict(font=dict(size=9)),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("")

# ═══════════════════════════ ROW 2 ═══════════════════════════════════════════
r2c1, r2c2 = st.columns(2)

# ── Chart 3: Yellow Bubbles (Invoices vs USD) ────────────────────────────────
with r2c1:
    scatter_df = chart_df.nlargest(200, "total_usd").copy()

    fig3 = go.Figure(go.Scatter(
        x=scatter_df["total_invoices"],
        y=scatter_df["total_usd"],
        mode="markers",
        marker=dict(
            size=scatter_df["total_usd"].apply(lambda v: max(5, min(40, v / scatter_df["total_usd"].max() * 40))),
            color="#fbbf24",          # ← YELLOW
            opacity=0.7,
            line=dict(width=1, color="#f59e0b"),
        ),
        text=scatter_df["buyer_name"],
        hovertemplate="<b>%{text}</b><br>Invoices: %{x}<br>USD: $%{y:,.0f}<extra></extra>",
    ))
    fig3.update_layout(
        **LAYOUT,
        title=dict(text="🟡 Invoices vs USD", font=dict(size=15)),
        height=480,
        xaxis=dict(title="Total Invoices", gridcolor="rgba(48,54,61,0.6)", zeroline=False),
        yaxis=dict(title="Total USD ($)", gridcolor="rgba(48,54,61,0.6)", zeroline=False),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ── Chart 4: Top Countries by Buyer Count ────────────────────────────────────
with r2c2:
    cc = chart_df.groupby("destination_country", as_index=False).agg(
        buyers=("buyer_name", "count"),
    ).nlargest(15, "buyers").sort_values("buyers", ascending=False)

    bar_colors = []
    for i in range(len(cc)):
        t = i / max(len(cc) - 1, 1)
        r = int(34 + t * (99 - 34))
        g = int(197 + t * (102 - 197))
        b = int(94 + t * (241 - 94))
        bar_colors.append(f"rgb({r},{g},{b})")

    fig4 = go.Figure(go.Bar(
        x=cc["destination_country"],
        y=cc["buyers"],
        marker_color=bar_colors,
        text=cc["buyers"],
        textposition="outside",
        textfont=dict(size=10, color="#c9d1d9"),
    ))
    fig4.update_layout(
        **LAYOUT,
        title=dict(text="📦 Top Countries by Buyer Count", font=dict(size=15)),
        height=480,
        xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(gridcolor="rgba(48,54,61,0.6)", zeroline=False),
    )
    st.plotly_chart(fig4, use_container_width=True)
