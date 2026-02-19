"""
OBSIDIAN dark-theme CSS — injected into every page via st.markdown.
"""

import streamlit as st

OBSIDIAN_CSS = """
<style>
/* ── Import Google Font ──────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

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
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 14px 14px 0 0;
}
.kpi-card-purple::before   { background: linear-gradient(90deg, #a855f7, #c084fc); }
.kpi-card-green::before    { background: linear-gradient(90deg, #22c55e, #4ade80); }
.kpi-card-blue::before     { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.kpi-card-amber::before    { background: linear-gradient(90deg, #f59e0b, #fbbf24); }

.kpi-card-purple .kpi-value { color: #c084fc; }
.kpi-card-green  .kpi-value { color: #4ade80; }
.kpi-card-blue   .kpi-value { color: #60a5fa; }
.kpi-card-amber  .kpi-value { color: #fbbf24; }

.kpi-value {
    font-size: 2rem;
    font-weight: 700;
    color: #a855f7;
    letter-spacing: -0.5px;
}
.kpi-label {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.4rem;
    font-weight: 500;
}

/* ── Chart containers ───────────────────────────── */
.chart-container {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
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
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3) !important;
}

/* ── Top nav page links ─────────────────────────── */
a[data-testid="stPageLink-NavLink"] {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%) !important;
    border: 1px solid #30363d !important;
    border-radius: 10px !important;
    padding: 0.5rem 0.8rem !important;
    text-align: center !important;
    transition: all 0.2s ease !important;
    text-decoration: none !important;
}
a[data-testid="stPageLink-NavLink"]:hover {
    border-color: #a855f7 !important;
    box-shadow: 0 0 12px rgba(168, 85, 247, 0.25) !important;
    transform: translateY(-1px);
}
a[data-testid="stPageLink-NavLink"][aria-current="page"] {
    border-color: #a855f7 !important;
    background: linear-gradient(135deg, #1f1936 0%, #2a1f47 100%) !important;
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

/* ── Dashboard specific ─────────────────────────── */
.stPlotlyChart {
    background: #0e1117;
    border-radius: 12px;
    border: 1px solid #21262d;
    padding: 0.5rem;
}

/* ── Hide built-in Streamlit page nav (we have our own) ──── */
section[data-testid="stSidebar"] > div:first-child > div:first-child > div:first-child ul {
    display: none !important;
}

/* Alternative selectors for Streamlit's auto-generated nav */
[data-testid="stSidebarNavItems"] {
    display: none !important;
}
nav[data-testid="stSidebarNav"] {
    display: none !important;
}

/* ── Mobile Responsive ──────────────────────────── */
@media (max-width: 768px) {
    /* Make sidebar an overlay, not push content */
    section[data-testid="stSidebar"] {
        z-index: 999 !important;
        box-shadow: 4px 0 24px rgba(0,0,0,0.6);
    }

    /* Reduce padding on mobile */
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        padding-top: 1rem !important;
    }

    /* Smaller page title */
    .page-title {
        font-size: 1.3rem;
    }

    /* KPI cards: smaller on mobile */
    .kpi-card {
        padding: 0.8rem 0.6rem;
    }
    .kpi-value {
        font-size: 1.4rem;
    }
    .kpi-label {
        font-size: 0.65rem;
    }

    /* Detail panel fits screen */
    .detail-panel {
        padding: 1rem;
        min-height: auto;
    }
    .detail-buyer-name {
        font-size: 1rem;
    }
    .detail-panel-title {
        font-size: 0.95rem;
    }

    /* Table scroll horizontal on mobile */
    .buyer-table {
        font-size: 0.72rem;
    }
    .buyer-table td {
        padding: 0.4rem 0.5rem;
        max-width: 120px;
    }
    .buyer-table th {
        padding: 0.4rem 0.5rem;
        font-size: 0.65rem;
    }

    /* Sidebar brand smaller */
    .sidebar-brand {
        font-size: 1.1rem;
    }

    /* Loc-vol row stack on mobile */
    .loc-vol-row {
        flex-direction: column;
        gap: 0.5rem;
    }
}

/* ── Very small phones ──────────────────────────── */
@media (max-width: 480px) {
    .page-title {
        font-size: 1.1rem;
    }
    .kpi-value {
        font-size: 1.2rem;
    }
    .detail-buyer-name {
        font-size: 0.9rem;
    }
}

/* ── Keyframe Animations ────────────────────────── */
@keyframes borderGlow {
    0%, 100% { border-color: rgba(168, 85, 247, 0.3); box-shadow: 0 0 20px rgba(168, 85, 247, 0.08); }
    50% { border-color: rgba(168, 85, 247, 0.7); box-shadow: 0 0 40px rgba(168, 85, 247, 0.2), 0 0 80px rgba(168, 85, 247, 0.05); }
}
@keyframes scanline {
    0% { top: -100%; }
    100% { top: 200%; }
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
@keyframes typewriter {
    from { width: 0; }
    to { width: 100%; }
}
@keyframes shimmer {
    0% { background-position: -200% center; }
    100% { background-position: 200% center; }
}
@keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-6px); }
}

/* ── Access Protocol Login ──────────────────────── */
.login-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 92vh;
    padding: 1rem;
    position: relative;
    overflow: hidden;
}

/* Background grid pattern */
.login-wrapper::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image:
        linear-gradient(rgba(168, 85, 247, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(168, 85, 247, 0.03) 1px, transparent 1px);
    background-size: 50px 50px;
    pointer-events: none;
    z-index: 0;
}

/* Radial glow behind card */
.login-wrapper::after {
    content: '';
    position: fixed;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 600px; height: 600px;
    background: radial-gradient(circle, rgba(168, 85, 247, 0.08) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
}

.login-card {
    background: rgba(13, 17, 23, 0.92);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 16px;
    padding: 2.8rem 2.8rem 2.2rem;
    width: 100%;
    max-width: 440px;
    position: relative;
    z-index: 1;
    animation: fadeInUp 0.6s ease-out, borderGlow 4s ease-in-out infinite;
    overflow: hidden;
}

/* Scanline effect */
.login-card::before {
    content: '';
    position: absolute;
    top: -100%; left: 0; right: 0;
    height: 40px;
    background: linear-gradient(to bottom, transparent, rgba(168, 85, 247, 0.04), transparent);
    animation: scanline 6s linear infinite;
    pointer-events: none;
    z-index: 2;
}

/* Top accent bar */
.login-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #a855f7, #c084fc, #a855f7, transparent);
    background-size: 200% 100%;
    animation: shimmer 3s linear infinite;
}

/* ── Header Section ─────────────────────────────── */
.login-header {
    text-align: center;
    margin-bottom: 2rem;
    animation: fadeInUp 0.6s ease-out 0.1s both;
}
.login-icon {
    font-size: 2.8rem;
    display: inline-block;
    animation: float 3s ease-in-out infinite;
    margin-bottom: 0.8rem;
    filter: drop-shadow(0 0 12px rgba(168, 85, 247, 0.4));
}
.login-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #e6edf3;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
    text-shadow: 0 0 20px rgba(168, 85, 247, 0.3);
}
.login-subtitle {
    font-size: 0.72rem;
    color: #8b949e;
    letter-spacing: 3px;
    text-transform: uppercase;
    font-weight: 400;
}

/* ── Status Indicator ───────────────────────────── */
.login-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-bottom: 1.8rem;
    animation: fadeInUp 0.6s ease-out 0.2s both;
}
.login-status-dot {
    width: 6px; height: 6px;
    background: #3fb950;
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
    box-shadow: 0 0 8px rgba(63, 185, 80, 0.5);
}
.login-status-text {
    font-size: 0.68rem;
    color: #3fb950;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 500;
}

/* ── Divider ────────────────────────────────────── */
.login-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #21262d, transparent);
    margin-bottom: 1.8rem;
}

/* ── Field Labels ───────────────────────────────── */
.login-field-label {
    font-size: 0.68rem;
    color: #a855f7;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 0.35rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.login-field-label::before {
    content: '›';
    color: #a855f7;
    font-weight: 700;
    font-size: 0.9rem;
}

/* ── Input Fields ───────────────────────────────── */
.login-card div[data-testid="stTextInput"] input {
    background: rgba(22, 27, 34, 0.8) !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
    padding: 0.7rem 1rem !important;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.5px !important;
    transition: all 0.3s ease !important;
}
.login-card div[data-testid="stTextInput"] input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 1px #a855f7, 0 0 16px rgba(168, 85, 247, 0.15) !important;
    background: rgba(22, 27, 34, 1) !important;
}
.login-card div[data-testid="stTextInput"] input::placeholder {
    color: #484f58 !important;
    font-style: italic !important;
}

/* Password dots styling */
.login-card div[data-testid="stTextInput"] input[type="password"] {
    letter-spacing: 4px !important;
}

/* ── Remember Me Checkbox ───────────────────────── */
.login-card div[data-testid="stCheckbox"] {
    margin-top: 0.4rem;
    margin-bottom: 1rem;
}
.login-card div[data-testid="stCheckbox"] label span {
    font-size: 0.78rem !important;
    color: #8b949e !important;
    font-weight: 400 !important;
}
.login-card div[data-testid="stCheckbox"] label span[role="checkbox"] {
    border-color: #30363d !important;
}

/* ── Initialize Button ─────────────────────────── */
.login-btn-row {
    margin-top: 0.5rem;
}
.login-btn-row .stButton > button {
    width: 100% !important;
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(168, 85, 247, 0.05) 100%) !important;
    border: 1px solid rgba(168, 85, 247, 0.4) !important;
    color: #c084fc !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    padding: 0.7rem 1.5rem !important;
    border-radius: 8px !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    transition: all 0.3s ease !important;
    position: relative !important;
    overflow: hidden !important;
}
.login-btn-row .stButton > button:hover {
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.3) 0%, rgba(168, 85, 247, 0.15) 100%) !important;
    border-color: #a855f7 !important;
    color: #e6edf3 !important;
    box-shadow: 0 0 24px rgba(168, 85, 247, 0.3), 0 4px 16px rgba(0, 0, 0, 0.3) !important;
    transform: translateY(-1px) !important;
}
.login-btn-row .stButton > button:active {
    transform: translateY(0) !important;
    box-shadow: 0 0 12px rgba(168, 85, 247, 0.2) !important;
}

/* ── Footer ─────────────────────────────────────── */
.login-footer {
    text-align: center;
    margin-top: 1.6rem;
    padding-top: 1.2rem;
    border-top: 1px solid rgba(33, 38, 45, 0.6);
}
.login-footer-text {
    font-size: 0.62rem;
    color: #484f58;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-weight: 400;
}
.login-version {
    font-size: 0.58rem;
    color: #30363d;
    letter-spacing: 1px;
    margin-top: 0.3rem;
}

/* ── Error styling inside login card ────────────── */
.login-card div[data-testid="stAlert"] {
    background: rgba(248, 81, 73, 0.08) !important;
    border: 1px solid rgba(248, 81, 73, 0.3) !important;
    border-radius: 8px !important;
    animation: fadeInUp 0.3s ease-out;
}

/* ── Mobile Responsive Login ────────────────────── */
@media (max-width: 768px) {
    .login-card {
        padding: 2rem 1.5rem 1.5rem;
        max-width: 100%;
        border-radius: 12px;
    }
    .login-title {
        font-size: 1.3rem;
        letter-spacing: 1.5px;
    }
    .login-icon {
        font-size: 2.2rem;
    }
    .login-subtitle {
        font-size: 0.65rem;
        letter-spacing: 2px;
    }
}

@media (max-width: 480px) {
    .login-card {
        padding: 1.5rem 1.2rem 1.2rem;
    }
    .login-title {
        font-size: 1.1rem;
    }
    .login-icon {
        font-size: 1.8rem;
    }
}
</style>
"""


def inject_css():
    """Call at the top of every page to apply the OBSIDIAN theme."""
    st.markdown(OBSIDIAN_CSS, unsafe_allow_html=True)
