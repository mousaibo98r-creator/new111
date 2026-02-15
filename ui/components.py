"""
Shared UI components: auth gate, sidebar brand/nav/filters, detail card, KPI cards.
"""

from __future__ import annotations
import os
import json
import urllib.parse

import streamlit as st
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Authentication gate — call at the TOP of every page
# ──────────────────────────────────────────────────────────────────────────────
def _get_app_password() -> str | None:
    try:
        return st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        return os.environ.get("APP_PASSWORD")


def auth_gate():
    """Block the page unless the user has authenticated.
    Call this AFTER st.set_page_config() in every page file.
    This does NOT call set_page_config — the calling page must do that first."""
    if st.session_state.get("authenticated"):
        return  # already authed

    from ui.style import inject_css
    inject_css()

    st.markdown("---")
    st.markdown(
        '<div style="text-align:center;">'
        '<span style="font-size:2rem;">🔐</span><br>'
        '<span class="sidebar-brand">OBSIDIAN</span><br>'
        '<span class="sidebar-brand-sub">Strategic Intelligence Platform</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    password = st.text_input("Enter password", type="password", key="login_pw")
    if st.button("🔓 Unlock", use_container_width=True):
        expected = _get_app_password()
        if expected and password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar brand
# ──────────────────────────────────────────────────────────────────────────────
def render_sidebar_brand():
    st.sidebar.markdown(
        '<div class="sidebar-brand">⚡ OBSIDIAN</div>'
        '<div class="sidebar-brand-sub">Strategic Intelligence Platform</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ──────────────────────────────────────────────────────────────────────────────
def render_sidebar_nav():
    st.sidebar.markdown('<div class="sidebar-section">Navigation</div>', unsafe_allow_html=True)
    pages = {
        "📊 Dashboard": "pages/1_Dashboard.py",
        "🔴 Matrix": "pages/2_Matrix.py",
        "📁 Archive": "pages/3_Archive.py",
        "⚙️ Settings": "pages/4_Settings.py",
    }
    for label in pages:
        st.sidebar.page_link(pages[label], label=label)


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ──────────────────────────────────────────────────────────────────────────────
def render_sidebar_filters(filter_options: dict) -> dict:
    st.sidebar.markdown('<div class="sidebar-section">🔧 Filters</div>', unsafe_allow_html=True)

    selected = {}
    selected["countries"] = st.sidebar.multiselect(
        "Countries",
        options=filter_options.get("countries", []),
        default=[],
        key="filter_countries",
    )
    selected["exporters"] = st.sidebar.multiselect(
        "Exporters",
        options=filter_options.get("exporters", []),
        default=[],
        key="filter_exporters",
    )
    return selected


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar export + logout
# ──────────────────────────────────────────────────────────────────────────────
def render_sidebar_export(df: pd.DataFrame):
    st.sidebar.markdown('<div class="sidebar-section">📦 Export Data</div>', unsafe_allow_html=True)
    export_cols = [c for c in df.columns if not c.startswith("_")]
    json_str = df[export_cols].to_json(orient="records", force_ascii=False, indent=2)
    st.sidebar.download_button(
        label="📥 Download Updated JSON",
        data=json_str,
        file_name="obsidian_export.json",
        mime="application/json",
        use_container_width=True,
    )


def render_sidebar_logout():
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# KPI cards
# ──────────────────────────────────────────────────────────────────────────────
def render_kpi_cards(df: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-value">{len(df):,}</div>'
            '<div class="kpi-label">Total Buyers</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        total_usd = df["total_usd"].sum() if "total_usd" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-value">${total_usd:,.0f}</div>'
            '<div class="kpi-label">Total USD</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        total_inv = int(df["total_invoices"].sum()) if "total_invoices" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-value">{total_inv:,}</div>'
            '<div class="kpi-label">Total Invoices</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        n_countries = df["destination_country"].nunique() if "destination_country" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-value">{n_countries}</div>'
            '<div class="kpi-label">Countries</div></div>',
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Detail card (right panel)
# ──────────────────────────────────────────────────────────────────────────────
def _safe(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val)


def _list_val(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            if "," in val:
                return [v.strip() for v in val.split(",") if v.strip()]
            return [val] if val else []
    return []


def render_buyer_detail(row: pd.Series | None):
    """Render the Entity Profile panel on the right side."""
    if row is None:
        st.markdown(
            '<div class="detail-default">Select a buyer to view details.</div>',
            unsafe_allow_html=True,
        )
        return

    buyer_name = _safe(row.get("buyer_name", ""))
    english = _safe(row.get("company_name_english", ""))
    country = _safe(row.get("destination_country", ""))
    country_code = _safe(row.get("country_code", ""))
    total_usd = row.get("total_usd", 0)

    # Title
    st.markdown(
        '<div class="detail-panel-title">📂 Entity Profile</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="detail-buyer-name">{buyer_name}</div>', unsafe_allow_html=True)
    if english:
        st.markdown(f'<div class="detail-english">ENGLISH: {english}</div>', unsafe_allow_html=True)

    # Location & Volume
    loc_text = f"{country}"
    if country_code:
        loc_text += f" ({country_code})"

    st.markdown(
        f'<div class="loc-vol-row">'
        f'<div class="loc-vol-item"><div class="loc-vol-label">LOCATION</div>'
        f'<div class="loc-vol-value">{loc_text}</div></div>'
        f'<div class="loc-vol-item"><div class="loc-vol-label">VOLUME</div>'
        f'<div class="loc-vol-value">${total_usd:,.2f}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Emails
    emails = _list_val(row.get("email", row.get("emails", [])))
    if emails:
        st.markdown('<div class="detail-label">EMAILS</div>', unsafe_allow_html=True)
        for e in emails[:5]:
            st.markdown(f'<a class="detail-link" href="mailto:{e}">{e}</a>', unsafe_allow_html=True)

    # Websites
    websites = _list_val(row.get("website", row.get("websites", [])))
    if websites:
        st.markdown('<div class="detail-label">WEBSITES</div>', unsafe_allow_html=True)
        for w in websites[:5]:
            url = w if w.startswith("http") else f"https://{w}"
            st.markdown(f'<a class="detail-link" href="{url}" target="_blank">{w}</a>', unsafe_allow_html=True)

    # Phones
    phones = _list_val(row.get("phone", row.get("phones", [])))
    if phones:
        st.markdown('<div class="detail-label">PHONES (WhatsApp)</div>', unsafe_allow_html=True)
        for p in phones[:5]:
            st.markdown(f'<a class="detail-phone-link" href="https://wa.me/{p}" target="_blank">{p}</a>', unsafe_allow_html=True)

    # Addresses
    addresses = _list_val(row.get("address", row.get("addresses", [])))
    if addresses:
        st.markdown('<div class="detail-label">ADDRESSES</div>', unsafe_allow_html=True)
        for a in addresses[:3]:
            st.markdown(f'<div class="detail-value">• {a}</div>', unsafe_allow_html=True)

    # Exporters
    exporters = row.get("exporters", {})
    if isinstance(exporters, str):
        try:
            exporters = json.loads(exporters)
        except Exception:
            exporters = {}
    if isinstance(exporters, dict) and exporters:
        st.markdown('<div class="detail-label">EXPORTERS</div>', unsafe_allow_html=True)
        for name, count in list(exporters.items())[:8]:
            st.markdown(
                f'<div class="detail-value">• {name} <span style="color:#8b949e;">({count})</span></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Actions ──
    st.markdown('<div class="actions-title">⚡ Actions</div>', unsafe_allow_html=True)

    # Google Search
    gq = urllib.parse.quote_plus(f"{buyer_name} {country} contact")
    st.link_button("🟢 Google Search", f"https://www.google.com/search?q={gq}", use_container_width=True)

    return buyer_name, country  # caller can use for Scavenge
