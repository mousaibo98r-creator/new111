"""
Data-access helpers — load buyers, filter, search (scavenge @tokens), caching.
"""

from __future__ import annotations
import json
import os
import re
from typing import Optional

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Load buyers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_buyers(table_name: str = "mousa") -> pd.DataFrame:
    """Load ALL buyer data from Supabase (paginated past 1000 limit)."""
    try:
        from services.supabase_client import get_client
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
                break  # last page
            offset += page_size

        if all_rows:
            return _enrich(pd.DataFrame(all_rows))
    except Exception:
        pass
    return pd.DataFrame()


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
# Auto-merge duplicate buyers by overlapping email or phone
# ---------------------------------------------------------------------------
def _to_list(val) -> list:
    """Convert a value to a list of strings."""
    if isinstance(val, list):
        return [str(v).strip().lower() for v in val if v]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(v).strip().lower() for v in parsed if v]
        except Exception:
            if val.strip():
                return [v.strip().lower() for v in val.split(",") if v.strip()]
    return []


def _to_dict(val) -> dict:
    """Convert exporters value to a dict."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            d = json.loads(val)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _unique_list(vals: list) -> list:
    """Deduplicate a list preserving order (case-insensitive for strings)."""
    seen = set()
    out = []
    for v in vals:
        key = str(v).strip().lower() if isinstance(v, str) else v
        if key and key not in seen:
            seen.add(key)
            # Keep the original-case version
            out.append(v if not isinstance(v, str) else v.strip())
    return out


def merge_duplicate_buyers(table_name: str = "mousa", callback=None) -> dict:
    """
    Find buyers sharing at least one email or phone → merge them.
    Returns {"groups_found": N, "rows_deleted": M, "rows_updated": K}.
    Uses Union-Find to handle transitive overlaps (A↔B, B↔C → merge A+B+C).
    """
    from services.supabase_client import get_client
    client = get_client()
    if client is None:
        return {"error": "No Supabase connection"}

    if callback:
        callback("📥 Loading all buyers…")

    # Load all rows
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = client.table(table_name).select("*").range(offset, offset + page_size - 1).execute()
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size

    if len(all_rows) < 2:
        return {"groups_found": 0, "rows_deleted": 0, "rows_updated": 0}

    if callback:
        callback(f"📊 Loaded {len(all_rows)} buyers. Building contact index…")

    # --- Union-Find ---
    parent = list(range(len(all_rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Build index: email → row indices, phone → row indices
    email_index: dict[str, list[int]] = {}
    phone_index: dict[str, list[int]] = {}

    for i, row in enumerate(all_rows):
        for e in _to_list(row.get("email", row.get("emails", []))):
            if e:
                email_index.setdefault(e, []).append(i)
        for p in _to_list(row.get("phone", row.get("phones", []))):
            # Normalize: strip non-digits for comparison
            digits = re.sub(r'\D', '', p)
            if len(digits) >= 6:  # skip junk
                phone_index.setdefault(digits, []).append(i)

    # Union rows that share an email or phone
    for indices in email_index.values():
        for j in range(1, len(indices)):
            union(indices[0], indices[j])

    for indices in phone_index.values():
        for j in range(1, len(indices)):
            union(indices[0], indices[j])

    # Collect groups (only groups with 2+ members)
    groups: dict[int, list[int]] = {}
    for i in range(len(all_rows)):
        root = find(i)
        groups.setdefault(root, []).append(i)

    merge_groups = {k: v for k, v in groups.items() if len(v) > 1}

    if not merge_groups:
        if callback:
            callback("✅ No duplicates found!")
        return {"groups_found": 0, "rows_deleted": 0, "rows_updated": 0}

    if callback:
        callback(f"🔗 Found {len(merge_groups)} groups of duplicates. Merging…")

    rows_deleted = 0
    rows_updated = 0

    for group_indices in merge_groups.values():
        group_rows = [all_rows[i] for i in group_indices]

        # Pick the "primary" row: the one with the highest total_usd
        primary = max(group_rows, key=lambda r: float(r.get("total_usd", 0) or 0))
        others = [r for r in group_rows if r.get("id") != primary.get("id")]

        # --- Merge fields ---
        # Sum numeric fields
        merged_usd = sum(float(r.get("total_usd", 0) or 0) for r in group_rows)
        merged_invoices = sum(int(r.get("total_invoices", 0) or 0) for r in group_rows)

        # Union list fields (deduplicated)
        list_fields = ["email", "emails", "phone", "phones",
                       "website", "websites", "address", "addresses"]
        merged_lists = {}
        for field in list_fields:
            all_vals = []
            for r in group_rows:
                val = r.get(field)
                if val is not None:
                    if isinstance(val, list):
                        all_vals.extend(val)
                    elif isinstance(val, str):
                        try:
                            parsed = json.loads(val)
                            if isinstance(parsed, list):
                                all_vals.extend(parsed)
                            else:
                                all_vals.append(val)
                        except Exception:
                            all_vals.append(val)
            if all_vals:
                merged_lists[field] = _unique_list(all_vals)

        # Merge exporters (sum counts)
        merged_exporters = {}
        for r in group_rows:
            exp = _to_dict(r.get("exporters", {}))
            for name, count in exp.items():
                merged_exporters[name] = merged_exporters.get(name, 0) + (int(count) if count else 0)

        # Keep longer/non-empty text fields
        text_fields = ["company_name_english", "country_code"]
        merged_text = {}
        for field in text_fields:
            best = ""
            for r in group_rows:
                v = r.get(field, "") or ""
                if len(str(v)) > len(str(best)):
                    best = v
            if best:
                merged_text[field] = best

        # --- Build update payload ---
        update = {
            "total_usd": merged_usd,
            "total_invoices": merged_invoices,
        }
        for field, vals in merged_lists.items():
            update[field] = vals
        if merged_exporters:
            update["exporters"] = merged_exporters
        update.update(merged_text)

        # --- Save to Supabase ---
        try:
            # Update the primary row
            primary_id = primary.get("id")
            if primary_id:
                client.table(table_name).update(update).eq("id", primary_id).execute()
                rows_updated += 1

            # Delete the other rows
            for r in others:
                rid = r.get("id")
                if rid:
                    client.table(table_name).delete().eq("id", rid).execute()
                    rows_deleted += 1
        except Exception as e:
            if callback:
                callback(f"⚠️ Error merging group: {e}")

    # Clear cache so next load picks up changes
    st.cache_data.clear()

    if callback:
        callback(f"✅ Merged! {len(merge_groups)} groups → deleted {rows_deleted} duplicates, updated {rows_updated} records.")

    return {
        "groups_found": len(merge_groups),
        "rows_deleted": rows_deleted,
        "rows_updated": rows_updated,
    }
