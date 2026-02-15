"""
Page 1 — Dashboard: KPI Cards + Interactive Charts
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Dashboard", page_icon="📊", layout="wide")

import pandas as pd
import plotly.express as px
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

# ── Prepare data ─────────────────────────────────────────────────────────────
chart_df = filtered.copy()

for col in ["total_usd", "number_of_exporters", "total_invoices"]:
    if col not in chart_df.columns:
        chart_df[col] = 0

chart_df["total_usd"] = pd.to_numeric(chart_df["total_usd"], errors="coerce").fillna(0)
chart_df["total_invoices"] = pd.to_numeric(chart_df["total_invoices"], errors="coerce").fillna(0)
chart_df["number_of_exporters"] = pd.to_numeric(chart_df["number_of_exporters"], errors="coerce").fillna(0)

chart_df = chart_df[chart_df["total_usd"] > 0].copy()

if "buyer_name" not in chart_df.columns:
    chart_df["buyer_name"] = "Unknown"
if "destination_country" not in chart_df.columns:
    chart_df["destination_country"] = ""

# Color palette for charts
NEON_COLORS = [
    "#a855f7", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444",
    "#06b6d4", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316",
    "#6366f1", "#84cc16", "#e879f9", "#0ea5e9", "#fbbf24",
]

if chart_df.empty:
    st.info("No data to display. Adjust filters or check your data source.")
else:
    # ── Row 1: Top Buyers Bar + Country Pie ──────────────────────────────
    col_bar, col_pie = st.columns([3, 2])

    with col_bar:
        st.markdown("##### 📊 Top 20 Buyers by Total USD")
        top20 = chart_df.nlargest(20, "total_usd").copy()
        top20["short_name"] = top20["buyer_name"].str[:30]

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            y=top20["short_name"],
            x=top20["total_usd"],
            orientation="h",
            marker=dict(
                color=top20["total_usd"],
                colorscale=[[0, "#3b82f6"], [0.5, "#a855f7"], [1, "#ec4899"]],
                line=dict(width=0),
            ),
            text=top20["total_usd"].apply(lambda v: f"${v:,.0f}"),
            textposition="auto",
            textfont=dict(color="#e6edf3", size=10),
            hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
        ))
        fig_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=500,
            yaxis=dict(autorange="reversed", tickfont=dict(size=10, color="#8b949e")),
            xaxis=dict(showgrid=True, gridcolor="#21262d", tickfont=dict(color="#8b949e")),
            margin=dict(l=0, r=20, t=10, b=20),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="top20_bar")

    with col_pie:
        st.markdown("##### 🌍 USD by Country")
        country_agg = chart_df.groupby("destination_country", as_index=False).agg(
            total_usd=("total_usd", "sum"),
            buyers=("buyer_name", "count"),
        ).nlargest(15, "total_usd")

        fig_pie = go.Figure()
        fig_pie.add_trace(go.Pie(
            labels=country_agg["destination_country"],
            values=country_agg["total_usd"],
            hole=0.45,
            marker=dict(colors=NEON_COLORS[:len(country_agg)]),
            textinfo="label+percent",
            textfont=dict(size=10, color="#e6edf3"),
            hovertemplate="<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>",
        ))
        fig_pie.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            height=500,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True, key="country_pie")

    st.markdown("")

    # ── Row 2: Scatter + Invoices Treemap ────────────────────────────────
    col_scatter, col_tree = st.columns([3, 2])

    with col_scatter:
        st.markdown("##### 🫧 Buyer Landscape — Invoices vs USD")
        scatter_df = chart_df.nlargest(300, "total_usd").copy()
        max_usd = scatter_df["total_usd"].max()
        scatter_df["bubble_size"] = (scatter_df["total_usd"] / max_usd * 40).clip(lower=4) if max_usd > 0 else 8

        fig_scatter = go.Figure()
        # Group by country for coloring
        countries = scatter_df["destination_country"].unique()
        for i, country in enumerate(countries):
            cdf = scatter_df[scatter_df["destination_country"] == country]
            fig_scatter.add_trace(go.Scatter(
                x=cdf["total_invoices"],
                y=cdf["total_usd"],
                mode="markers",
                name=country[:20],
                marker=dict(
                    size=cdf["bubble_size"],
                    color=NEON_COLORS[i % len(NEON_COLORS)],
                    opacity=0.7,
                    line=dict(width=1, color="#21262d"),
                ),
                text=cdf["buyer_name"],
                hovertemplate="<b>%{text}</b><br>Invoices: %{x}<br>USD: $%{y:,.0f}<extra>%{fullData.name}</extra>",
            ))
        fig_scatter.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=450,
            xaxis=dict(title="Invoices", gridcolor="#21262d", tickfont=dict(color="#8b949e")),
            yaxis=dict(title="Total USD", gridcolor="#21262d", tickfont=dict(color="#8b949e")),
            margin=dict(l=0, r=0, t=10, b=40),
            showlegend=False,
        )
        st.plotly_chart(fig_scatter, use_container_width=True, key="scatter_chart")

    with col_tree:
        st.markdown("##### 📦 Top Countries by Buyer Count")
        country_buyers = chart_df.groupby("destination_country", as_index=False).agg(
            count=("buyer_name", "count"),
            usd=("total_usd", "sum"),
        ).nlargest(15, "count")

        fig_tree = go.Figure()
        fig_tree.add_trace(go.Bar(
            x=country_buyers["destination_country"],
            y=country_buyers["count"],
            marker=dict(
                color=NEON_COLORS[:len(country_buyers)],
                line=dict(width=0),
            ),
            text=country_buyers["count"],
            textposition="outside",
            textfont=dict(color="#e6edf3", size=11),
            hovertemplate="<b>%{x}</b><br>Buyers: %{y}<extra></extra>",
        ))
        fig_tree.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=450,
            xaxis=dict(tickangle=-45, tickfont=dict(size=9, color="#8b949e")),
            yaxis=dict(showgrid=True, gridcolor="#21262d", tickfont=dict(color="#8b949e")),
            margin=dict(l=0, r=0, t=10, b=80),
            showlegend=False,
        )
        st.plotly_chart(fig_tree, use_container_width=True, key="country_bars")
