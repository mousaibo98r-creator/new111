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
selected = render_sidebar_filters(opts, df=df_all)
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
    show_df = df_view[available].copy().reset_index(drop=True)
    show_df.columns = [display_cols[c] for c in available]

    # Format USD column for display
    if "USD" in show_df.columns:
        show_df["USD"] = show_df["USD"].apply(lambda v: f"${v:,.0f}" if v else "-")

    # Interactive dataframe with row selection — show ALL rows
    event = st.dataframe(
        show_df,
        use_container_width=True,
        height=540,
        on_select="rerun",
        selection_mode="single-row",
        key="matrix_table",
    )

    st.caption(f"Showing {len(df_view)} buyers  •  Click a row to view details")

    # Get selected row index
    selected_rows = event.selection.rows if event and event.selection else []
    selected_idx = selected_rows[0] if selected_rows else None

# ── Right panel ──────────────────────────────────────────────────────────────
with col_detail:
    if selected_idx is not None and selected_idx < len(df_view):
        row = df_view.iloc[selected_idx]
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

                                # ── Save to Supabase DB ──────────────────
                                from services.supabase_client import get_client
                                sb = get_client()
                                if sb:
                                    # Build update — only contact fields
                                    update = {}
                                    for field in ["email", "website", "phone", "address"]:
                                        if result_data.get(field):
                                            update[field] = result_data[field]

                                    if update:
                                        try:
                                            # Use id (primary key) if available — guaranteed match
                                            row_id = row.get("id", None)
                                            if row_id is not None:
                                                resp = sb.table("mousa").update(update).eq(
                                                    "id", int(row_id)
                                                ).execute()
                                            else:
                                                # Fallback: match by buyer_name
                                                buyer_n = row.get("buyer_name", "")
                                                resp = sb.table("mousa").update(update).eq(
                                                    "buyer_name", buyer_n
                                                ).execute()

                                            if resp.data:
                                                st.success(f"💾 Saved {len(update)} fields to database!")
                                                st.cache_data.clear()
                                            else:
                                                # Show debug info
                                                st.warning(f"⚠️ No rows matched. Row ID={row_id}")
                                                st.json({"update_payload": update, "response": str(resp)})
                                        except Exception as save_err:
                                            st.error(f"❌ DB save error: {save_err}")
                                    else:
                                        st.info("No new contact data to save.")
                                else:
                                    st.warning("⚠️ Supabase not connected — data not saved.")

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
