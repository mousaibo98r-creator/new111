"""
db.py
─────────────────────────────────────────────────────────────
Antigravity :: Database Operations Layer
Full CRUD for the `mousa` (leads) and `logs` tables via the
official supabase-py client.  Every public function returns
typed Python objects and raises on unrecoverable errors so
callers can react intelligently.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
from uuid import UUID

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger("antigravity.db")

# ── Supabase client (singleton) ───────────────────────────────
_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
        logger.info("Supabase client initialised for: %s", url)
    return _client


# ═══════════════════════════════════════════════════════════════
#  MOUSA (leads)
# ═══════════════════════════════════════════════════════════════

def get_all_leads(status_filter: Optional[str] = None) -> list[dict]:
    """Return all leads, optionally filtered by status."""
    db = get_client()
    query = db.table("mousa").select("*").order("created_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter)
    response = query.execute()
    return response.data or []


def get_lead_by_id(lead_id: str | UUID) -> Optional[dict]:
    """Return a single lead row by UUID, or None if not found."""
    db = get_client()
    response = (
        db.table("mousa")
        .select("*")
        .eq("id", str(lead_id))
        .single()
        .execute()
    )
    return response.data


def get_lead_by_email(email: str) -> Optional[dict]:
    """Return a single lead row by email, or None if not found."""
    db = get_client()
    response = (
        db.table("mousa")
        .select("*")
        .eq("email", email)
        .maybe_single()
        .execute()
    )
    return response.data


def create_lead(name: str, company: str, email: str, status: str = "pending") -> dict:
    """Insert a new lead and return the created row."""
    db = get_client()
    payload = {"name": name, "company": company, "email": email, "status": status}
    response = db.table("mousa").insert(payload).execute()
    lead = response.data[0]
    logger.info("Lead created: %s <%s>", lead["name"], lead["email"])
    return lead


def update_lead_status(lead_id: str | UUID, new_status: str) -> dict:
    """Update a lead's status and return the updated row."""
    db = get_client()
    response = (
        db.table("mousa")
        .update({"status": new_status})
        .eq("id", str(lead_id))
        .execute()
    )
    updated = response.data[0]
    logger.info("Lead %s status → %s", lead_id, new_status)
    return updated


def update_lead(lead_id: str | UUID, fields: dict[str, Any]) -> dict:
    """Partial update of any lead fields; returns the updated row."""
    db = get_client()
    response = (
        db.table("mousa")
        .update(fields)
        .eq("id", str(lead_id))
        .execute()
    )
    return response.data[0]


def delete_lead(lead_id: str | UUID) -> bool:
    """Delete a lead by ID.  Returns True on success."""
    db = get_client()
    db.table("mousa").delete().eq("id", str(lead_id)).execute()
    logger.info("Lead %s deleted.", lead_id)
    return True


def upsert_leads(leads: list[dict]) -> list[dict]:
    """
    Bulk upsert a list of lead dicts.
    Conflict resolution on the `email` column.
    """
    db = get_client()
    response = (
        db.table("mousa")
        .upsert(leads, on_conflict="email")
        .execute()
    )
    logger.info("Upserted %d leads.", len(response.data))
    return response.data


# ═══════════════════════════════════════════════════════════════
#  LOGS
# ═══════════════════════════════════════════════════════════════

def create_log(
    email: str,
    event_type: str,
    lead_id: Optional[str | UUID] = None,
    subject: Optional[str] = None,
    body_preview: Optional[str] = None,
    ai_classification: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Insert a new log entry and return the created row."""
    db = get_client()
    payload: dict[str, Any] = {
        "email":      email,
        "event_type": event_type,
    }
    if lead_id:
        payload["lead_id"] = str(lead_id)
    if subject:
        payload["subject"] = subject
    if body_preview:
        payload["body_preview"] = body_preview[:500]
    if ai_classification:
        payload["ai_classification"] = ai_classification
    if ai_confidence is not None:
        payload["ai_confidence"] = round(float(ai_confidence), 3)
    if metadata:
        payload["metadata"] = metadata

    response = db.table("logs").insert(payload).execute()
    return response.data[0]


def get_logs(
    lead_id: Optional[str | UUID] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Retrieve log entries, optionally filtered by lead or event type."""
    db = get_client()
    query = db.table("logs").select("*").order("created_at", desc=True).limit(limit)
    if lead_id:
        query = query.eq("lead_id", str(lead_id))
    if event_type:
        query = query.eq("event_type", event_type)
    response = query.execute()
    return response.data or []


# ═══════════════════════════════════════════════════════════════
#  ANALYTICS HELPERS
# ═══════════════════════════════════════════════════════════════

def get_status_counts() -> dict[str, int]:
    """Return a dict of {status: count} across all leads."""
    leads = get_all_leads()
    counts: dict[str, int] = {}
    for lead in leads:
        s = lead.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return counts


def get_recent_activity(limit: int = 50) -> list[dict]:
    """Return the most recent log entries joined with lead names."""
    db = get_client()
    response = (
        db.table("logs")
        .select("*, mousa(name, company)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []
