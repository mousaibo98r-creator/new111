"""
Page 4 — Archive & Recovery: Upload files to Supabase Storage, manage metadata
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Archive", page_icon="📁", layout="wide")

import uuid
from datetime import datetime, timezone

from ui.style import inject_css
from ui.components import render_sidebar_brand, render_sidebar_nav

inject_css()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📁 Archive & Recovery</div>', unsafe_allow_html=True)
st.markdown("")

# ── Check storage availability ───────────────────────────────────────────────
from services.supabase_client import get_client, get_storage_client

storage_client = get_storage_client()
anon_client = get_client()
storage_ready = storage_client is not None

if not storage_ready:
    st.warning(
        "⚠️ Supabase is not configured. File uploads are disabled.\n\n"
        "Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` (+ optionally `SUPABASE_SERVICE_ROLE_KEY`) "
        "to your Streamlit secrets or environment variables."
    )

# ── Upload Section ───────────────────────────────────────────────────────────
st.markdown("### 📤 Upload Files")
c_upload, c_note = st.columns([2, 1])

with c_upload:
    uploaded = st.file_uploader(
        "Choose file(s)",
        type=["pdf", "csv", "xlsx", "xls", "png", "jpg", "jpeg", "gif", "webp"],
        accept_multiple_files=True,
        disabled=not storage_ready,
    )

with c_note:
    note = st.text_area("Note (optional)", height=100, key="archive_note")

if st.button("⬆️ Upload to Archive", disabled=not storage_ready or not uploaded, use_container_width=False):
    bucket = "archive"
    for f in uploaded:
        file_id = str(uuid.uuid4())
        storage_path = f"{file_id}/{f.name}"

        try:
            # Upload to storage
            storage_client.storage.from_(bucket).upload(
                storage_path,
                f.getvalue(),
                file_options={"content-type": f.type or "application/octet-stream"},
            )

            # Save metadata
            meta = {
                "id": file_id,
                "filename": f.name,
                "storage_path": storage_path,
                "note": note or "",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            if anon_client:
                anon_client.table("archive_files").insert(meta).execute()

            st.success(f"✅ Uploaded: {f.name}")

        except Exception as e:
            err_msg = str(e)
            if "policy" in err_msg.lower() or "403" in err_msg or "not allowed" in err_msg.lower():
                st.error(
                    f"❌ Storage policy blocked upload for **{f.name}**. "
                    "You may need `SUPABASE_SERVICE_ROLE_KEY` in your secrets, "
                    "or create a public/authenticated policy on the `archive` bucket."
                )
            else:
                st.error(f"❌ Failed to upload {f.name}: {err_msg}")

st.markdown("---")

# ── Archived Files List ──────────────────────────────────────────────────────
st.markdown("### 📋 Archived Files")

search_files = st.text_input("Search files…", key="archive_search", placeholder="filename or note")

if anon_client:
    try:
        resp = anon_client.table("archive_files").select("*").order("uploaded_at", desc=True).execute()
        files = resp.data or []
    except Exception:
        files = []
        st.info("Table `archive_files` not found. Create it in Supabase to enable file listing.")
else:
    files = []

if search_files:
    q = search_files.lower()
    files = [f for f in files if q in f.get("filename", "").lower() or q in f.get("note", "").lower()]

if files:
    # Build table
    header = "<th>Filename</th><th>Note</th><th>Uploaded</th><th>Actions</th>"
    rows = []
    for f in files:
        fname = f.get("filename", "?")
        fnote = f.get("note", "")[:60]
        fdate = f.get("uploaded_at", "")[:19].replace("T", " ")
        spath = f.get("storage_path", "")
        fid = f.get("id", "")

        # Build download URL
        dl_url = ""
        if storage_client and spath:
            try:
                dl_url = storage_client.storage.from_("archive").get_public_url(spath)
            except Exception:
                pass

        actions = ""
        if dl_url:
            actions += f'<a href="{dl_url}" target="_blank" class="detail-link">📥 Download</a>'

        rows.append(f"<tr><td>{fname}</td><td>{fnote}</td><td>{fdate}</td><td>{actions}</td></tr>")

    html = (
        '<div style="max-height:400px; overflow-y:auto; border:1px solid #21262d; border-radius:8px;">'
        f'<table class="file-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    st.caption(f"{len(files)} file(s) found")

    # Recovery section
    st.markdown("### 🔄 Recovery")
    recovery_file = st.selectbox(
        "Select a file to recover",
        ["— none —"] + [f.get("filename", "?") for f in files],
        key="recovery_select",
    )
    if recovery_file != "— none —" and st.button("♻️ Recover", key="btn_recover"):
        # Recovery = re-insert metadata into a recovery table
        match = [f for f in files if f.get("filename") == recovery_file]
        if match:
            item = match[0].copy()
            item["recovered_at"] = datetime.now(timezone.utc).isoformat()
            item.pop("id", None)
            item["id"] = str(uuid.uuid4())
            try:
                anon_client.table("archive_files").insert(item).execute()
                st.success(f"✅ Recovery entry created for **{recovery_file}**")
            except Exception as e:
                st.error(f"Recovery failed: {e}")

elif anon_client:
    st.info("No archived files yet. Upload some files above.")
else:
    st.info("Configure Supabase to enable archive functionality.")
