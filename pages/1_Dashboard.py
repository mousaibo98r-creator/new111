"""
Page 1 — Dashboard: KPI Cards + Interactive Charts
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Dashboard", page_icon="📊", layout="wide")

import pandas as pd
import plotly.express as px

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

# ── Prepare data ─────────────────────────────────────────────────────────────
chart_df = filtered.copy()

for col in ["total_usd", "number_of_exporters", "total_invoices"]:
    if col not in chart_df.columns:
        chart_df[col] = 0

chart_df["total_usd"] = pd.to_numeric(chart_df["total_usd"], errors="coerce").fillna(0)
chart_df["total_invoices"] = pd.to_numeric(chart_df["total_invoices"], errors="coerce").fillna(0)

chart_df = chart_df[chart_df["total_usd"] > 0].copy()

if "buyer_name" not in chart_df.columns:
    chart_df["buyer_name"] = "Unknown"
if "destination_country" not in chart_df.columns:
    chart_df["destination_country"] = ""

# ── Dark theme template ─────────────────────────────────────────────────────
DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(14,17,23,0)",
    plot_bgcolor="rgba(14,17,23,0.5)",
    font=dict(color="#c9d1d9", family="Inter"),
    margin=dict(l=10, r=10, t=40, b=40),
)

if chart_df.empty:
    st.info("No data to display. Adjust filters or check your data source.")
else:
    # ── Row 1: Top 20 Buyers Bar + Country Donut ───────────────────────────
    col_bar, col_pie = st.columns([3, 2])

    with col_bar:
        top20 = chart_df.nlargest(20, "total_usd").copy()
        top20["short_name"] = top20["buyer_name"].str[:28]

        fig_bar = px.bar(
            top20,
            y="short_name",
            x="total_usd",
            orientation="h",
            title="🏆 Top 20 Buyers by Total USD",
            color="total_usd",
            color_continuous_scale=["#6366f1", "#a855f7", "#ec4899"],
            text=top20["total_usd"].apply(lambda v: f"${v:,.0f}"),
        )
        fig_bar.update_layout(
            **DARK_LAYOUT,
            height=520,
            yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
            xaxis=dict(showgrid=True, gridcolor="rgba(33,38,45,0.8)"),
            coloraxis_showscale=False,
            showlegend=False,
        )
        fig_bar.update_traces(textposition="outside", textfont_size=9)
        st.plotly_chart(fig_bar, use_container_width=True, key="bar1")

    with col_pie:
        country_usd = chart_df.groupby("destination_country", as_index=False)["total_usd"].sum()
        country_usd = country_usd.nlargest(12, "total_usd")

        fig_pie = px.pie(
            country_usd,
            names="destination_country",
            values="total_usd",
            title="🌍 USD by Country",
            hole=0.45,
            color_discrete_sequence=[
                "#a855f7", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444",
                "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316",
                "#6366f1", "#84cc16",
            ],
        )
        fig_pie.update_layout(**DARK_LAYOUT, height=520, showlegend=True,
                              legend=dict(font=dict(size=10)))
        fig_pie.update_traces(textinfo="label+percent", textfont_size=10)
        st.plotly_chart(fig_pie, use_container_width=True, key="pie1")

    st.markdown("")

    # ── Row 2: Yellow Bubble Scatter + Country Bar ───────────────────────────
    col_scatter, col_cbar = st.columns([3, 2])

    with col_scatter:
        scatter_df = chart_df.nlargest(200, "total_usd").copy()

        fig_scatter = px.scatter(
            scatter_df,
            x="total_invoices",
            y="total_usd",
            size="total_usd",
            size_max=45,
            hover_name="buyer_name",
            title="🫧 Invoices vs USD (Yellow Bubbles)",
            hover_data={"destination_country": True, "total_usd": ":$,.0f"},
        )
        # Make all bubbles yellow
        fig_scatter.update_traces(
            marker=dict(
                color="#fbbf24",
                opacity=0.75,
                line=dict(width=1, color="#f59e0b"),
            )
        )
        fig_scatter.update_layout(
            **DARK_LAYOUT,
            height=480,
            xaxis=dict(title="Total Invoices", gridcolor="rgba(33,38,45,0.8)"),
            yaxis=dict(title="Total USD ($)", gridcolor="rgba(33,38,45,0.8)"),
        )
        st.plotly_chart(fig_scatter, use_container_width=True, key="scatter1")

    with col_cbar:
        country_count = chart_df.groupby("destination_country", as_index=False).agg(
            buyers=("buyer_name", "count"),
        ).nlargest(15, "buyers")

        fig_cbar = px.bar(
            country_count,
            x="destination_country",
            y="buyers",
            title="📦 Top Countries by Buyer Count",
            color="buyers",
            color_continuous_scale=["#22c55e", "#06b6d4", "#3b82f6"],
            text="buyers",
        )
        fig_cbar.update_layout(
            **DARK_LAYOUT,
            height=480,
            xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
            yaxis=dict(gridcolor="rgba(33,38,45,0.8)"),
            coloraxis_showscale=False,
        )
        fig_cbar.update_traces(textposition="outside", textfont_size=10)
        st.plotly_chart(fig_cbar, use_container_width=True, key="cbar1")
