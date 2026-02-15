"""
Data-access helpers — load buyers, filter, search (scavenge @tokens), caching.
"""

from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent.parent
_LOCAL_JSON = _THIS_DIR / "combined_buyers.json"


# ---------------------------------------------------------------------------
# Load buyers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_buyers(table_name: str = "mousa") -> pd.DataFrame:
    """Load from Supabase table, fallback to local JSON."""
    df = _try_supabase(table_name)
    if df is not None and not df.empty:
        return _enrich(df)
    return _load_local_json()


def _try_supabase(table_name: str) -> Optional[pd.DataFrame]:
    try:
        from services.supabase_client import get_client
        client = get_client()
        if client is None:
            return None
        resp = client.table(table_name).select("*").execute()
        if resp.data:
            return pd.DataFrame(resp.data)
    except Exception:
        pass
    return None


@st.cache_data(ttl=600, show_spinner=False)
def _load_local_json() -> pd.DataFrame:
    if not _LOCAL_JSON.exists():
        return pd.DataFrame()
    with open(_LOCAL_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    return _enrich(df)


# ---------------------------------------------------------------------------
# Enrich / derive columns
# ---------------------------------------------------------------------------
def _safe_list_to_str(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    if isinstance(val, str):
        return val
    return ""


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Normalize column names — Supabase may use slightly different names
    col_map = {
        "emails": "email",
        "websites": "website",
        "phones": "phone",
        "addresses": "address",
    }
    for src, dst in col_map.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    # Flatten list columns to strings
    for col in ["email", "website", "phone", "address"]:
        if col in df.columns:
            df[f"{col}_str"] = df[col].apply(_safe_list_to_str)
        else:
            df[f"{col}_str"] = ""

    # Number of exporters
    if "exporters" in df.columns:
        def _count_exporters(val):
            if isinstance(val, dict):
                return len(val)
            if isinstance(val, str):
                try:
                    return len(json.loads(val))
                except Exception:
                    return 0
            return 0
        df["number_of_exporters"] = df["exporters"].apply(_count_exporters)
    else:
        df["number_of_exporters"] = 0

    # Ensure numeric columns
    for col in ["total_usd", "total_invoices"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    # Country helpers
    if "destination_country" not in df.columns:
        df["destination_country"] = ""
    if "country_english" not in df.columns:
        df["country_english"] = df.get("destination_country", "")

    if "buyer_name" not in df.columns and "name" in df.columns:
        df.rename(columns={"name": "buyer_name"}, inplace=True)

    return df


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------
def get_filter_options(df: pd.DataFrame) -> dict:
    options: dict = {}
    if "destination_country" in df.columns:
        options["countries"] = sorted(df["destination_country"].dropna().unique().tolist())
    else:
        options["countries"] = []

    if "exporters" in df.columns:
        all_exp = set()
        for val in df["exporters"]:
            if isinstance(val, dict):
                all_exp.update(val.keys())
            elif isinstance(val, str):
                try:
                    all_exp.update(json.loads(val).keys())
                except Exception:
                    pass
        options["exporters"] = sorted(all_exp)
    else:
        options["exporters"] = []

    # Currencies — not always present
    if "currencies" in df.columns:
        all_cur = set()
        for val in df["currencies"]:
            if isinstance(val, list):
                all_cur.update(val)
            elif isinstance(val, str):
                all_cur.add(val)
        options["currencies"] = sorted(all_cur)
    else:
        options["currencies"] = ["USD"]

    return options


def apply_filters(df: pd.DataFrame, countries: list, exporters: list) -> pd.DataFrame:
    if countries:
        df = df[df["destination_country"].isin(countries)]
    if exporters:
        def _has_exporter(val):
            if isinstance(val, dict):
                return bool(set(val.keys()) & set(exporters))
            if isinstance(val, str):
                try:
                    return bool(set(json.loads(val).keys()) & set(exporters))
                except Exception:
                    return False
            return False
        if "exporters" in df.columns:
            df = df[df["exporters"].apply(_has_exporter)]
    return df


# ---------------------------------------------------------------------------
# Scavenge search — @field:value tokens + free-text
# ---------------------------------------------------------------------------
def search_buyers(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Parse scavenge query with @field:value tokens. Remaining text = free-text search."""
    if not query or not query.strip():
        return df

    query = query.strip()
    tokens = re.findall(r"@(\w+):(\S+)", query)
    free_text = re.sub(r"@\w+:\S+", "", query).strip()

    mask = pd.Series(True, index=df.index)

    field_map = {
        "buyer": "buyer_name",
        "country": "destination_country",
        "destination": "destination_country",
        "email": "email_str",
        "phone": "phone_str",
        "website": "website_str",
        "address": "address_str",
        "exporter": "_exporters_str",
    }

    # Build temp exporters string column for searching
    if "exporters" in df.columns:
        df = df.copy()
        df["_exporters_str"] = df["exporters"].apply(
            lambda v: ", ".join(v.keys()) if isinstance(v, dict) else str(v)
        )

    for field, value in tokens:
        col = field_map.get(field.lower())
        if col and col in df.columns:
            mask &= df[col].astype(str).str.contains(value, case=False, na=False)

    if free_text:
        text_cols = ["buyer_name", "destination_country", "email_str", "phone_str",
                     "website_str", "address_str", "company_name_english"]
        text_mask = pd.Series(False, index=df.index)
        for col in text_cols:
            if col in df.columns:
                text_mask |= df[col].astype(str).str.contains(free_text, case=False, na=False)
        mask &= text_mask

    # Clean up temp column
    if "_exporters_str" in df.columns:
        df = df.drop(columns=["_exporters_str"])

    return df[mask]


# ---------------------------------------------------------------------------
# Deterministic ID for upsert
# ---------------------------------------------------------------------------
def make_buyer_id(buyer_name: str, country: str, dest_country: str) -> str:
    raw = f"{buyer_name}|{country}|{dest_country}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Sync local JSON → Supabase
# ---------------------------------------------------------------------------
def sync_json_to_supabase(table_name: str = "buyers") -> dict:
    """Upsert local JSON data into Supabase table. Returns status dict."""
    from services.supabase_client import get_client
    client = get_client()
    if client is None:
        return {"ok": False, "error": "Supabase client not configured"}

    if not _LOCAL_JSON.exists():
        return {"ok": False, "error": "combined_buyers.json not found"}

    with open(_LOCAL_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for item in data:
        buyer_name = item.get("buyer_name", "")
        country = item.get("destination_country", "")
        dest = item.get("destination_country", "")
        row_id = item.get("id") or make_buyer_id(buyer_name, country, dest)

        row = {
            "id": row_id,
            "buyer_name": buyer_name,
            "destination_country": dest,
            "total_usd": item.get("total_usd", 0),
            "total_invoices": item.get("total_invoices", 0),
            "exporters": json.dumps(item.get("exporters", {}), ensure_ascii=False),
            "emails": json.dumps(item.get("email", []), ensure_ascii=False),
            "websites": json.dumps(item.get("website", []), ensure_ascii=False),
            "phones": json.dumps(item.get("phone", []), ensure_ascii=False),
            "addresses": json.dumps(item.get("address", []), ensure_ascii=False),
            "company_name_english": item.get("company_name_english", ""),
            "country_english": item.get("country_english", ""),
            "country_code": item.get("country_code", ""),
        }
        rows.append(row)

    # Upsert in batches
    batch_size = 500
    total_ok = 0
    errors = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            client.table(table_name).upsert(batch).execute()
            total_ok += len(batch)
        except Exception as e:
            errors.append(str(e))

    return {
        "ok": len(errors) == 0,
        "synced": total_ok,
        "total": len(rows),
        "errors": errors,
    }
