"""
OBSIDIAN Intelligence Platform — Entry Point
Starts directly on Dashboard.
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

# Redirect to Dashboard immediately
st.switch_page("pages/1_Dashboard.py")
