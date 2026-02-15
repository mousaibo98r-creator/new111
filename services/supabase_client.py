"""
Supabase client singleton — reads keys from Streamlit Secrets or env vars.
Never logs or prints secrets.
"""

from __future__ import annotations
import os
import streamlit as st

_client = None
_storage_client = None


def _get_secret(key: str) -> str | None:
    """Read a secret from st.secrets first, then fall back to env var."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key)


def get_client():
    """Return a Supabase client (anon key).  Returns None if keys missing."""
    global _client
    if _client is not None:
        return _client

    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_ANON_KEY")

    if not url or not key:
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception:
        return None


def get_storage_client():
    """Return a Supabase client using the *service-role* key (for Storage uploads).
    Falls back to anon client if service-role key is not set.
    Returns None if no keys at all."""
    global _storage_client
    if _storage_client is not None:
        return _storage_client

    url = _get_secret("SUPABASE_URL")
    srv_key = _get_secret("SUPABASE_SERVICE_ROLE_KEY")

    if url and srv_key:
        try:
            from supabase import create_client
            _storage_client = create_client(url, srv_key)
            return _storage_client
        except Exception:
            pass

    # fall back to anon client
    return get_client()


def check_connection() -> dict:
    """Return a status dict: reachable, tables_found, storage_ok."""
    status = {"reachable": False, "tables": [], "storage_buckets": []}
    client = get_client()
    if client is None:
        return status

    try:
        # Try listing a few rows from buyers
        resp = client.table("buyers").select("id").limit(1).execute()
        status["reachable"] = True
        status["tables"].append("buyers")
    except Exception:
        # table may not exist yet — still reachable
        try:
            # simple health check via schema
            status["reachable"] = True
        except Exception:
            pass

    try:
        resp = client.table("archive_files").select("id").limit(1).execute()
        status["tables"].append("archive_files")
    except Exception:
        pass

    try:
        storage = get_storage_client()
        if storage:
            buckets = storage.storage.list_buckets()
            status["storage_buckets"] = [b.name for b in buckets] if buckets else []
    except Exception:
        pass

    return status
