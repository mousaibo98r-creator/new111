"""
Page 1 — Dashboard: 3D Bubble Scatter + KPI Cards
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
    render_sidebar_export,
    render_kpi_cards,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters

inject_css()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

df_all = load_buyers()
opts = get_filter_options(df_all)
selected = render_sidebar_filters(opts)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = apply_filters(df_all, selected["countries"], selected["exporters"])

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📊 Dashboard</div>', unsafe_allow_html=True)
st.markdown("")

# ── KPI Cards ────────────────────────────────────────────────────────────────
render_kpi_cards(filtered)
st.markdown("")

# ── 3D Bubble Scatter ────────────────────────────────────────────────────────
st.markdown("##### 🫧 Buyer Landscape — 3D Bubble Chart")

chart_df = filtered.copy()

# Ensure required columns exist and have valid data
for col in ["total_usd", "number_of_exporters", "total_invoices"]:
    if col not in chart_df.columns:
        chart_df[col] = 0

# Filter out rows with zero USD (not useful for the chart)
chart_df = chart_df[chart_df["total_usd"] > 0].copy()

if chart_df.empty:
    st.info("No data to display. Adjust filters or check your data source.")
else:
    # Bubble size — normalise for visual clarity
    max_usd = chart_df["total_usd"].max()
    if max_usd > 0:
        chart_df["bubble_size"] = (chart_df["total_usd"] / max_usd * 50).clip(lower=5)
    else:
        chart_df["bubble_size"] = 10

    fig = px.scatter_3d(
        chart_df,
        x="number_of_exporters",
        y="total_usd",
        z="total_invoices",
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
            "number_of_exporters": "Number of Exporters",
            "total_usd": "Total USD",
            "total_invoices": "Invoices",
            "destination_country": "Country",
        },
        title="",
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        height=650,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        scene=dict(
            xaxis=dict(backgroundcolor="#0e1117", gridcolor="#21262d", title="Exporters"),
            yaxis=dict(backgroundcolor="#0e1117", gridcolor="#21262d", title="Total USD"),
            zaxis=dict(backgroundcolor="#0e1117", gridcolor="#21262d", title="Invoices"),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, key="dashboard_3d_chart")
