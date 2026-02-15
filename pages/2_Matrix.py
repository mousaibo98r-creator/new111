"""
Page 2 — Matrix & Intelligence: searchable buyer table + detail panel + AI Scavenge
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Matrix & Intelligence", page_icon="🔴", layout="wide")

import json
import asyncio
import pandas as pd

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_sidebar_filters,
    render_sidebar_export,
    render_buyer_detail,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters, search_buyers

inject_css()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

df_all = load_buyers()
opts = get_filter_options(df_all)
selected = render_sidebar_filters(opts)
filtered = apply_filters(df_all, selected["countries"], selected["exporters"])
render_sidebar_export(filtered)

# ── Main area ────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📋 Matrix & Intelligence</div>', unsafe_allow_html=True)

# Search bar
st.markdown("🔍 **Search Buyers**")
query = st.text_input(
    "Type to filter…",
    placeholder="e.g.  @country:Kazakhstan  @buyer:iron  or free text",
    label_visibility="collapsed",
    key="matrix_search",
)

df_view = search_buyers(filtered, query) if query else filtered

# ── Layout: table left (70%), detail right (30%) ─────────────────────────────
col_table, col_detail = st.columns([7, 3])

with col_table:
    # Build display dataframe
    display_cols = {
        "buyer_name": "Buyer",
        "destination_country": "Country",
        "total_invoices": "Invoices",
        "total_usd": "USD",
        "email_str": "Email",
        "website_str": "Website",
        "phone_str": "Phone",
        "address_str": "Address",
    }
    available = [c for c in display_cols if c in df_view.columns]
    show_df = df_view[available].copy()
    show_df.columns = [display_cols[c] for c in available]

    # Format USD column
    if "USD" in show_df.columns:
        show_df["USD"] = show_df["USD"].apply(lambda v: f"${v:,.0f}" if v else "-")

    # Build HTML table for exact screenshot match
    rows_html = []
    for idx, row in show_df.iterrows():
        cells = "".join(f"<td>{row[c]}</td>" for c in show_df.columns)
        rows_html.append(f"<tr>{cells}</tr>")

    header = "".join(f"<th>{c}</th>" for c in show_df.columns)

    # Limit display to avoid DOM overload
    max_rows = 200
    html = (
        f'<div style="max-height:540px; overflow-y:auto; border:1px solid #21262d; border-radius:8px;">'
        f'<table class="buyer-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(rows_html[:max_rows])}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    st.caption(f"Showing {min(len(df_view), max_rows)} of {len(df_view)} buyers")

    # Row selector — use selectbox for row picking
    st.markdown("")
    buyer_names = ["— Select a buyer —"] + df_view["buyer_name"].tolist()[:max_rows]
    selected_buyer = st.selectbox(
        "Pick a buyer to view details",
        buyer_names,
        key="matrix_select_buyer",
        label_visibility="collapsed",
    )

# ── Right panel ──────────────────────────────────────────────────────────────
with col_detail:
    if selected_buyer and selected_buyer != "— Select a buyer —":
        match = df_view[df_view["buyer_name"] == selected_buyer]
        if not match.empty:
            row = match.iloc[0]
            result = render_buyer_detail(row)

            # ── AI Scavenge ──────────────────────────────────────────────
            deepseek_key = None
            try:
                deepseek_key = st.secrets.get("DEEPSEEK_API_KEY")
            except (FileNotFoundError, KeyError):
                deepseek_key = os.environ.get("DEEPSEEK_API_KEY")

            if deepseek_key:
                force_overwrite = st.checkbox("Force Overwrite", key="force_overwrite")
                if st.button("🔮 Scavenge (AI)", use_container_width=True, key="btn_scavenge"):
                    with st.spinner("🤖 AI is searching the web…"):
                        try:
                            from deepseek_client import DeepSeekClient

                            system_prompt = (
                                "You are a company research assistant. "
                                "Find and return contact info for the given buyer in strict JSON:\n"
                                '{"email":[],"website":[],"phone":[],"address":[],'
                                '"company_name_english":"","country_english":"","country_code":""}\n'
                                "Use web_search and fetch_page tools. Return valid JSON only."
                            )

                            client = DeepSeekClient(api_key=deepseek_key)
                            buyer_n = row.get("buyer_name", "")
                            buyer_c = row.get("destination_country", "")

                            loop = asyncio.new_event_loop()
                            status_container = st.empty()

                            def _callback(msg):
                                status_container.caption(msg)

                            raw, turns = loop.run_until_complete(
                                client.extract_company_data(
                                    system_prompt, buyer_n, buyer_c, callback=_callback
                                )
                            )
                            loop.close()

                            if raw:
                                try:
                                    result_data = json.loads(raw) if isinstance(raw, str) else raw
                                    st.success(f"✅ Scavenge complete ({turns} turns)")
                                    st.json(result_data)
                                except json.JSONDecodeError:
                                    st.warning("AI returned non-JSON response:")
                                    st.code(raw)
                            else:
                                st.warning("Scavenge returned no data.")

                        except Exception as e:
                            st.error(f"Scavenge error: {e}")
            else:
                st.info("💡 Add `DEEPSEEK_API_KEY` to secrets to enable AI Scavenge.")
    else:
        render_buyer_detail(None)
