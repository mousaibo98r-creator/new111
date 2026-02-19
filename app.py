"""
OBSIDIAN Intelligence Platform — Entry Point
Shows Access Protocol login, then redirects to Dashboard.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# ── Page config — sidebar collapsed on mobile ────────────────────────────────
st.set_page_config(
    page_title="OBSIDIAN Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auth gate — shows Access Protocol login if not authenticated ──────────────
from ui.components import auth_gate
auth_gate()

# Redirect to Dashboard after successful login
st.switch_page("pages/1_Dashboard.py")
