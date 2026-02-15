"""
Page 1 — Dashboard: KPI Cards + Interactive Chart
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

# ── Charts ───────────────────────────────────────────────────────────────────
chart_df = filtered.copy()

for col in ["total_usd", "number_of_exporters", "total_invoices"]:
    if col not in chart_df.columns:
        chart_df[col] = 0

chart_df = chart_df[chart_df["total_usd"] > 0].copy()

if "buyer_name" not in chart_df.columns:
    chart_df["buyer_name"] = "Unknown"
if "destination_country" not in chart_df.columns:
    chart_df["destination_country"] = ""

if chart_df.empty:
    st.info("No data to display. Adjust filters or check your data source.")
else:
    # ── Top Buyers Bar Chart ─────────────────────────────────────────────
    st.markdown("##### 📊 Top 30 Buyers by Total USD")
    top30 = chart_df.nlargest(30, "total_usd")

    fig_bar = px.bar(
        top30,
        x="total_usd",
        y="buyer_name",
        color="destination_country",
        orientation="h",
        hover_data={"total_invoices": True, "number_of_exporters": True, "total_usd": ":$,.0f"},
        labels={"total_usd": "Total USD", "buyer_name": "Buyer", "destination_country": "Country"},
    )
    fig_bar.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        height=600,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True, key="top30_bar")

    st.markdown("")

    # ── Scatter: Invoices vs USD (fast 2D) ───────────────────────────────
    st.markdown("##### 🫧 Buyer Landscape — Invoices vs USD")
    st.caption(f"Showing top 500 buyers by Total USD")

    scatter_df = chart_df.nlargest(500, "total_usd").copy()
    max_usd = scatter_df["total_usd"].max()
    scatter_df["bubble_size"] = (scatter_df["total_usd"] / max_usd * 50).clip(lower=5) if max_usd > 0 else 10

    fig_scatter = px.scatter(
        scatter_df,
        x="total_invoices",
        y="total_usd",
        size="bubble_size",
        color="destination_country",
        hover_name="buyer_name",
        hover_data={
            "destination_country": True,
            "total_invoices": True,
            "total_usd": ":$,.0f",
            "number_of_exporters": True,
            "bubble_size": False,
        },
        labels={
            "total_invoices": "Invoices",
            "total_usd": "Total USD",
            "destination_country": "Country",
        },
    )
    fig_scatter.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        height=550,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_scatter, use_container_width=True, key="scatter_chart")

    st.markdown("")

    # ── Country breakdown ────────────────────────────────────────────────
    st.markdown("##### 🌍 USD by Country")
    country_agg = chart_df.groupby("destination_country", as_index=False).agg(
        total_usd=("total_usd", "sum"),
        buyers=("buyer_name", "count"),
    ).nlargest(20, "total_usd")

    fig_pie = px.pie(
        country_agg,
        values="total_usd",
        names="destination_country",
        hover_data={"buyers": True},
    )
    fig_pie.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig_pie, use_container_width=True, key="country_pie")
