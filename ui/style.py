"""
OBSIDIAN dark-theme CSS — injected into every page via st.markdown.
"""

import streamlit as st

OBSIDIAN_CSS = """
<style>
/* ── Import Google Font ──────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global ──────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* Hide Streamlit footer & menu */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Reduce top padding */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 1rem !important;
}

/* ── Sidebar ─────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background-color: #0d1117 !important;
    border-right: 1px solid #21262d !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1rem !important;
}

/* Brand title in sidebar */
.sidebar-brand {
    font-size: 1.4rem;
    font-weight: 700;
    color: #a855f7;
    margin-bottom: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.sidebar-brand-sub {
    font-size: 0.75rem;
    color: #8b949e;
    margin-bottom: 1.2rem;
    letter-spacing: 0.5px;
}

/* Sidebar section headers */
.sidebar-section {
    font-size: 0.8rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 1.2rem;
    margin-bottom: 0.4rem;
    border-top: 1px solid #21262d;
    padding-top: 0.8rem;
}

/* ── Page Title ──────────────────────────────────── */
.page-title {
    font-size: 1.8rem;
    font-weight: 700;
    color: #e6edf3;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.3rem;
}

/* ── KPI Cards ───────────────────────────────────── */
.kpi-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
}
.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #a855f7;
}
.kpi-label {
    font-size: 0.8rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 0.3rem;
}

/* ── Data Table ──────────────────────────────────── */
.buyer-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}
.buyer-table th {
    background-color: #161b22;
    color: #8b949e;
    font-weight: 600;
    padding: 0.6rem 0.8rem;
    text-align: left;
    border-bottom: 2px solid #21262d;
    position: sticky;
    top: 0;
    z-index: 1;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.5px;
}
.buyer-table td {
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid #161b22;
    color: #c9d1d9;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.buyer-table tr:hover {
    background-color: #1c2333 !important;
    cursor: pointer;
}
.buyer-table tr.selected-row {
    background-color: #1f1936 !important;
    border-left: 3px solid #a855f7;
}
.buyer-table tr:nth-child(even) {
    background-color: #0d1117;
}
.buyer-table tr:nth-child(odd) {
    background-color: #0e1117;
}

/* ── Detail Panel ────────────────────────────────── */
.detail-panel {
    background: linear-gradient(135deg, #161b22 0%, #1a1f2b 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 1.5rem;
    min-height: 200px;
}
.detail-panel-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #a855f7;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
}
.detail-buyer-name {
    font-size: 1.2rem;
    font-weight: 700;
    color: #e2b33c;
    margin-bottom: 0.2rem;
}
.detail-english {
    font-size: 0.82rem;
    color: #8b949e;
    margin-bottom: 1rem;
}
.detail-label {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 0.8rem;
    margin-bottom: 0.2rem;
}
.detail-value {
    color: #c9d1d9;
    font-size: 0.88rem;
}
.detail-link {
    color: #58a6ff;
    text-decoration: none;
}
.detail-link:hover {
    text-decoration: underline;
}
.detail-phone-link {
    color: #3fb950;
    text-decoration: none;
}

/* ── Location / Volume Row ───────────────────────── */
.loc-vol-row {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    margin-bottom: 1rem;
}
.loc-vol-item {
    flex: 1;
}
.loc-vol-label {
    font-size: 0.7rem;
    color: #a855f7;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
}
.loc-vol-value {
    font-size: 0.9rem;
    color: #c9d1d9;
    margin-top: 0.1rem;
}

/* ── Search Bar ──────────────────────────────────── */
div[data-testid="stTextInput"] input {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 1px #a855f7 !important;
}

/* ── Buttons ─────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

/* ── Multiselect ─────────────────────────────────── */
div[data-testid="stMultiSelect"] {
    font-size: 0.85rem;
}

/* ── Default text in detail area ─────────────────── */
.detail-default {
    color: #3fb950;
    font-size: 0.92rem;
    padding: 1rem;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    text-align: center;
}

/* ── Actions section ─────────────────────────────── */
.actions-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #e6edf3;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-top: 1.5rem;
    margin-bottom: 0.8rem;
}

/* ── File list table ─────────────────────────────── */
.file-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}
.file-table th {
    background-color: #161b22;
    color: #8b949e;
    font-weight: 600;
    padding: 0.5rem 0.8rem;
    text-align: left;
    border-bottom: 2px solid #21262d;
    font-size: 0.72rem;
    text-transform: uppercase;
}
.file-table td {
    padding: 0.5rem 0.8rem;
    border-bottom: 1px solid #161b22;
    color: #c9d1d9;
}
.file-table tr:hover {
    background-color: #1c2333 !important;
}

/* ── Status badges ───────────────────────────────── */
.status-ok {
    color: #3fb950;
    font-weight: 600;
}
.status-err {
    color: #f85149;
    font-weight: 600;
}
.status-warn {
    color: #e2b33c;
    font-weight: 600;
}

/* ── Plotly charts — dark background ─────────────── */
.js-plotly-plot .plotly .main-svg {
    background-color: #0e1117 !important;
}
</style>
"""


def inject_css():
    """Call at the top of every page to apply the OBSIDIAN theme."""
    st.markdown(OBSIDIAN_CSS, unsafe_allow_html=True)
