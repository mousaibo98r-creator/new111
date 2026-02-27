"""
Page 5 — Settings: Login/Logout, Connection Status, Sync JSON to Supabase
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Settings", page_icon="⚙️", layout="wide", initial_sidebar_state="collapsed")

from ui.style import inject_css
from ui.components import render_sidebar_brand, render_sidebar_nav, render_top_nav, auth_gate

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Password Gate ─────────────────────────────────────────────────────────────
def _get_app_password():
    try:
        pw = st.secrets.get("APP_PASSWORD")
        if pw:
            return pw
    except (FileNotFoundError, KeyError):
        pass
    return os.environ.get("APP_PASSWORD", "")

_app_pw = _get_app_password()

if _app_pw and not st.session_state.get("settings_unlocked"):
    st.markdown('<div class="page-title">⚙️ Settings</div>', unsafe_allow_html=True)
    st.markdown("")
    st.markdown("### 🔒 This page is password-protected")
    entered = st.text_input("Enter password", type="password", key="settings_pw_input")
    if st.button("Unlock", key="settings_unlock_btn"):
        if entered == _app_pw:
            st.session_state["settings_unlocked"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect password.")
    st.stop()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">⚙️ Settings</div>', unsafe_allow_html=True)
st.markdown("")

# ── Authentication Section ───────────────────────────────────────────────────
st.markdown("### 🔐 Authentication")

col_auth, col_spacer = st.columns([2, 3])
with col_auth:
    if st.session_state.get("authenticated"):
        st.markdown('<span class="status-ok">✅ System Authenticated & Online</span>', unsafe_allow_html=True)
        if st.button("🚪 Log Out", key="settings_logout"):
            st.session_state["authenticated"] = False
            from ui.components import cookie_manager
            cookie_manager.delete("auth_token")
            st.rerun()
    else:
        st.markdown('<span class="status-err">🔒 Not authenticated</span>', unsafe_allow_html=True)

st.markdown("---")

# ── Connection Status ────────────────────────────────────────────────────────
st.markdown("### 📡 Connection Status")

from services.supabase_client import check_connection

status = check_connection()

col_s1, col_s2, col_s3 = st.columns(3)

with col_s1:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-value" style="font-size:1.2rem;">'
        f'{"<span class=status-ok>✅ Reachable</span>" if status["reachable"] else "<span class=status-err>❌ Unreachable</span>"}'
        f'</div><div class="kpi-label">Supabase</div></div>',
        unsafe_allow_html=True,
    )

with col_s2:
    tables_str = ", ".join(status["tables"]) if status["tables"] else "none"
    cls = "status-ok" if status["tables"] else "status-warn"
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-value" style="font-size:1rem;"><span class="{cls}">{tables_str}</span></div>'
        f'<div class="kpi-label">Tables Found</div></div>',
        unsafe_allow_html=True,
    )

with col_s3:
    buckets_str = ", ".join(status["storage_buckets"]) if status["storage_buckets"] else "none"
    cls2 = "status-ok" if status["storage_buckets"] else "status-warn"
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-value" style="font-size:1rem;"><span class="{cls2}">{buckets_str}</span></div>'
        f'<div class="kpi-label">Storage Buckets</div></div>',
        unsafe_allow_html=True,
    )

# Show secrets availability (without revealing values)
st.markdown("")
st.markdown("##### 🔑 Secrets Status")

secrets_map = {
    "SUPABASE_URL": None,
    "SUPABASE_ANON_KEY": None,
    "SUPABASE_SERVICE_ROLE_KEY": None,
    "APP_PASSWORD": None,
    "DEEPSEEK_API_KEY": None,
}

def _has_secret(k):
    try:
        v = st.secrets.get(k)
        if v:
            return True
    except (FileNotFoundError, KeyError):
        pass
    return bool(os.environ.get(k))

cols = st.columns(len(secrets_map))
for col, key in zip(cols, secrets_map):
    present = _has_secret(key)
    icon = "✅" if present else "❌"
    cls = "status-ok" if present else "status-err"
    with col:
        st.markdown(
            f'<div style="text-align:center; padding:0.5rem;">'
            f'<span class="{cls}" style="font-size:1.1rem;">{icon}</span><br>'
            f'<span style="color:#8b949e; font-size:0.7rem;">{key.split("_")[-1]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("---")

# ── Data Source Configuration ────────────────────────────────────────────────
st.markdown("### 📊 Data Source")

table_name = st.text_input(
    "Supabase table name for buyer data",
    value=st.session_state.get("data_source_table", "mousa"),
    key="settings_table_name",
)
st.session_state["data_source_table"] = table_name

st.markdown("")

# ── Refresh Data ─────────────────────────────────────────────────────────────
st.markdown("### 🔄 Refresh Data")
st.caption("Clear cached data and reload fresh from Supabase.")

if st.button("🔄 Refresh Now", key="btn_refresh"):
    st.cache_data.clear()
    st.success("✅ Cache cleared! Data will reload on next page visit.")

st.markdown("---")

# ── Merge Duplicate Buyers ───────────────────────────────────────────────────
st.markdown("### 🔗 Merge Duplicate Buyers")
st.caption("Automatically merge buyers that share the same email or phone number. "
           "Keeps the highest-USD buyer name, sums totals, deduplicates contacts, merges exporters.")

if st.button("🔗 Find & Merge Duplicates", key="btn_merge_dupes", use_container_width=True):
    from services.data_helpers import merge_duplicate_buyers
    status_area = st.empty()

    def _update(msg):
        status_area.info(msg)

    with st.spinner("Scanning for duplicates…"):
        result = merge_duplicate_buyers(table_name=table_name, callback=_update)

    if result.get("error"):
        st.error(f"❌ {result['error']}")
    elif result["groups_found"] == 0:
        st.success("✅ No duplicates found — all buyers are unique!")
    else:
        st.success(
            f"✅ Done! Merged **{result['groups_found']}** groups. "
            f"Deleted **{result['rows_deleted']}** duplicate rows, "
            f"updated **{result['rows_updated']}** records."
        )
        st.cache_data.clear()

st.markdown("---")

# ── About ────────────────────────────────────────────────────────────────────
st.markdown("### ℹ️ About")
st.markdown(
    """
    **OBSIDIAN Intelligence Platform** v1.0

    Built with Streamlit + Supabase + Plotly.
    AI-powered buyer research via DeepSeek.

    *Never commit secrets. Always use `.streamlit/secrets.toml` or environment variables.*
    """
)
