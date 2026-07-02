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
