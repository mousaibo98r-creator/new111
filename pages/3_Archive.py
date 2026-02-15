"""
Page 3 — Archive & Recovery: Upload ANY file to Supabase Storage, manage & download
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — Archive", page_icon="📁", layout="wide")

import uuid
import base64
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

# ── Check Supabase availability ──────────────────────────────────────────────
from services.supabase_client import get_client

client = get_client()
db_ready = client is not None

if not db_ready:
    st.warning(
        "⚠️ Supabase is not configured. File uploads are disabled.\n\n"
        "Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to your Streamlit secrets."
    )

# ── Upload Section ───────────────────────────────────────────────────────────
st.markdown("### 📤 Upload Files")
c_upload, c_note = st.columns([2, 1])

with c_upload:
    uploaded = st.file_uploader(
        "Choose file(s) — any type",
        accept_multiple_files=True,
        disabled=not db_ready,
        key="archive_uploader",
    )

with c_note:
    note = st.text_area("Note (optional)", height=100, key="archive_note")

if st.button("⬆️ Upload to Archive", disabled=not db_ready or not uploaded, use_container_width=False):
    for f in uploaded:
        file_id = str(uuid.uuid4())
        file_bytes = f.getvalue()
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        file_size = len(file_bytes)

        # Size label
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

        try:
            meta = {
                "id": file_id,
                "filename": f.name,
                "file_type": f.type or "application/octet-stream",
                "file_size": file_size,
                "file_data": file_b64,
                "note": note or "",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            client.table("archive_files").insert(meta).execute()
            st.success(f"✅ Uploaded: **{f.name}** ({size_str})")

        except Exception as e:
            st.error(f"❌ Failed to upload {f.name}: {e}")

st.markdown("---")

# ── Archived Files List ──────────────────────────────────────────────────────
st.markdown("### 📋 Archived Files")

search_files = st.text_input("Search files…", key="archive_search", placeholder="filename or note")

if db_ready:
    try:
        resp = client.table("archive_files").select("id, filename, file_type, file_size, note, uploaded_at").order("uploaded_at", desc=True).execute()
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
    for f in files:
        fname = f.get("filename", "?")
        fnote = f.get("note", "")
        fdate = f.get("uploaded_at", "")[:19].replace("T", " ")
        fsize = f.get("file_size", 0)
        fid = f.get("id", "")

        # Size label
        if fsize < 1024:
            size_str = f"{fsize} B"
        elif fsize < 1024 * 1024:
            size_str = f"{fsize / 1024:.1f} KB"
        else:
            size_str = f"{fsize / (1024 * 1024):.1f} MB"

        with st.container():
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.markdown(f"**📄 {fname}**")
                info_parts = [size_str, fdate]
                if fnote:
                    info_parts.append(f"_{fnote}_")
                st.caption(" · ".join(info_parts))
            with c2:
                if st.button("📥 Download", key=f"dl_{fid}", use_container_width=True):
                    # Fetch file data
                    try:
                        resp2 = client.table("archive_files").select("file_data, filename, file_type").eq("id", fid).execute()
                        if resp2.data:
                            file_data = base64.b64decode(resp2.data[0]["file_data"])
                            st.download_button(
                                label="💾 Save File",
                                data=file_data,
                                file_name=resp2.data[0]["filename"],
                                mime=resp2.data[0].get("file_type", "application/octet-stream"),
                                key=f"save_{fid}",
                            )
                        else:
                            st.error("File not found in database.")
                    except Exception as e:
                        st.error(f"Download error: {e}")
            with c3:
                if st.button("🗑️ Delete", key=f"del_{fid}", use_container_width=True):
                    try:
                        client.table("archive_files").delete().eq("id", fid).execute()
                        st.success(f"Deleted {fname}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete error: {e}")

    st.caption(f"{len(files)} file(s) found")
elif db_ready:
    st.info("No archived files yet. Upload some files above.")
else:
    st.info("Configure Supabase to enable archive functionality.")
