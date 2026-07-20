"""
Page 5 — Lead Management: Leads Database + Quick Add + Status Update + Send to Campaign
Matches CRM2 dashboard Leads tab exactly.
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
    add_lead,
)

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Sidebar: Quick Add Lead ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("#### ➕ Quick Add Lead")
    with st.form("quick_add_form", clear_on_submit=True):
        qa_name = st.text_input("Name", placeholder="Lead Name")
        qa_company = st.text_input("Company", placeholder="Company Name")
        qa_email = st.text_input("Email", placeholder="email@domain.com")
        qa_country = st.text_input("Country", placeholder="e.g. Germany")

        qa_submit = st.form_submit_button("Add Lead", use_container_width=True)
        if qa_submit:
            if not qa_name or not qa_email:
                st.warning("⚠️ Name and Email are required.")
            elif "@" not in qa_email or "." not in qa_email:
                st.error("⚠️ Invalid email format.")
            else:
                if add_lead(
                    buyer_name=qa_name,
                    email=qa_email,
                    country=qa_country if qa_country.strip() else "",
                    company=qa_company if qa_company.strip() else "",
                ):
                    st.success(f"✅ Lead Added: {qa_name}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Insertion failed.")

# ── Page-specific CSS ────────────────────────────────────────────────────────
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

# Explode emails so that companies with multiple emails show up in separate rows (with one email per row)
if "email_str" in df_all.columns:
    df_all["email_str"] = df_all["email_str"].apply(lambda x: [e.strip() for e in str(x).split(",") if e.strip()] if x else [""])
    df_all = df_all.explode("email_str").reset_index(drop=True)


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

# Ensure company column
if "company_name_english" not in df_all.columns:
    df_all["company_name_english"] = ""
else:
    df_all["company_name_english"] = df_all["company_name_english"].fillna("")

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

# ── Add New Lead ─────────────────────────────────────────────────────────────
with st.expander("➕ Add New Lead", expanded=False):
    st.markdown("Enter details to manually create a new lead in the database.")
    with st.form("add_lead_form_main"):
        nl1, nl2, nl3, nl4 = st.columns(4)
        with nl1:
            new_buyer_name = st.text_input("Buyer / Company Name *")
        with nl2:
            new_company = st.text_input("Company Name (English)")
        with nl3:
            new_email = st.text_input("Email Address")
        with nl4:
            country_options = sorted(df_all["destination_country"].dropna().unique().tolist()) if "destination_country" in df_all.columns else []
            new_country = st.selectbox("Country", options=[""] + country_options)
            
        submit_lead = st.form_submit_button("💾 Save Lead")
        if submit_lead:
            if not new_buyer_name.strip():
                st.error("Buyer / Company Name is required.")
            else:
                if add_lead(new_buyer_name.strip(), new_email.strip(), new_country, "new", new_company.strip()):
                    st.success(f"Lead '{new_buyer_name}' added successfully!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to add lead. Check database connection.")


# ── Filter & Sort Control panel ──────────────────────────────────────────────
f_row1 = st.columns(5)
with f_row1[0]:
    search_name = st.text_input("🔍 Filter by Lead Name", "", key="leads_filter_name")
with f_row1[1]:
    search_company = st.text_input("🏢 Filter by Company", "", key="leads_filter_company")
with f_row1[2]:
    search_desc = st.text_input("📦 Search Description", "", key="leads_filter_desc")
with f_row1[3]:
    unique_desc = ["All"]
    if not df_all.empty and "esya_ticari_tanimi" in df_all.columns:
        unique_desc += sorted([str(x) for x in df_all["esya_ticari_tanimi"].dropna().unique().tolist() if str(x).strip()])
    filter_desc = st.selectbox("📋 Select Description", unique_desc, key="leads_filter_desc_sel")
with f_row1[4]:
    all_statuses = ["All"] + LEAD_STATUSES
    filter_status = st.selectbox("📌 Filter by Status", all_statuses, key="leads_filter_status")

f_row2 = st.columns(3)
with f_row2[0]:
    unique_countries = ["All"]
    if not df_all.empty and "destination_country" in df_all.columns:
        unique_countries += sorted(df_all["destination_country"].dropna().unique().tolist())
    filter_country = st.selectbox("🌍 Filter by Country", unique_countries, key="leads_filter_country")
with f_row2[1]:
    sort_options = ["USD Volume", "Invoices", "Name", "Company", "Status", "Country"]
    sort_by = st.selectbox("↕️ Sort by Column", sort_options, index=0, key="leads_sort_by")
with f_row2[2]:
    sort_order = st.selectbox("↕️ Sort Order", ["Descending", "Ascending"], index=0, key="leads_sort_order")

# ── Apply Filters ────────────────────────────────────────────────────────────
view_leads = df_all.copy()

if search_name:
    view_leads = view_leads[view_leads["buyer_name"].str.contains(search_name, case=False, na=False)]
if search_company:
    view_leads = view_leads[view_leads["company_name_english"].str.contains(search_company, case=False, na=False)]
if search_desc and "esya_ticari_tanimi" in view_leads.columns:
    view_leads = view_leads[view_leads["esya_ticari_tanimi"].str.contains(search_desc, case=False, na=False)]
if filter_desc != "All" and "esya_ticari_tanimi" in view_leads.columns:
    view_leads = view_leads[view_leads["esya_ticari_tanimi"] == filter_desc]
if filter_status != "All":
    view_leads = view_leads[view_leads["status"] == filter_status]
if filter_country != "All" and "destination_country" in view_leads.columns:
    view_leads = view_leads[view_leads["destination_country"] == filter_country]

# Apply Sorting
sort_col_map = {
    "Name": "buyer_name",
    "Company": "company_name_english",
    "Status": "status",
    "Country": "destination_country",
    "Invoices": "total_invoices",
    "USD Volume": "total_usd",
}
actual_sort_col = sort_col_map.get(sort_by, "total_usd")
if actual_sort_col in view_leads.columns:
    view_leads = view_leads.sort_values(
        by=actual_sort_col,
        ascending=(sort_order == "Ascending"),
        na_position="last"
    )

# Add Select checkbox column
if "Select" not in view_leads.columns:
    selected_emails = st.session_state.get("selected_emails_targeted", [])
    view_leads.insert(0, "Select", view_leads.get("email_str", pd.Series("", index=view_leads.index)).isin(selected_emails))

# Define display columns
display_cols = ["Select", "buyer_name", "company_name_english", "email_str", "status"]
additional_cols = ["destination_country", "total_invoices", "total_usd", "gtip_aciklamasi", "esya_ticari_tanimi", "website_str", "phone_str", "notes"]
for col in additional_cols:
    if col in view_leads.columns:
        display_cols.append(col)

# Filter to available columns only
display_cols = [c for c in display_cols if c in view_leads.columns]
view_leads_display = view_leads[display_cols].copy()

# ── Render Leads Grid ────────────────────────────────────────────────────────
if view_leads_display.empty:
    st.info("No leads matching selected filters.")
else:
    with st.form("leads_selection_form", border=False):
        col_btn, col_info = st.columns([1, 2])
        with col_btn:
            submit_btn = st.form_submit_button("🎯 Save Selection Changes", use_container_width=True)
        with col_info:
            st.markdown("<p style='margin-top: 8px; color: #7070A0; font-size: 0.85rem;'>💡 Toggle checkboxes below, then click <b>Save Selection Changes</b> to update targeted leads.</p>", unsafe_allow_html=True)

        edited_df = st.data_editor(
            view_leads_display,
            use_container_width=True,
            hide_index=True,
            key="lead_editor_select",
            column_config={
                "Select": st.column_config.CheckboxColumn("✓", default=False, width="small"),
                "buyer_name": st.column_config.TextColumn("Name", disabled=True),
                "company_name_english": st.column_config.TextColumn("Company", disabled=True),
                "email_str": st.column_config.TextColumn("Email", disabled=True),
                "status": st.column_config.TextColumn("Status", disabled=True),
                "destination_country": st.column_config.TextColumn("Country", disabled=True),
                "total_invoices": st.column_config.NumberColumn("Invoices", disabled=True, format="%d"),
                "total_usd": st.column_config.NumberColumn("USD Volume", disabled=True, format="$%d"),
                "gtip_aciklamasi": st.column_config.TextColumn("GTIP", disabled=True),
                "esya_ticari_tanimi": st.column_config.TextColumn("Description", disabled=True),
                "website_str": st.column_config.LinkColumn("Website", disabled=True),
                "phone_str": st.column_config.TextColumn("Phone", disabled=True),
                "notes": st.column_config.TextColumn("Notes", disabled=True),
            }
        )

        if submit_btn:
            if not edited_df.empty and "Select" in edited_df.columns:
                selected_rows = edited_df[edited_df["Select"] == True]
                if "email_str" in selected_rows.columns:
                    st.session_state["selected_emails_targeted"] = selected_rows["email_str"].tolist()
                elif "buyer_name" in selected_rows.columns:
                    st.session_state["selected_emails_targeted"] = selected_rows["buyer_name"].tolist()
                st.toast(f"✅ Selections synced! {len(selected_rows)} leads ready for Campaign.")
                st.rerun()

# ── Action Layer ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### ⚡ Quick Update Status")

if df_all.empty:
    st.caption("No leads available to update.")
else:
    act_col1, act_col2, act_col3 = st.columns([2, 2, 1])
    with act_col1:
        # Build choices list with name + company + email
        lead_choices = []
        for _, row in df_all.iterrows():
            name = row.get("buyer_name", "")
            company = row.get("company_name_english", "")
            email = row.get("email_str", "")
            label = f"{name}"
            if company:
                label += f" @ {company}"
            if email:
                label += f" <{email}>"
            lead_choices.append(label)
        update_lead_choice = st.selectbox("Select Lead", options=lead_choices, key="update_lead_choice")
    with act_col2:
        statuses = LEAD_STATUSES
        update_status_val = st.selectbox("New Status", statuses, key="update_status_val")
    with act_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Apply Status", use_container_width=True, key="apply_status_sync"):
            # Extract buyer name from the choice string
            if update_lead_choice:
                buyer_name = update_lead_choice.split(" @ ")[0].split(" <")[0].strip()
                if update_lead_status(buyer_name, update_status_val):
                    st.toast(f"✅ Synced: {buyer_name} is now {update_status_val.upper()}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Sync failed.")

    # Send selected to Campaign button
    selected_emails = st.session_state.get("selected_emails_targeted", [])
    if selected_emails:
        st.markdown("---")
        sc1, sc2 = st.columns([3, 1])
        with sc1:
            st.success(f"🎯 {len(selected_emails)} lead(s) selected and ready for campaign.")
        with sc2:
            if st.button("🚀 Send to Campaign", use_container_width=True, type="primary", key="btn_go_campaign"):
                st.switch_page("pages/6_Campaign.py")
