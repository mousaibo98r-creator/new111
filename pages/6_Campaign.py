"""
Page 6 — Campaign Dispatch Control
Matches CRM2 dashboard Campaign tab exactly.
Template editor, deliverability advisor, lead targeting, Resend dispatch, live preview.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Campaign", page_icon="🚀", layout="wide", initial_sidebar_state="collapsed")

import pandas as pd
import json

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
    update_lead_status,
)

auth_gate()
inject_css()
render_top_nav()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Page CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.campaign-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 16px;
}
.campaign-card:hover { border-color: #a855f7; }
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
</style>
""", unsafe_allow_html=True)

# ── Main area ────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">🚀 Campaign Dispatch Control</div>', unsafe_allow_html=True)

# ── Load leads ───────────────────────────────────────────────────────────────
df_leads = load_buyers()

# Ensure columns exist
if not df_leads.empty:
    if "status" not in df_leads.columns:
        df_leads["status"] = "new"
    else:
        df_leads["status"] = df_leads["status"].fillna("new")
    if "company_name_english" not in df_leads.columns:
        df_leads["company_name_english"] = ""
    else:
        df_leads["company_name_english"] = df_leads["company_name_english"].fillna("")

# ── Multiple Templates Management ─────────────────────────────────────────────
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "campaign_template.json")

def load_templates():
    default_templates = {
        "Standard Cold Outreach": {
            "subject": "Quick question for {buyer_name}",
            "body": "Hi {buyer_name},\n\nI was looking at your company and..."
        },
        "High-Deliverability Conversational": {
            "subject": "quick question",
            "body": "Hi {buyer_name},\n\nI noticed that your company is active in aluminum profiles. Are you currently importing or sourcing profiles from Turkey?\n\nBest,\nAbdullah"
        }
    }
    
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Check if it is the old single-template format
                    if "subject" in data and "body" in data:
                        return {"Saved Template": data}
                    return data
        except Exception:
            pass
    return default_templates

def save_template(name, subject, body):
    try:
        templates = load_templates()
        templates[name] = {"subject": subject, "body": body}
        with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def delete_template(name):
    try:
        templates = load_templates()
        if name in templates:
            del templates[name]
            with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
                json.dump(templates, f, indent=2, ensure_ascii=False)
            return True
    except Exception:
        pass
    return False

templates = load_templates()
template_names = list(templates.keys())

if "selected_template_name" not in st.session_state:
    st.session_state["selected_template_name"] = template_names[0] if template_names else "Standard Cold Outreach"

active_tpl = templates.get(st.session_state["selected_template_name"], templates[template_names[0]] if template_names else {"subject": "", "body": ""})

# Canonical Streamlit key binding
if st.session_state.get("camp_subject") is None:
    st.session_state["camp_subject"] = active_tpl.get("subject", "")
if st.session_state.get("camp_body") is None:
    st.session_state["camp_body"] = active_tpl.get("body", "")

# ── Get Resend config from secrets ───────────────────────────────────────────
def _get_secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)

RESEND_API_KEY = _get_secret("RESEND_API_KEY", "")
SENDER_EMAIL = _get_secret("SENDER_EMAIL", "info@emiroglual.net")
SENDER_NAME = _get_secret("SENDER_NAME", "Abdullah Şeyh")
REPLY_TO_EMAIL = _get_secret("REPLY_TO_EMAIL", "")

# ── Layout: Form left (60%), Preview right (40%) ────────────────────────────
col_form, col_preview = st.columns([3, 2])

with col_form:
    campaign_title = st.text_input("Campaign Title", "Standard Cold Outreach", key="camp_title")
    from_alias = st.text_input("From Display Name Alias", SENDER_NAME, key="camp_from")

    # Template selection bar (the requested template bar)
    selected_template = st.selectbox(
        "📂 Select Saved Template",
        options=template_names,
        index=template_names.index(st.session_state["selected_template_name"]) if st.session_state["selected_template_name"] in template_names else 0,
        key="select_template_bar"
    )
    
    if selected_template != st.session_state["selected_template_name"]:
        st.session_state["selected_template_name"] = selected_template
        st.session_state["camp_subject"] = templates[selected_template]["subject"]
        st.session_state["camp_body"] = templates[selected_template]["body"]
        st.rerun()

    camp_subject = st.text_input("Subject Line", key="camp_subject")
    camp_body = st.text_area("Email Body", height=180, key="camp_body")

    camp_plain = st.checkbox("✉️ Send as Plain Text (Helps avoid Promotions folder)", value=True, key="camp_plain_text")
    camp_headers = st.checkbox("Include List-Unsubscribe Headers (Uncheck for 1-to-1 deliverability)", value=False, key="camp_include_unsubscribe_headers")
    camp_no_delay = st.checkbox("⚡ Send all at once (no delay between emails)", value=False, key="camp_no_delay")

    # ── Deliverability Advisor ────────────────────────────────────────────
    st.markdown("#### 🛡️ Deliverability Advisor")
    score = 100
    warnings = []

    if camp_subject.isupper():
        score -= 20
        warnings.append("Subject is in ALL CAPS. (SUBJ_ALL_CAPS spam score penalty)")
    if len(camp_subject) > 60:
        score -= 10
        warnings.append("Subject is too long. Conversational subjects are usually short.")

    promo_words = ["cooperation", "established in", "manufacturer", "customs records", "supplying", "valued customer", "high-quality", "offer"]
    for w in promo_words:
        if w in camp_body.lower() or w in camp_subject.lower():
            score -= 15
            warnings.append(f"Contains sales/marketing keyword: '{w}'")

    link_cnt = camp_body.count("http") + camp_body.count("www.") + camp_body.count("@")
    if link_cnt > 2:
        score -= 15
        warnings.append("Multiple links/emails in body. Large signatures look like commercial advertisements.")

    if camp_headers:
        score -= 10
        warnings.append("List-Unsubscribe headers are included. (Gmail classifies headers in one-to-one mail as bulk list mail).")

    if score >= 80:
        rating = "🟢 Conversational (High chance of Primary Inbox)"
        color = "#7EE8A2"
    elif score >= 50:
        rating = "🟡 Moderate (May land in Promotions)"
        color = "#F0D460"
    else:
        rating = "🔴 Promotional (Highly likely to land in Promotions or Spam)"
        color = "#F07070"

    st.markdown(f"""
        <div style='background:#13131A; padding:14px; border-radius:10px; border:1px solid #1E1E2E; margin-bottom:15px;'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;'>
                <span style='font-size:0.85rem; font-weight:600;'>Placement Rating:</span>
                <span style='color:{color}; font-weight:bold; font-size:0.85rem;'>{rating}</span>
            </div>
            <div style='font-size:0.75rem; color:#7070A0;'>
                <b>Spam Check Score:</b> {score}/100
            </div>
        </div>
    """, unsafe_allow_html=True)

    if warnings:
        for w in warnings:
            st.caption(f"⚠️ {w}")

    # ── Target Selection ──────────────────────────────────────────────────
    if df_leads.empty:
        st.caption("No leads to display.")
        target_emails = []
    else:
        selected_emails = st.session_state.get("selected_emails_targeted", [])
        num_picked = len(selected_emails)

        if num_picked > 0:
            target_mode = st.radio(
                "Targeting Options",
                [f"🎯 Send directly to all {num_picked} checked lead(s)", "🔍 Custom filter / edit list manually"],
                index=0,
                key="camp_target_mode"
            )
        else:
            target_mode = "🔍 Custom filter / edit list manually"
            st.info("💡 Go to the **Leads** tab and check the boxes (`✓`) next to the leads you want to target.")

        if target_mode.startswith("🎯 Send directly"):
            target_emails = selected_emails
            st.success(f"Selected: **{num_picked} checked lead(s)** will be targeted in this campaign.")
        else:
            lead_choices = []
            default_selected = []
            for _, row in df_leads.iterrows():
                email = row.get("email_str", "")
                buyer_name = row.get("buyer_name", "")
                company = row.get("company_name_english", "")
                is_picked = email in selected_emails or buyer_name in selected_emails
                prefix = "✅ [PICKED] " if is_picked else ""
                opt = f"{prefix}{buyer_name} @ {company} <{email}>"
                lead_choices.append(opt)
                if is_picked:
                    default_selected.append(opt)

            selected_leads = st.multiselect(
                "Filter Campaign Targets",
                options=lead_choices,
                default=default_selected,
                key="camp_selected"
            )
            target_emails = [sel.split("<")[-1].replace(">", "").strip() for sel in selected_leads]

    # Template actions (Save / Delete)
    st.markdown("---")
    st.markdown("#### 💾 Manage Templates")
    t_save_name = st.text_input("Save Template As...", value=st.session_state["selected_template_name"])
    
    ta_col1, ta_col2 = st.columns(2)
    with ta_col1:
        if st.button("💾 Save Template", use_container_width=True, key="camp_save_template_btn"):
            if not camp_subject.strip() or not camp_body.strip() or not t_save_name.strip():
                st.toast("❌ Template Name, Subject, and Body are required.", icon="⚠️")
            else:
                if save_template(t_save_name.strip(), camp_subject, camp_body):
                    st.toast("✅ Template saved!", icon="💾")
                    st.session_state["selected_template_name"] = t_save_name.strip()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to save template.")
    with ta_col2:
        if st.button("🗑️ Delete Template", use_container_width=True, key="camp_delete_template_btn"):
            if t_save_name in templates:
                # Prevent deleting all templates to keep it clean
                if len(templates) <= 1:
                    st.warning("Cannot delete the last remaining template.")
                elif delete_template(t_save_name):
                    st.toast("🗑️ Template deleted!", icon="info")
                    new_templates = load_templates()
                    st.session_state["selected_template_name"] = list(new_templates.keys())[0] if new_templates else ""
                    st.session_state["camp_subject"] = ""
                    st.session_state["camp_body"] = ""
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Failed to delete.")
            else:
                st.warning("Template not found.")

    st.markdown("---")
    dispatch_btn = st.button("🚀 Dispatch Campaign", use_container_width=True, type="primary", key="camp_dispatch_btn")

    # ── Dispatch Campaign (Actual Sending via Resend API) ─────────────────
    if dispatch_btn:
        if not target_emails:
            st.toast("❌ Please select at least one target lead.", icon="⚠️")
        elif not camp_subject or not camp_body:
            st.toast("❌ Subject Line and Email Body are required.", icon="⚠️")
        elif not RESEND_API_KEY:
            st.error("❌ Missing RESEND_API_KEY in .streamlit/secrets.toml. Add it to send emails.")
        else:
            import requests
            import time
            import random

            progress_bar = st.progress(0.0)
            status_box = st.empty()

            total_emails = len(target_emails)
            success_count = 0
            fail_count = 0

            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            }

            for email_idx, email in enumerate(target_emails):
                # Find the lead row
                lead_row = None
                if "email_str" in df_leads.columns:
                    match = df_leads[df_leads["email_str"] == email]
                    if not match.empty:
                        lead_row = match.iloc[0]

                if lead_row is None:
                    # Try matching by buyer_name (if selected_emails contains names)
                    if "buyer_name" in df_leads.columns:
                        match = df_leads[df_leads["buyer_name"] == email]
                        if not match.empty:
                            lead_row = match.iloc[0]
                            # Get actual email
                            email = lead_row.get("email_str", "")

                # Clean and split email address (handles JSON arrays, semicolons, brackets, quotes)
                clean_email_list = []
                if email:
                    sanitized_email = str(email).replace("[", "").replace("]", "").replace("\"", "").replace("'", "").replace(";", ",")
                    for part in sanitized_email.split(","):
                        clean_part = part.strip()
                        if clean_part and "@" in clean_part:
                            clean_email_list.append(clean_part)

                if lead_row is None or not clean_email_list:
                    fail_count += 1
                    continue

                buyer_name = lead_row.get("buyer_name", "")
                company = lead_row.get("company_name_english", "")
                status = lead_row.get("status", "new")

                # SAFETY: Skip leads that already replied, bounced, or unsubscribed
                skip_statuses = {"replied", "interested", "in_conversation",
                                 "not_interested", "unsubscribed", "bounced"}
                if status in skip_statuses:
                    status_box.markdown(f"⏭️ Skipping {email} (status: {status})")
                    continue

                # Inject variables
                injected_subject = camp_subject.replace("{buyer_name}", buyer_name).replace("{company}", company).replace("{country}", str(lead_row.get("destination_country", "")))
                injected_body = camp_body.replace("{buyer_name}", buyer_name).replace("{company}", company).replace("{country}", str(lead_row.get("destination_country", "")))

                # Build email payload
                email_params = {
                    "from": f"{from_alias} <{SENDER_EMAIL}>",
                    "to": clean_email_list,
                    "subject": injected_subject,
                }


                if camp_plain:
                    email_params["text"] = injected_body
                else:
                    html_paragraphs = [f"<p>{p.strip()}</p>" for p in injected_body.split("\n\n") if p.strip()]
                    html_body = f"<div style='font-family: sans-serif; font-size: 14px; color: #222; line-height: 1.5;'>{''.join(html_paragraphs)}</div>"
                    email_params["html"] = html_body
                    email_params["text"] = injected_body

                if REPLY_TO_EMAIL:
                    email_params["reply_to"] = REPLY_TO_EMAIL



                if camp_headers:
                    email_params["headers"] = {
                        "List-Unsubscribe": f"<mailto:{SENDER_EMAIL}?subject=unsubscribe>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
                    }

                try:
                    r = requests.post(url, headers=headers, json=email_params)
                    if r.status_code in [200, 201]:
                        success_count += 1
                        update_lead_status(buyer_name, "contacted")
                        status_box.markdown(f"✅ Sent to {buyer_name} <{email}>")
                    else:
                        fail_count += 1
                        update_lead_status(buyer_name, "bounced")
                        status_box.markdown(f"❌ Failed: {buyer_name} — {r.text[:100]}")
                except Exception as e:
                    fail_count += 1
                    status_box.markdown(f"❌ Error: {buyer_name} — {str(e)[:100]}")

                # Update progress bar
                progress_bar.progress((email_idx + 1) / total_emails)

                # Randomized delay between emails
                if not camp_no_delay and email_idx < total_emails - 1:
                    jitter = random.randint(-15, 15)
                    wait_time = max(10, 60 + jitter)
                    status_box.markdown(f"⏳ Waiting {wait_time}s before next email... ({success_count} sent, {fail_count} failed)")
                    time.sleep(wait_time)

            status_box.empty()
            st.success(f"✅ Campaign complete: {success_count} sent successfully, {fail_count} failed.")
            st.cache_data.clear()
            st.rerun()

with col_preview:
    st.markdown("#### 👁️ Template Live Preview")

    # Preview template with first selected lead or mock fallback
    pv_name = "Jane Doe"
    pv_company = "ACME Corp"
    pv_email = "jane@acme.com"
    pv_country = "Germany"

    if target_emails and not df_leads.empty:
        if "email_str" in df_leads.columns:
            first_lead_row = df_leads[df_leads["email_str"] == target_emails[0]]
        else:
            first_lead_row = pd.DataFrame()
        if not first_lead_row.empty:
            pv_name = first_lead_row.iloc[0].get("buyer_name", pv_name)
            pv_company = first_lead_row.iloc[0].get("company_name_english", pv_company)
            pv_email = first_lead_row.iloc[0].get("email_str", pv_email)
            pv_country = first_lead_row.iloc[0].get("destination_country", pv_country)

    pv_sub = camp_subject.replace("{buyer_name}", pv_name).replace("{company}", pv_company).replace("{country}", str(pv_country))
    pv_bod = camp_body.replace("{buyer_name}", pv_name).replace("{company}", pv_company).replace("{country}", str(pv_country))

    st.markdown(f"""
        <div class='preview-panel'>
            <p style='color:#7070A0; font-size:0.75rem; margin-bottom:4px;'>TO: {pv_name} &lt;{pv_email}&gt;</p>
            <div class='preview-subject'>Subject: {pv_sub}</div>
            <div class='preview-body'>{pv_bod}</div>
        </div>
    """, unsafe_allow_html=True)

    # Campaign summary card
    st.markdown("")
    target_count = len(target_emails) if target_emails else 0
    st.markdown(f"""
        <div style="background: rgba(74,222,128,0.06); border: 1px solid rgba(74,222,128,0.15); border-radius: 10px; padding: 16px; margin-top: 16px;">
            <div style="font-size: 0.75rem; font-weight: 600; color: #4ade80; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Campaign Summary</div>
            <div style="font-size: 0.85rem; color: #c9d1d9;">
                📧 <strong>Target:</strong> {target_count:,} leads<br>
                📝 <strong>Subject:</strong> {camp_subject[:50] + '...' if camp_subject and len(camp_subject) > 50 else camp_subject or '—'}<br>
                ✉️ <strong>Mode:</strong> {'Plain Text' if camp_plain else 'HTML'}<br>
                🔑 <strong>Resend:</strong> {'🟢 Key Configured' if RESEND_API_KEY else '🔴 Missing Key'}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # System Health
    st.markdown("")
    st.markdown(f"""
        <div style='font-size: 0.8rem; background: #13131A; padding: 12px; border-radius: 8px; border:1px solid #1E1E2E; margin-top: 16px;'>
            <b>Resend:</b> {'🟢 Active' if RESEND_API_KEY else '🔴 Missing Key'}<br>
            <b>Sender:</b> {SENDER_EMAIL}<br>
            <b>Reply-To:</b> {REPLY_TO_EMAIL or 'Not set'}
        </div>
    """, unsafe_allow_html=True)
