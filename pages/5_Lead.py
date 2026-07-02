"""
Page 5 — Lead Management: full buyer data + pipeline status tracking + notes
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Lead Management", page_icon="👤", layout="wide", initial_sidebar_state="collapsed")

import pandas as pd

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_top_nav,
    render_buyer_detail,
    auth_gate,
)
from services.data_helpers import load_buyers, search_buyers
from services.crm_helpers import (
    LEAD_STATUSES,
    STATUS_COLORS,
    STATUS_ICONS,
    get_lead_stats,
    update_lead_status,
    update_lead_notes,
    bulk_update_status,
)

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Additional page-specific CSS ─────────────────────────────────────────────
st.markdown("""
<style>
.lead-status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-family: 'Inter', sans-serif;
}
.pipeline-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
    transition: all 0.25s ease;
}
.pipeline-card:hover {
    border-color: #a855f7;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(168,85,247,0.08);
}
.pipeline-count {
    font-size: 1.8rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.2;
}
.pipeline-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #8b949e;
    margin-top: 4px;
}
.bulk-actions-bar {
    background: linear-gradient(135deg, rgba(168,85,247,0.08) 0%, rgba(96,165,250,0.08) 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 12px 20px;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ── Main area ────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">👤 Lead Management</div>', unsafe_allow_html=True)

# ── Load data (same as Matrix) ───────────────────────────────────────────────
df_all = load_buyers()

if df_all.empty:
    st.warning("⚠️ No data loaded. Check your Supabase connection.")
    st.stop()

# Ensure status column
if "status" not in df_all.columns:
    df_all["status"] = "new"
else:
    df_all["status"] = df_all["status"].fillna("new")

# Ensure notes column
if "notes" not in df_all.columns:
    df_all["notes"] = ""
else:
    df_all["notes"] = df_all["notes"].fillna("")

# ── Pipeline KPI Cards ───────────────────────────────────────────────────────
stats = get_lead_stats(df_all)

pipeline_items = [
    ("total", "Total Leads", "#a855f7"),
    ("new", "New", STATUS_COLORS["new"]),
    ("contacted", "Contacted", STATUS_COLORS["contacted"]),
    ("replied", "Replied", STATUS_COLORS["replied"]),
    ("interested", "Interested", STATUS_COLORS["interested"]),
    ("not_interested", "Not Interested", STATUS_COLORS["not_interested"]),
    ("bounced", "Bounced", STATUS_COLORS["bounced"]),
]

cols = st.columns(len(pipeline_items))
for col, (key, label, color) in zip(cols, pipeline_items):
    with col:
        st.markdown(f"""
            <div class="pipeline-card">
                <div class="pipeline-count" style="color: {color};">{stats.get(key, 0):,}</div>
                <div class="pipeline-label">{label}</div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("")

# ── Filter Bar ───────────────────────────────────────────────────────────────
with st.expander("🔧 Filters & Search", expanded=True):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        search_query = st.text_input(
            "🔍 Search",
            placeholder="Search buyers, emails, GTIP...",
            key="lead_search",
        )
    with fc2:
        status_filter = st.selectbox(
            "Status",
            options=["All"] + LEAD_STATUSES,
            key="lead_status_filter",
        )
    with fc3:
        countries = sorted(df_all["destination_country"].dropna().unique().tolist()) if "destination_country" in df_all.columns else []
        country_filter = st.selectbox(
            "Country",
            options=["All"] + countries,
            key="lead_country_filter",
        )
    with fc4:
        sort_col = st.selectbox(
            "Sort By",
            options=["total_usd", "total_invoices", "buyer_name", "status", "destination_country"],
            format_func=lambda x: {"total_usd": "USD Volume", "total_invoices": "Invoices", "buyer_name": "Name", "status": "Status", "destination_country": "Country"}.get(x, x),
            key="lead_sort",
        )

# ── Apply Filters ────────────────────────────────────────────────────────────
df_view = df_all.copy()

if search_query:
    df_view = search_buyers(df_view, search_query)

if status_filter != "All":
    df_view = df_view[df_view["status"] == status_filter]

if country_filter != "All":
    df_view = df_view[df_view["destination_country"] == country_filter]

# Sort
if sort_col in df_view.columns:
    ascending = sort_col in ["buyer_name", "status", "destination_country"]
    df_view = df_view.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

# ── Layout: table left (70%), detail right (30%) ─────────────────────────────
col_table, col_detail = st.columns([7, 3])

with col_table:
    # Build display dataframe
    display_cols = {
        "buyer_name": "Buyer",
        "status": "Status",
        "destination_country": "Country",
        "gtip_aciklamasi": "GTIP",
        "esya_ticari_tanimi": "Description",
        "total_invoices": "Invoices",
        "total_usd": "USD",
        "email_str": "Email",
        "phone_str": "Phone",
    }
    available = [c for c in display_cols if c in df_view.columns]
    show_df = df_view[available].copy().reset_index(drop=True)
    show_df.columns = [display_cols[c] for c in available]

    # Format USD column
    if "USD" in show_df.columns:
        show_df["USD"] = show_df["USD"].apply(lambda v: f"${v:,.0f}" if v else "-")

    # Format status with emoji
    if "Status" in show_df.columns:
        show_df["Status"] = show_df["Status"].apply(
            lambda s: f"{STATUS_ICONS.get(s, '⚪')} {s}" if s else "⚪ new"
        )

    # Interactive table with multi-select
    event = st.dataframe(
        show_df,
        use_container_width=True,
        height=480,
        on_select="rerun",
        selection_mode="multi-row",
        key="lead_table",
    )

    selected_rows = event.selection.rows if event and event.selection else []

    st.caption(f"Showing {len(df_view)} leads  •  {len(selected_rows)} selected")

    # ── Bulk Actions Bar ─────────────────────────────────────────────────────
    if selected_rows:
        st.markdown('<div class="bulk-actions-bar">', unsafe_allow_html=True)
        ba1, ba2, ba3 = st.columns([2, 2, 1])
        with ba1:
            st.markdown(f"**⚡ {len(selected_rows)} lead(s) selected**")
        with ba2:
            bulk_status = st.selectbox(
                "Change status to",
                options=LEAD_STATUSES,
                key="bulk_status_select",
                label_visibility="collapsed",
            )
        with ba3:
            if st.button("✅ Apply", use_container_width=True, key="btn_bulk_apply"):
                names = [df_view.iloc[i].get("buyer_name", "") for i in selected_rows if i < len(df_view)]
                names = [n for n in names if n]
                if names:
                    count = bulk_update_status(names, bulk_status)
                    st.success(f"Updated {count} lead(s) to '{bulk_status}'")
                    st.cache_data.clear()
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ── Right Panel — Detail + Status + Notes ────────────────────────────────────
with col_detail:
    if selected_rows and len(selected_rows) > 0:
        first_idx = selected_rows[0]
        if first_idx < len(df_view):
            row = df_view.iloc[first_idx]
            buyer_name = row.get("buyer_name", "")

            # Render the standard buyer detail (same as Matrix)
            render_buyer_detail(row)

            # ── Lead Status Management ───────────────────────────────────
            st.markdown("---")
            st.markdown('<div class="detail-panel-title">📋 Lead Management</div>', unsafe_allow_html=True)

            current_status = row.get("status", "new") or "new"

            # Status badge
            color = STATUS_COLORS.get(current_status, "#8b949e")
            icon = STATUS_ICONS.get(current_status, "⚪")
            st.markdown(
                f'<div class="lead-status-badge" style="background: {color}22; color: {color}; border: 1px solid {color}44;">'
                f'{icon} {current_status.upper()}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")

            # Status changer
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                new_status = st.selectbox(
                    "Change Status",
                    options=LEAD_STATUSES,
                    index=LEAD_STATUSES.index(current_status) if current_status in LEAD_STATUSES else 0,
                    key="detail_status_select",
                    label_visibility="collapsed",
                )
            with sc2:
                if st.button("💾", key="btn_save_status", use_container_width=True):
                    if update_lead_status(buyer_name, new_status):
                        st.success(f"✅ Status → {new_status}")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Failed to update")

            # Notes
            st.markdown("")
            st.markdown('<div class="detail-label">NOTES</div>', unsafe_allow_html=True)
            current_notes = row.get("notes", "") or ""
            new_notes = st.text_area(
                "Notes",
                value=current_notes,
                height=120,
                key="detail_notes",
                label_visibility="collapsed",
                placeholder="Add notes about this lead...",
            )
            if st.button("💾 Save Notes", key="btn_save_notes", use_container_width=True):
                if update_lead_notes(buyer_name, new_notes):
                    st.success("✅ Notes saved")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to save notes")

        else:
            render_buyer_detail(None)
    else:
        st.markdown(
            '<div class="detail-default">Select a lead to view details and manage status.</div>',
            unsafe_allow_html=True,
        )
