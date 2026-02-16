"""
Page 1 — Dashboard: KPI Cards + Charts (Streamlit native — guaranteed render)
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

import pandas as pd

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_sidebar_filters,
    render_kpi_cards,
    render_top_nav,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters

inject_css()
render_top_nav()

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

chart_df = chart_df[chart_df["total_usd"] > 0].copy().sort_values("total_usd", ascending=False)

if chart_df.empty:
    st.info("No data available. Check Supabase connection and filters.")
    st.stop()

# ═══════════════════════════ ROW 1 ═══════════════════════════════════════════
r1c1, r1c2 = st.columns(2)

# ── Chart 1: Top 20 Buyers ──────────────────────────────────────────────────
with r1c1:
    st.markdown("### 🏆 Top 20 Buyers by USD")
    top20 = chart_df.nlargest(20, "total_usd")[["buyer_name", "total_usd"]].copy()
    top20["buyer_name"] = top20["buyer_name"].str[:25]
    top20 = top20.set_index("buyer_name").sort_values("total_usd", ascending=True)
    st.bar_chart(top20, horizontal=True, color="#a855f7")

# ── Chart 2: USD by Country (Top 12) ────────────────────────────────────────
with r1c2:
    st.markdown("### 🌍 USD by Country")
    country_usd = chart_df.groupby("destination_country", as_index=False)["total_usd"].sum()
    country_usd = country_usd.nlargest(12, "total_usd")
    country_usd = country_usd.set_index("destination_country")
    st.bar_chart(country_usd, color="#3b82f6")

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
    st.markdown("### 📦 Buyers per Country")
    cc = chart_df.groupby("destination_country", as_index=False).agg(
        buyers=("buyer_name", "count"),
    ).nlargest(15, "buyers").sort_values("buyers", ascending=False)
    cc = cc.set_index("destination_country")
    st.bar_chart(cc, color="#22c55e")

st.markdown("")

# ═══════════════════════════ ROW 3: Data Overview ════════════════════════════
with st.expander("📋 Data Summary", expanded=False):
    st.markdown(f"**Total records loaded:** {len(filtered):,}")
    st.markdown(f"**Records with USD > 0:** {len(chart_df):,}")
    st.markdown(f"**Countries:** {chart_df['destination_country'].nunique()}")

    if "exporters" in chart_df.columns:
        st.markdown(f"**Columns available:** {', '.join(chart_df.columns[:15].tolist())}")
