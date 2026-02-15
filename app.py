"""
OBSIDIAN Intelligence Platform — Entry Point
"""

import streamlit as st

# ── Page config must come FIRST ──────────────────────────────────────────────
st.set_page_config(
    page_title="OBSIDIAN Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports ──────────────────────────────────────────────────────────────────
import os, sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
)

# ── Show nav ─────────────────────────────────────────────────────────────────
inject_css()
render_sidebar_brand()
render_sidebar_nav()

# ── Home content ─────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">⚡ Welcome to OBSIDIAN</div>', unsafe_allow_html=True)
st.markdown(
    """
    <div style="color:#8b949e; font-size:1rem; margin-top:0.4rem; max-width:640px;">
        Your strategic intelligence hub. Use the sidebar to navigate between pages:
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("")

c1, c2, c3, c4 = st.columns(4)
cards = [
    ("📊", "Dashboard", "3D bubble scatter of buyers"),
    ("🔴", "Matrix", "Buyer data table & search"),
    ("📁", "Archive", "File storage & recovery"),
    ("⚙️", "Settings", "Connection & sync"),
]
for col, (icon, title, desc) in zip([c1, c2, c3, c4], cards):
    with col:
        st.markdown(
            f'<div class="kpi-card" style="text-align:center; padding:1.5rem 1rem;">'
            f'<div style="font-size:2rem;">{icon}</div>'
            f'<div style="color:#e6edf3; font-weight:600; margin-top:0.5rem;">{title}</div>'
            f'<div style="color:#8b949e; font-size:0.78rem; margin-top:0.3rem;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
