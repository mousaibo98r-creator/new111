"""
Page 2 — Matrix & Intelligence: searchable buyer table + detail panel + AI Scavenge
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Matrix & Intelligence", page_icon="🔴", layout="wide", initial_sidebar_state="collapsed")

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
    render_top_nav,
    render_inline_filters,
    auth_gate,
)
from services.data_helpers import load_buyers, get_filter_options, apply_filters, search_buyers

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Main area ────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📋 Matrix & Intelligence</div>', unsafe_allow_html=True)

df_all = load_buyers()
opts = get_filter_options(df_all)

# ── Inline filters (visible on mobile) ───────────────────────────────────────
selected = render_inline_filters(opts, df=df_all)
filtered = apply_filters(df_all, selected["countries"], selected["exporters"])
render_sidebar_export(filtered)

# Search bar
st.markdown("🔍 **Search Buyers**")
query = st.text_input(
    "Type to filter…",
    placeholder="e.g.  @country:Kazakhstan  @buyer:iron  or free text",
    label_visibility="collapsed",
    key="matrix_search",
)

df_view = search_buyers(filtered, query) if query else filtered

# Sort by USD descending so table AND row selection stay in sync
if "total_usd" in df_view.columns:
    df_view = df_view.sort_values("total_usd", ascending=False).reset_index(drop=True)

# ── Layout: table left (70%), detail right (30%) ─────────────────────────────
col_table, col_detail = st.columns([7, 3])

with col_table:
    # Build display dataframe
    display_cols = {
        "buyer_name": "Buyer",
        "destination_country": "Country",
        "gtip_aciklamasi": "GTIP",
        "esya_ticari_tanimi": "Description",
        "total_invoices": "Invoices",
        "total_usd": "USD",
    }
    available = [c for c in display_cols if c in df_view.columns]
    show_df = df_view[available].copy().reset_index(drop=True)
    show_df.columns = [display_cols[c] for c in available]

    # Format USD column for display
    if "USD" in show_df.columns:
        show_df["USD"] = show_df["USD"].apply(lambda v: f"${v:,.0f}" if v else "-")

    # Interactive dataframe with row selection — show ALL rows (multi-select)
    event = st.dataframe(
        show_df,
        use_container_width=True,
        height=540,
        on_select="rerun",
        selection_mode="multi-row",
        key="matrix_table",
    )

    st.caption(f"Showing {len(df_view)} buyers  •  Click rows to select for scavenge")

    # Get ALL selected row indices
    selected_rows = event.selection.rows if event and event.selection else []

# ── Right panel ──────────────────────────────────────────────────────────────
with col_detail:
    if selected_rows:
        # Show details for the first selected buyer
        first_idx = selected_rows[0]
        if first_idx < len(df_view):
            row = df_view.iloc[first_idx]
            render_buyer_detail(row)
        else:
            render_buyer_detail(None)

        # ── AI Scavenge (multi-select, sequential) ───────────────────
        deepseek_key = None
        try:
            deepseek_key = st.secrets.get("DEEPSEEK_API_KEY")
        except (FileNotFoundError, KeyError):
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY")

        if deepseek_key:
            st.divider()
            force_overwrite = st.checkbox("Force Overwrite", key="force_overwrite")

            # Show queued buyers list
            valid_indices = [i for i in selected_rows if i < len(df_view)]
            queue_names = [df_view.iloc[i].get("buyer_name", "?") for i in valid_indices]

            st.markdown(f"**🔮 Scavenge Queue ({len(queue_names)})**")
            for qi, qn in enumerate(queue_names, 1):
                st.caption(f"  {qi}. {qn}")

            if st.button(
                f"🔮 Scavenge Selected ({len(queue_names)})",
                use_container_width=True,
                key="btn_scavenge",
            ):
                from deepseek_client import DeepSeekClient
                from services.supabase_client import get_client

                system_prompt = (
                    "You are an elite company contact intelligence agent. Your mission is to find "
                    "VERIFIED, REAL contact information for the given buyer company.\n\n"
                    "WORKFLOW (follow this order strictly):\n"
                    "Turn 1: web_search for the company name and country.\n"
                    '   Example: "<company name> <country>" — simple search first.\n'
                    "   → The search tool will AUTO-FETCH the homepage and contact page for you.\n"
                    "   → Check the returned all_emails and all_phones — these are VERIFIED from real pages.\n\n"
                    "Turn 2: If the search returned a contact_page URL that wasn't auto-fetched, "
                    "call fetch_page on it. Otherwise, try fetch_page on website.com/contact or /contact-us.\n\n"
                    "Turn 3: If still missing data, try a DIFFERENT search query:\n"
                    '   "<company> email phone address"\n'
                    '   "<company> <country> official website"\n'
                    '   "<company> headquarters location"\n\n'
                    "Turn 4+: Try fetching /about, /about-us, or /impressum pages. "
                    "Try searching with the English company name if the original is in another language.\n\n"
                    "CRITICAL RULES:\n"
                    "- ALWAYS include ALL emails and phones returned by the search/fetch tools.\n"
                    "- The all_emails and all_phones from search results are VERIFIED — use them directly.\n"
                    "- Prefer role emails: info@, sales@, export@, contact@, but include ALL valid ones.\n"
                    "- If you find nothing after 3+ turns, return empty arrays — NEVER fabricate data.\n"
                    "- Look for address in page_text_preview and address_hints.\n"
                    "- The Phase 0 analysis has already translated the company name — use those values.\n\n"
                    "OUTPUT: Return ONLY valid JSON with this exact structure:\n"
                    '{"email":[],"website":[],"phone":[],"address":[],'
                    '"company_name_english":"","country_english":"","country_code":""}\n'
                    "No markdown, no explanation — JSON ONLY."
                )

                progress_bar = st.progress(0, text="Starting…")
                results_container = st.container()
                total = len(valid_indices)
                success_count = 0
                fail_count = 0

                for step, idx in enumerate(valid_indices):
                    buyer_row = df_view.iloc[idx]
                    buyer_n = str(buyer_row.get("buyer_name", "")).strip()
                    buyer_c = str(buyer_row.get("destination_country", "")).strip()

                    progress_bar.progress(
                        (step) / total,
                        text=f"⏳ Processing {step + 1}/{total}: **{buyer_n}**…",
                    )

                    status_line = st.empty()
                    status_line.info(f"🤖 Scavenging **{buyer_n}** ({buyer_c})…")

                    try:
                        client = DeepSeekClient(api_key=deepseek_key)
                        loop = asyncio.new_event_loop()

                        def _callback(msg, _name=buyer_n):
                            status_line.caption(f"[{_name}] {msg}")

                        raw, turns = loop.run_until_complete(
                            client.extract_company_data(
                                system_prompt, buyer_n, buyer_c, callback=_callback
                            )
                        )
                        loop.run_until_complete(client.close())
                        loop.close()

                        if raw:
                            try:
                                result_data = json.loads(raw) if isinstance(raw, str) else raw

                                # ── Save to Supabase ─────────────
                                sb = get_client()
                                if sb:
                                    update = {}
                                    for field in ["email", "website", "phone", "address"]:
                                        if result_data.get(field):
                                            update[field] = result_data[field]

                                    # Also save translation fields
                                    for field in ["company_name_english", "country_english", "country_code"]:
                                        val = result_data.get(field)
                                        if val and isinstance(val, str) and val.strip():
                                            update[field] = val.strip()

                                    if update:
                                        resp = None
                                        try:
                                            resp = sb.table("mousa").update(update).ilike(
                                                "buyer_name", buyer_n
                                            ).execute()
                                        except Exception:
                                            resp = sb.table("mousa").update(update).ilike(
                                                "name", buyer_n
                                            ).execute()

                                        if resp and resp.data:
                                            saved_fields = list(update.keys())
                                            status_line.success(
                                                f"✅ {buyer_n} — saved {len(update)} fields: {', '.join(saved_fields)} ({turns} turns)"
                                            )
                                            success_count += 1
                                        else:
                                            status_line.warning(f"⚠️ {buyer_n} — no DB rows matched")
                                            fail_count += 1
                                    else:
                                        status_line.info(f"ℹ️ {buyer_n} — no new data found")
                                        fail_count += 1
                                else:
                                    status_line.warning(f"⚠️ {buyer_n} — Supabase not connected")
                                    fail_count += 1

                            except json.JSONDecodeError:
                                status_line.warning(f"⚠️ {buyer_n} — AI returned non-JSON")
                                fail_count += 1
                        else:
                            status_line.warning(f"⚠️ {buyer_n} — no data returned")
                            fail_count += 1

                    except Exception as e:
                        status_line.error(f"❌ {buyer_n} — error: {e}")
                        fail_count += 1

                # Done — update progress bar
                progress_bar.progress(1.0, text="✅ All done!")
                st.success(f"**Finished!** ✅ {success_count} saved, ⚠️ {fail_count} skipped")

                # Clear cache and reload after all are done
                st.cache_data.clear()
                st.rerun()
        else:
            st.info("💡 Add `DEEPSEEK_API_KEY` to secrets to enable AI Scavenge.")
    else:
        render_buyer_detail(None)
