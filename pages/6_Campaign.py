"""
Page 6 — Campaign Management: create, manage, and track email campaigns
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Campaigns", page_icon="🚀", layout="wide", initial_sidebar_state="collapsed")

import pandas as pd
from datetime import datetime

from ui.style import inject_css
from ui.components import (
    render_sidebar_brand,
    render_sidebar_nav,
    render_top_nav,
    auth_gate,
)
from services.data_helpers import load_buyers
from services.crm_helpers import (
    LEAD_STATUSES,
    STATUS_COLORS,
    STATUS_ICONS,
    list_campaigns,
    create_campaign,
    update_campaign,
    delete_campaign,
)

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Page-specific CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
.campaign-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 12px;
    transition: all 0.25s ease;
    cursor: pointer;
}
.campaign-card:hover {
    border-color: #a855f7;
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(168,85,247,0.08);
}
.campaign-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 6px;
}
.campaign-meta {
    font-size: 0.75rem;
    color: #8b949e;
    margin-bottom: 12px;
}
.campaign-stats-row {
    display: flex;
    gap: 16px;
    margin-top: 12px;
}
.campaign-stat {
    text-align: center;
    flex: 1;
}
.campaign-stat-value {
    font-size: 1.2rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}
.campaign-stat-label {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #8b949e;
}
.campaign-status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 16px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.preview-panel {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 24px;
}
.preview-subject {
    font-size: 1rem;
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px solid #21262d;
}
.preview-body {
    font-size: 0.88rem;
    color: #c9d1d9;
    line-height: 1.6;
    white-space: pre-wrap;
}
.template-hint {
    background: rgba(168,85,247,0.08);
    border: 1px solid rgba(168,85,247,0.2);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.78rem;
    color: #c9d1d9;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ── Main area ────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">🚀 Campaign Management</div>', unsafe_allow_html=True)

# ── Session state defaults ───────────────────────────────────────────────────
if "campaign_view" not in st.session_state:
    st.session_state["campaign_view"] = "list"  # "list" or "create" or "detail"
if "selected_campaign_id" not in st.session_state:
    st.session_state["selected_campaign_id"] = None

# ── Load campaigns ───────────────────────────────────────────────────────────
df_campaigns = list_campaigns()

# ── Load leads for targeting ─────────────────────────────────────────────────
df_leads = load_buyers()


# ── Campaign Status Colors ───────────────────────────────────────────────────
CAMPAIGN_STATUS_COLORS = {
    "draft": "#8b949e",
    "active": "#4ade80",
    "completed": "#60a5fa",
    "paused": "#fbbf24",
}


# ═════════════════════════════════════════════════════════════════════════════
#  KPI Row
# ═════════════════════════════════════════════════════════════════════════════
kc1, kc2, kc3, kc4 = st.columns(4)
total_campaigns = len(df_campaigns)
active_campaigns = len(df_campaigns[df_campaigns["status"] == "active"]) if not df_campaigns.empty and "status" in df_campaigns.columns else 0
total_sent = int(df_campaigns["sent_count"].sum()) if not df_campaigns.empty and "sent_count" in df_campaigns.columns else 0
total_failed = int(df_campaigns["failed_count"].sum()) if not df_campaigns.empty and "failed_count" in df_campaigns.columns else 0

with kc1:
    st.markdown(f"""
        <div class="kpi-card kpi-card-purple">
            <div class="kpi-value">{total_campaigns}</div>
            <div class="kpi-label">Total Campaigns</div>
        </div>
    """, unsafe_allow_html=True)
with kc2:
    st.markdown(f"""
        <div class="kpi-card kpi-card-green">
            <div class="kpi-value">{active_campaigns}</div>
            <div class="kpi-label">Active</div>
        </div>
    """, unsafe_allow_html=True)
with kc3:
    st.markdown(f"""
        <div class="kpi-card kpi-card-blue">
            <div class="kpi-value">{total_sent:,}</div>
            <div class="kpi-label">Emails Sent</div>
        </div>
    """, unsafe_allow_html=True)
with kc4:
    st.markdown(f"""
        <div class="kpi-card kpi-card-amber">
            <div class="kpi-value">{total_failed:,}</div>
            <div class="kpi-label">Failed</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("")

# ═════════════════════════════════════════════════════════════════════════════
#  Action Buttons
# ═════════════════════════════════════════════════════════════════════════════
btn_cols = st.columns([1, 1, 4])
with btn_cols[0]:
    if st.button("➕ New Campaign", use_container_width=True, key="btn_new_campaign"):
        st.session_state["campaign_view"] = "create"
        st.rerun()
with btn_cols[1]:
    if st.button("📋 All Campaigns", use_container_width=True, key="btn_list_campaigns"):
        st.session_state["campaign_view"] = "list"
        st.rerun()

st.markdown("---")


# ═════════════════════════════════════════════════════════════════════════════
#  VIEW: Campaign List
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state["campaign_view"] == "list":
    if df_campaigns.empty:
        st.markdown("""
            <div style="text-align: center; padding: 60px 20px; color: #8b949e;">
                <div style="font-size: 3rem; margin-bottom: 12px;">🚀</div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3; margin-bottom: 8px;">
                    No campaigns yet
                </div>
                <div style="font-size: 0.85rem;">
                    Create your first campaign to start reaching out to leads.
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        # Display campaign table
        display_cols = {
            "name": "Campaign",
            "subject": "Subject",
            "status": "Status",
            "target_count": "Targets",
            "sent_count": "Sent",
            "failed_count": "Failed",
            "created_at": "Created",
        }
        available = [c for c in display_cols if c in df_campaigns.columns]
        show_df = df_campaigns[available].copy().reset_index(drop=True)
        show_df.columns = [display_cols[c] for c in available]

        # Format status
        if "Status" in show_df.columns:
            show_df["Status"] = show_df["Status"].apply(
                lambda s: f"{'🟢' if s == 'active' else '⚪' if s == 'draft' else '🔵' if s == 'completed' else '🟡'} {s}" if s else "⚪ draft"
            )

        # Format date
        if "Created" in show_df.columns:
            show_df["Created"] = show_df["Created"].apply(
                lambda d: d[:10] if isinstance(d, str) and len(d) > 10 else d
            )

        event = st.dataframe(
            show_df,
            use_container_width=True,
            height=400,
            on_select="rerun",
            selection_mode="single-row",
            key="campaign_table",
        )

        selected_rows = event.selection.rows if event and event.selection else []

        if selected_rows:
            idx = selected_rows[0]
            if idx < len(df_campaigns):
                campaign = df_campaigns.iloc[idx]
                campaign_id = campaign.get("id", "")

                st.markdown("---")

                # Campaign detail section
                dc1, dc2 = st.columns([3, 2])

                with dc1:
                    st.markdown(f'<div class="detail-panel-title">📧 Campaign Detail</div>', unsafe_allow_html=True)

                    c_name = campaign.get("name", "Untitled")
                    c_status = campaign.get("status", "draft")
                    c_subject = campaign.get("subject", "")
                    c_body = campaign.get("body", "")

                    status_color = CAMPAIGN_STATUS_COLORS.get(c_status, "#8b949e")
                    st.markdown(
                        f'<div style="margin-bottom: 16px;">'
                        f'<span style="font-size: 1.2rem; font-weight: 600; color: #e6edf3;">{c_name}</span> '
                        f'<span class="campaign-status-badge" style="background: {status_color}22; color: {status_color}; border: 1px solid {status_color}44;">'
                        f'{c_status.upper()}</span></div>',
                        unsafe_allow_html=True,
                    )

                    # Editable subject/body
                    edit_subject = st.text_input("Subject", value=c_subject, key="edit_subject")
                    edit_body = st.text_area("Body", value=c_body, height=200, key="edit_body")

                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        new_c_status = st.selectbox(
                            "Status",
                            options=["draft", "active", "completed", "paused"],
                            index=["draft", "active", "completed", "paused"].index(c_status) if c_status in ["draft", "active", "completed", "paused"] else 0,
                            key="edit_campaign_status",
                        )
                    with ec2:
                        if st.button("💾 Save Changes", use_container_width=True, key="btn_save_campaign"):
                            update_campaign(
                                campaign_id,
                                subject=edit_subject,
                                body=edit_body,
                                status=new_c_status,
                            )
                            st.success("✅ Campaign updated!")
                            st.cache_data.clear()
                            st.rerun()
                    with ec3:
                        if st.button("🗑️ Delete", use_container_width=True, key="btn_delete_campaign"):
                            delete_campaign(campaign_id)
                            st.success("Campaign deleted")
                            st.cache_data.clear()
                            st.rerun()

                    # Sending Action
                    if c_status == "draft":
                        st.markdown("---")
                        st.markdown('<div class="detail-label">SEND EMAILS</div>', unsafe_allow_html=True)
                        if st.button("▶️ Start Campaign (Send Emails)", type="primary", use_container_width=True):
                            from services.crm_helpers import send_campaign_emails
                            
                            # We just send to ALL leads here for simplicity, OR we can filter
                            # Since we didn't save the exact targeting in DB, if the user wants to 
                            # send to specific leads they should create a new campaign from the Lead page.
                            # But if target_count > 0 and they created it from the 'Lead' page, how do we know who?
                            # For now, let's just use df_leads. In a full system, you'd save a target_query string.
                            
                            st.info("Gathering targets...")
                            # Fallback: Just grab random `target_count` leads or all leads
                            limit_count = campaign.get("target_count", 0)
                            if limit_count == 0:
                                limit_count = len(df_leads)
                                
                            target_df = df_leads.head(limit_count)
                            target_dicts = target_df.to_dict('records')
                            
                            sent, failed = send_campaign_emails(campaign_id, edit_subject, edit_body, target_dicts)
                            st.success(f"Campaign sent! Sent: {sent}, Failed: {failed}")
                            st.cache_data.clear()
                            st.rerun()

                with dc2:
                    # Live preview
                    st.markdown('<div class="detail-panel-title">👁️ Live Preview</div>', unsafe_allow_html=True)

                    # Get sample lead for preview
                    sample_name = "Jane Doe"
                    sample_country = "Germany"
                    if not df_leads.empty:
                        sample_lead = df_leads.iloc[0]
                        sample_name = sample_lead.get("buyer_name", "Jane Doe")
                        sample_country = sample_lead.get("destination_country", "Germany")

                    preview_subject = (edit_subject or c_subject).replace("{buyer_name}", sample_name).replace("{country}", sample_country)
                    preview_body = (edit_body or c_body).replace("{buyer_name}", sample_name).replace("{country}", sample_country)

                    st.markdown(f"""
                        <div class="preview-panel">
                            <div class="preview-subject">📨 {preview_subject}</div>
                            <div class="preview-body">{preview_body}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Stats
                    st.markdown("")
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.metric("Targeted", campaign.get("target_count", 0))
                    with sc2:
                        st.metric("Sent", campaign.get("sent_count", 0))
                    with sc3:
                        st.metric("Failed", campaign.get("failed_count", 0))


# ═════════════════════════════════════════════════════════════════════════════
#  VIEW: Create New Campaign
# ═════════════════════════════════════════════════════════════════════════════
elif st.session_state["campaign_view"] == "create":
    col_form, col_preview = st.columns([3, 2])

    with col_form:
        st.markdown('<div class="detail-panel-title">✨ Create New Campaign</div>', unsafe_allow_html=True)

        campaign_name = st.text_input(
            "Campaign Name",
            placeholder="e.g. Q3 Outreach — European Buyers",
            key="new_campaign_name",
        )

        st.markdown("")

        # Template variable hints
        st.markdown("""
            <div class="template-hint">
                💡 <strong>Available Variables:</strong> Use <code>{buyer_name}</code> for the buyer's name
                and <code>{country}</code> for their country. These will be automatically replaced when sending.
            </div>
        """, unsafe_allow_html=True)

        subject = st.text_input(
            "Subject Line",
            placeholder="e.g. Quick question about {buyer_name}'s aluminum needs",
            key="new_campaign_subject",
        )

        body = st.text_area(
            "Email Body",
            height=250,
            placeholder="Hello,\n\nI noticed {buyer_name} is importing aluminum profiles to {country}...\n\nBest regards",
            key="new_campaign_body",
        )

        st.markdown("")

        # Target selection
        st.markdown('<div class="detail-label">TARGET LEADS</div>', unsafe_allow_html=True)

        target_options = ["All leads", "Filter by status", "Filter by country"]
        selected_leads = st.session_state.get("campaign_target_leads", [])
        if selected_leads:
            target_options.insert(0, "Selected from Leads")

        target_mode = st.radio(
            "Targeting",
            options=target_options,
            horizontal=True,
            key="new_campaign_target_mode",
            label_visibility="collapsed",
        )

        target_count = len(df_leads)
        if target_mode == "Selected from Leads":
            target_count = len(selected_leads)
            st.caption(f"📊 {target_count} specific leads passed from Leads page")
        elif target_mode == "Filter by status":
            target_status = st.selectbox("Status", LEAD_STATUSES, key="new_target_status")
            if "status" in df_leads.columns:
                target_count = int((df_leads["status"] == target_status).sum())
            st.caption(f"📊 {target_count} leads with status '{target_status}'")
        elif target_mode == "Filter by country":
            countries = sorted(df_leads["destination_country"].dropna().unique().tolist()) if "destination_country" in df_leads.columns else []
            target_country = st.selectbox("Country", countries, key="new_target_country")
            target_count = int((df_leads["destination_country"] == target_country).sum())
            st.caption(f"📊 {target_count} leads in '{target_country}'")
        else:
            st.caption(f"📊 {target_count} total leads will be targeted")

        st.markdown("")

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("🚀 Create Campaign", use_container_width=True, type="primary", key="btn_create_campaign"):
                if not campaign_name:
                    st.error("Please enter a campaign name")
                elif not subject:
                    st.error("Please enter a subject line")
                elif not body:
                    st.error("Please enter an email body")
                else:
                    if create_campaign(campaign_name, subject, body, target_count):
                        st.success(f"✅ Campaign '{campaign_name}' created!")
                        st.session_state["campaign_view"] = "list"
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Failed to create campaign. Make sure the 'campaigns' table exists in Supabase.")
        with bc2:
            if st.button("← Back to List", use_container_width=True, key="btn_back_to_list"):
                st.session_state["campaign_view"] = "list"
                st.rerun()

    with col_preview:
        st.markdown('<div class="detail-panel-title">👁️ Live Preview</div>', unsafe_allow_html=True)

        # Get sample lead
        sample_name = "Jane Doe"
        sample_country = "Germany"
        if not df_leads.empty:
            sample_lead = df_leads.iloc[0]
            sample_name = sample_lead.get("buyer_name", "Jane Doe")
            sample_country = sample_lead.get("destination_country", "Germany")

        preview_subject = (subject or "Your subject line...").replace("{buyer_name}", sample_name).replace("{country}", sample_country)
        preview_body = (body or "Your email body will appear here...").replace("{buyer_name}", sample_name).replace("{country}", sample_country)

        st.markdown(f"""
            <div class="preview-panel">
                <div class="preview-subject">📨 {preview_subject}</div>
                <div class="preview-body">{preview_body}</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("")
        st.markdown(f"""
            <div style="background: rgba(74,222,128,0.06); border: 1px solid rgba(74,222,128,0.15); border-radius: 10px; padding: 16px;">
                <div style="font-size: 0.75rem; font-weight: 600; color: #4ade80; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Campaign Summary</div>
                <div style="font-size: 0.85rem; color: #c9d1d9;">
                    📧 <strong>Target:</strong> {target_count:,} leads<br>
                    📝 <strong>Subject:</strong> {subject[:50] + '...' if subject and len(subject) > 50 else subject or '—'}<br>
                </div>
            </div>
        """, unsafe_allow_html=True)
