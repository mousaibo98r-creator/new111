"""
Page 1 — Dashboard: KPI Cards + Charts (Streamlit native — guaranteed render)
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

import pandas as pd
import plotly.express as px

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_sidebar_filters,
    render_kpi_cards,
    render_top_nav,
    render_inline_filters,
    auth_gate,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📊 Dashboard</div>', unsafe_allow_html=True)
st.markdown("")

df_all = load_buyers()
opts = get_filter_options(df_all)

# ── Inline filters (visible on mobile) ───────────────────────────────────────
selected = render_inline_filters(opts, df=df_all)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = apply_filters(df_all, selected["countries"], selected["exporters"])
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

chart_df = chart_df[chart_df["total_usd"] > 0].copy().sort_values("total_usd", ascending=False)

if chart_df.empty:
    st.info("No data available. Check Supabase connection and filters.")
    st.stop()

# ═══════════════════════════ ROW 1 ═══════════════════════════════════════════
r1c1, r1c2 = st.columns(2)

# ── Chart 1: Top 20 Buyers ──────────────────────────────────────────────────
with r1c1:
    st.markdown("### 🏆 Top 20 Buyers by USD")
    top20 = chart_df.nlargest(20, "total_usd").copy()
    top20["display_name"] = top20["buyer_name"].str[:25]
    top20 = top20.sort_values("total_usd", ascending=True) # Plotly bar horizontal sorts bottom-up
    
    fig1 = px.bar(
        top20,
        x="total_usd",
        y="display_name",
        orientation="h",
        template="plotly_dark",
        color_discrete_sequence=["#a855f7"]
    )
    fig1.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=450,
        xaxis_title="Total USD",
        yaxis_title=None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})

# ── Chart 2: USD by Country (Top 12) ────────────────────────────────────────
with r1c2:
    st.markdown("### 🌍 USD by Country (Top 20)")
    country_usd = chart_df.groupby("destination_country", as_index=False)["total_usd"].sum()
    country_usd = country_usd.nlargest(20, "total_usd").sort_values("total_usd", ascending=False)
    
    fig2 = px.bar(
        country_usd,
        x="destination_country",
        y="total_usd",
        template="plotly_dark",
        color_discrete_sequence=["#3b82f6"]
    )
    fig2.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=450,
        xaxis_title=None,
        yaxis_title="Total USD",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    # Force sorting on x-axis
    fig2.update_xaxes(categoryorder='total descending')
    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

st.markdown("")

# ═══════════════════════════ ROW 2 ═══════════════════════════════════════════
r2c1, r2c2 = st.columns(2)

# ── Chart 3: Yellow Scatter — Invoices vs USD ────────────────────────────────
with r2c1:
    st.markdown("### 🟡 Invoices vs USD")
    scatter_data = chart_df.nlargest(300, "total_usd")[["total_invoices", "total_usd"]].copy()
    st.scatter_chart(scatter_data, x="total_invoices", y="total_usd", color="#fbbf24")

# ── Chart 4: Buyers per Country ──────────────────────────────────────────────
with r2c2:
    st.markdown("### 📦 Buyers per Country (Top 20)")
    cc = chart_df.groupby("destination_country", as_index=False).agg(
        buyers=("buyer_name", "count"),
    ).nlargest(20, "buyers").sort_values("buyers", ascending=False)
    
    fig3 = px.bar(
        cc,
        x="destination_country",
        y="buyers",
        template="plotly_dark",
        color_discrete_sequence=["#22c55e"]
    )
    fig3.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=450,
        xaxis_title=None,
        yaxis_title="Buyer Count",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig3.update_xaxes(categoryorder='total descending')
    st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})

st.markdown("")

# ═══════════════════════════ ROW 3: Data Overview ════════════════════════════
with st.expander("📋 Data Summary", expanded=False):
    st.markdown(f"**Total records loaded:** {len(filtered):,}")
    st.markdown(f"**Records with USD > 0:** {len(chart_df):,}")
    st.markdown(f"**Countries:** {chart_df['destination_country'].nunique()}")

    if "exporters" in chart_df.columns:
        st.markdown(f"**Columns available:** {', '.join(chart_df.columns[:15].tolist())}")
