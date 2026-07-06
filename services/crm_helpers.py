"""
CRM helper functions — Lead management & Campaign CRUD using the main Supabase client.
"""

from __future__ import annotations
import json
from typing import Optional

import pandas as pd
import streamlit as st

from services.supabase_client import get_client


# ── Lead Status Constants ────────────────────────────────────────────────────
LEAD_STATUSES = [
    "new", "contacted", "replied", "interested",
    "not_interested", "bounced", "unsubscribed",
]

STATUS_COLORS = {
    "new": "#8b949e",
    "contacted": "#60a5fa",
    "replied": "#c084fc",
    "interested": "#4ade80",
    "not_interested": "#f87171",
    "bounced": "#fb923c",
    "unsubscribed": "#6b7280",
}

STATUS_ICONS = {
    "new": "⚪",
    "contacted": "🔵",
    "replied": "🟣",
    "interested": "🟢",
    "not_interested": "🔴",
    "bounced": "🟠",
    "unsubscribed": "⚫",
}


# ── Load Leads (cached) ─────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def load_leads(table_name: str = "mousa") -> pd.DataFrame:
    """Load ALL leads from Supabase with pagination."""
    try:
        client = get_client()
        if client is None:
            return pd.DataFrame()

        all_rows = []
        page_size = 1000
        offset = 0

        while True:
            resp = client.table(table_name).select("*").range(
                offset, offset + page_size - 1
            ).execute()
            if not resp.data:
                break
            all_rows.extend(resp.data)
            if len(resp.data) < page_size:
                break
            offset += page_size

        if all_rows:
            df = pd.DataFrame(all_rows)
            # Ensure status column exists with default
            if "status" not in df.columns:
                df["status"] = "new"
            else:
                df["status"] = df["status"].fillna("new")
            # Ensure notes column
            if "notes" not in df.columns:
                df["notes"] = ""
            else:
                df["notes"] = df["notes"].fillna("")
            return df
    except Exception:
        pass
    return pd.DataFrame()


# ── Lead Stats ───────────────────────────────────────────────────────────────
def get_lead_stats(df: pd.DataFrame) -> dict:
    """Calculate lead stats from dataframe."""
    stats = {"total": len(df)}
    if "status" in df.columns:
        for status in LEAD_STATUSES:
            stats[status] = int((df["status"] == status).sum())
    else:
        stats["new"] = len(df)
        for status in LEAD_STATUSES[1:]:
            stats[status] = 0
    return stats


# ── Update Lead Status ───────────────────────────────────────────────────────
def update_lead_status(buyer_name: str, new_status: str) -> bool:
    """Update the status of a lead by buyer_name."""
    try:
        client = get_client()
        if client is None:
            return False
        resp = client.table("mousa").update(
            {"status": new_status}
        ).eq("buyer_name", buyer_name).execute()
        if resp.data:
            st.cache_data.clear()
            return True
    except Exception:
        pass
    return False


# ── Bulk Update Status ───────────────────────────────────────────────────────
def bulk_update_status(buyer_names: list, new_status: str) -> int:
    """Bulk update status for multiple leads. Returns count of updated rows."""
    client = get_client()
    if client is None:
        return 0
    updated = 0
    for name in buyer_names:
        try:
            resp = client.table("mousa").update(
                {"status": new_status}
            ).eq("buyer_name", name).execute()
            if resp.data:
                updated += 1
        except Exception:
            continue
    if updated:
        st.cache_data.clear()
    return updated


# ── Update Lead Notes ────────────────────────────────────────────────────────
def update_lead_notes(buyer_name: str, notes: str) -> bool:
    """Update notes for a lead."""
    try:
        client = get_client()
        if client is None:
            return False
        resp = client.table("mousa").update(
            {"notes": notes}
        ).eq("buyer_name", buyer_name).execute()
        if resp.data:
            st.cache_data.clear()
            return True
    except Exception:
        pass
    return False


# ── Campaign CRUD ────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def list_campaigns() -> pd.DataFrame:
    """Load all campaigns from the campaigns table."""
    try:
        client = get_client()
        if client is None:
            return pd.DataFrame()
        resp = client.table("campaigns").select("*").order(
            "created_at", desc=True
        ).execute()
        if resp.data:
            return pd.DataFrame(resp.data)
    except Exception:
        pass
    return pd.DataFrame()


def create_campaign(name: str, subject: str, body: str, target_count: int = 0) -> bool:
    """Create a new campaign."""
    try:
        client = get_client()
        if client is None:
            return False
        resp = client.table("campaigns").insert({
            "name": name,
            "subject": subject,
            "body": body,
            "status": "draft",
            "target_count": target_count,
            "sent_count": 0,
            "failed_count": 0,
        }).execute()
        if resp.data:
            st.cache_data.clear()
            return True
    except Exception:
        pass
    return False


def update_campaign(campaign_id: str, **fields) -> bool:
    """Update campaign fields."""
    try:
        client = get_client()
        if client is None:
            return False
        resp = client.table("campaigns").update(
            fields
        ).eq("id", campaign_id).execute()
        if resp.data:
            st.cache_data.clear()
            return True
    except Exception:
        pass
    return False


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign."""
    try:
        client = get_client()
        if client is None:
            return False
        client.table("campaigns").delete().eq("id", campaign_id).execute()
        st.cache_data.clear()
        return True
    except Exception:
        pass
    return False


# ── Add New Lead ─────────────────────────────────────────────────────────────
def add_lead(buyer_name: str, email: str, country: str, status: str = "new", company: str = "") -> bool:
    """Manually add a new lead to the mousa table."""
    try:
        client = get_client()
        if client is None:
            return False
        
        payload = {
            "buyer_name": buyer_name,
            "email": [email] if email else [],
            "destination_country": country,
            "status": status,
            "total_usd": 0,
            "total_invoices": 0,
        }
        if company:
            payload["company_name_english"] = company
        
        resp = client.table("mousa").insert(payload).execute()
        
        if resp.data:
            st.cache_data.clear()
            return True
    except Exception as e:
        print("Error adding lead:", e)
        pass
    return False


# ── Send Emails via Resend ───────────────────────────────────────────────────
def send_campaign_emails(campaign_id: str, subject_template: str, body_template: str, leads: list[dict]) -> tuple[int, int]:
    """
    Sends emails to the provided leads using the Resend API.
    Replaces {buyer_name} and {country} in subject and body.
    Updates the campaign counts and lead statuses in Supabase.
    Returns (sent_count, failed_count)
    """
    import requests
    
    # Try to get Resend key from secrets, then from env (for local)
    try:
        resend_api_key = st.secrets.get("RESEND_API_KEY", "")
        sender_email = st.secrets.get("SENDER_EMAIL", "info@emiroglual.net")
        reply_to_email = st.secrets.get("REPLY_TO_EMAIL", "Abdullah@emiroglual.com")
    except Exception:
        import os
        resend_api_key = os.environ.get("RESEND_API_KEY", "")
        sender_email = os.environ.get("SENDER_EMAIL", "info@emiroglual.net")
        reply_to_email = os.environ.get("REPLY_TO_EMAIL", "Abdullah@emiroglual.com")

    if not resend_api_key:
        st.error("Missing RESEND_API_KEY in .streamlit/secrets.toml")
        return 0, 0

    sent_count = 0
    failed_count = 0

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json"
    }

    # Setup progress bar
    progress_text = "Sending emails... Please wait."
    my_bar = st.progress(0, text=progress_text)
    total_leads = len(leads)

    for i, lead in enumerate(leads):
        email = lead.get("email_str") or lead.get("email")
        if not email:
            failed_count += 1
            continue
            
        buyer_name = lead.get("buyer_name", "")
        country = lead.get("destination_country", "")

        # Personalize
        subject = subject_template.replace("{buyer_name}", buyer_name).replace("{country}", country)
        body = body_template.replace("{buyer_name}", buyer_name).replace("{country}", country)

        payload = {
            "from": sender_email,
            "to": [email],
            "subject": subject,
            "text": body,
        }
        if reply_to_email:
            payload["reply_to"] = reply_to_email.strip()
            payload["replyTo"] = reply_to_email.strip()

        try:
            r = requests.post(url, headers=headers, json=payload)
            if r.status_code in [200, 201]:
                sent_count += 1
                # Update lead status
                update_lead_status(buyer_name, "contacted")
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

        # Update progress bar
        progress = (i + 1) / total_leads
        my_bar.progress(progress, text=f"Sent {sent_count} / {total_leads} emails")

    my_bar.empty()

    # Update campaign stats in DB
    try:
        client = get_client()
        if client:
            client.table("campaigns").update({
                "sent_count": sent_count,
                "failed_count": failed_count,
                "status": "completed"
            }).eq("id", campaign_id).execute()
    except Exception:
        pass

    return sent_count, failed_count
