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
import time as _time

def _get_secret(key: str) -> str | None:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key)


def auth_gate():
    """Block the page unless the user has authenticated.
    Call this AFTER st.set_page_config() in every page file.
    This does NOT call set_page_config — the calling page must do that first."""

    auth_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".auth_session.json")

    # If not authenticated in session, try to load from persistent token file
    if not st.session_state.get("authenticated"):
        if os.path.exists(auth_file):
            try:
                with open(auth_file, "r") as f:
                    data = json.load(f)
                    # If within 24 hours
                    if _time.time() - data.get("auth_ts", 0) <= 86400:
                        st.session_state["authenticated"] = True
                    else:
                        # Expired, clean up
                        os.remove(auth_file)
            except Exception:
                pass

    # Check if already authenticated
    if st.session_state.get("authenticated"):
        return  # still valid

    from ui.style import inject_css
    inject_css()

    # ── Access Protocol Login Screen ──
    st.markdown('<div class="login-wrapper"><div class="login-card">', unsafe_allow_html=True)

    # Header — icon, title, subtitle
    st.markdown(
        '<div class="login-header">'
        '<div class="login-icon">⚡</div>'
        '<div class="login-title">Access Protocol</div>'
        '<div class="login-subtitle">OBSIDIAN Intelligence Platform</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Status indicator
    st.markdown(
        '<div class="login-status">'
        '<div class="login-status-dot"></div>'
        '<div class="login-status-text">System Online — Awaiting Authentication</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Divider
    st.markdown('<div class="login-divider"></div>', unsafe_allow_html=True)

    # Username field
    st.markdown('<div class="login-field-label">Operator ID</div>', unsafe_allow_html=True)
    username = st.text_input(
        "Username", label_visibility="collapsed", key="login_username",
        placeholder="Enter your operator ID…",
    )

    # Password field
    st.markdown('<div class="login-field-label">Access Key</div>', unsafe_allow_html=True)
    password = st.text_input(
        "Password", type="password", label_visibility="collapsed", key="login_password",
        placeholder="Enter your access key…",
    )

    # Remember me checkbox
    remember = st.checkbox("Remember session for 24 hours", value=True, key="login_remember")

    # Initialize System button
    st.markdown('<div class="login-btn-row">', unsafe_allow_html=True)
    if st.button("⚡ Initialize System", key="login_submit", use_container_width=True):
        expected_pw = _get_secret("APP_PASSWORD")
        expected_user = _get_secret("APP_USERNAME")

        # Validate credentials
        pw_ok = (expected_pw and password == expected_pw)
        user_ok = (not expected_user) or (username == expected_user)

        if pw_ok and user_ok:
            st.session_state["authenticated"] = True
            
            # Persistent remember if checked
            auth_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".auth_session.json")
            if remember:
                try:
                    with open(auth_file, "w") as f:
                        json.dump({"auth_ts": _time.time()}, f)
                except Exception:
                    pass
            else:
                if os.path.exists(auth_file):
                    try:
                        os.remove(auth_file)
                    except Exception:
                        pass
            
            st.rerun()
        else:
            st.error("⛔ Access denied — invalid credentials.")
    st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div class="login-footer">'
        '<div class="login-footer-text">Encrypted Connection Active</div>'
        '<div class="login-version">OBSIDIAN v2.0</div>'
        '</div>',
        unsafe_allow_html=True,
    )


    st.markdown('</div></div>', unsafe_allow_html=True)
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
        "📁 File Manager": "pages/3_File_Manager.py",
        "⚙️ Settings": "pages/4_Settings.py",
    }
    for label in pages:
        st.sidebar.page_link(pages[label], label=label)


# ──────────────────────────────────────────────────────────────────────────────
# Top navigation bar — always visible (even when sidebar is collapsed)
# ──────────────────────────────────────────────────────────────────────────────
def render_top_nav():
    """Horizontal navigation bar at the top of the page."""
    pages = {
        "📊 Dashboard": "pages/1_Dashboard.py",
        "🔴 Matrix": "pages/2_Matrix.py",
        "📁 Files": "pages/3_File_Manager.py",
        "⚙️ Settings": "pages/4_Settings.py",
    }
    cols = st.columns(len(pages))
    for col, (label, path) in zip(cols, pages.items()):
        with col:
            st.page_link(path, label=label, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# Inline filters — rendered in the main content area (visible on mobile)
# ──────────────────────────────────────────────────────────────────────────────
def render_inline_filters(filter_options: dict, df: pd.DataFrame = None) -> dict:
    """Render Country and Exporter filters in the main page area."""
    with st.expander("🔧 Filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            countries = st.multiselect(
                "Countries",
                options=filter_options.get("countries", []),
                default=[],
                key="inline_countries",
            )
        # Cascading: if countries selected, filter exporters
        if countries and df is not None:
            country_df = df[df["destination_country"].isin(countries)]
            exporter_opts = _extract_exporters(country_df)
        else:
            exporter_opts = filter_options.get("exporters", [])

        with c2:
            exporters = st.multiselect(
                "Exporters",
                options=exporter_opts,
                default=[],
                key="inline_exporters",
            )
    return {"countries": countries, "exporters": exporters}


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ──────────────────────────────────────────────────────────────────────────────
def render_sidebar_filters(filter_options: dict, df: pd.DataFrame = None) -> dict:
    st.sidebar.markdown('<div class="sidebar-section">🔧 Filters</div>', unsafe_allow_html=True)

    selected = {}
    selected["countries"] = st.sidebar.multiselect(
        "Countries",
        options=filter_options.get("countries", []),
        default=[],
        key="filter_countries",
    )

    # Cascading: if countries are selected, only show exporters from those countries
    if selected["countries"] and df is not None:
        country_df = df[df["destination_country"].isin(selected["countries"])]
        exporter_opts = _extract_exporters(country_df)
    else:
        exporter_opts = filter_options.get("exporters", [])

    selected["exporters"] = st.sidebar.multiselect(
        "Exporters",
        options=exporter_opts,
        default=[],
        key="filter_exporters",
    )
    return selected


def _extract_exporters(df: pd.DataFrame) -> list:
    """Extract unique exporter names from the dataframe."""
    import json as _json
    all_exp = set()
    if "exporters" not in df.columns:
        return []
    for val in df["exporters"]:
        if isinstance(val, dict):
            all_exp.update(val.keys())
        elif isinstance(val, str):
            try:
                all_exp.update(_json.loads(val).keys())
            except Exception:
                pass
    return sorted(all_exp)



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
        
        # Clear persistent auth token if exists
        auth_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".auth_session.json")
        if os.path.exists(auth_file):
            try:
                os.remove(auth_file)
            except Exception:
                pass
                
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# KPI cards
# ──────────────────────────────────────────────────────────────────────────────
def render_kpi_cards(df: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kpi-card kpi-card-purple"><div class="kpi-value">{len(df):,}</div>'
            '<div class="kpi-label">Total Buyers</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        total_usd = df["total_usd"].sum() if "total_usd" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card kpi-card-green"><div class="kpi-value">${total_usd:,.0f}</div>'
            '<div class="kpi-label">Total USD</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        total_inv = int(df["total_invoices"].sum()) if "total_invoices" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card kpi-card-blue"><div class="kpi-value">{total_inv:,}</div>'
            '<div class="kpi-label">Total Invoices</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        n_countries = df["destination_country"].nunique() if "destination_country" in df.columns else 0
        st.markdown(
            f'<div class="kpi-card kpi-card-amber"><div class="kpi-value">{n_countries}</div>'
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
