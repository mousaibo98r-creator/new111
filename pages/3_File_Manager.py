"""
Page 3 — File Manager: Upload, browse, download, delete files in Supabase Storage
Card-based layout with note, date, name for each file.
"""

import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — File Manager", page_icon="📁", layout="wide")

from datetime import datetime

from ui.style import inject_css
from ui.components import render_sidebar_brand, render_sidebar_nav
from services.supabase_client import get_client, get_storage_client

inject_css()

# ── Card CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.file-card {
    background: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
    border: 1px solid #21262d;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.file-card:hover {
    border-color: #a855f7;
    box-shadow: 0 4px 20px rgba(168, 85, 247, 0.15);
    transform: translateY(-2px);
}
.file-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #3b82f6, #a855f7);
    border-radius: 14px 14px 0 0;
}
.file-card-icon {
    font-size: 2.2rem;
    margin-bottom: 0.4rem;
}
.file-card-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #e6edf3;
    word-break: break-all;
    margin-bottom: 0.5rem;
    line-height: 1.3;
}
.file-card-note {
    font-size: 0.8rem;
    color: #a855f7;
    background: rgba(168, 85, 247, 0.1);
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
    display: inline-block;
}
.file-card-meta {
    font-size: 0.75rem;
    color: #8b949e;
    display: flex;
    gap: 1rem;
    margin-top: 0.4rem;
}
.file-card-meta span {
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📁 File Manager</div>', unsafe_allow_html=True)
st.markdown("")

BUCKET = "archives"

# ── Supabase check ───────────────────────────────────────────────────────────
client = get_storage_client()
if not client:
    client = get_client()
if not client:
    st.error("⚠️ Supabase is not configured. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to secrets.")
    st.stop()

# ── Upload Section ───────────────────────────────────────────────────────────
st.markdown("### 📤 Upload Files")

c_upload, c_note = st.columns([2, 1])

with c_upload:
    uploaded_files = st.file_uploader(
        "Drag & drop or browse — **any file type accepted**",
        accept_multiple_files=True,
        key="fm_uploader",
    )

with c_note:
    note = st.text_area("📝 Note (optional)", height=120, key="fm_note",
                        placeholder="Add a note for this upload…")

if uploaded_files and st.button("⬆️ Upload to Storage", use_container_width=False):
    for f in uploaded_files:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_original = re.sub(r'[^\w.\-]', '_', f.name)

        if note and note.strip():
            clean_note = re.sub(r'[^a-zA-Z0-9_\- ]', '', note.strip())[:50].strip().replace(' ', '_')
            safe_name = f"{ts}__{clean_note}__{clean_original}"
        else:
            safe_name = f"{ts}__{clean_original}"

        file_bytes = f.getvalue()
        content_type = f.type or "application/octet-stream"

        try:
            client.storage.from_(BUCKET).upload(
                safe_name, file_bytes,
                file_options={"content-type": content_type},
            )
            st.success(f"✅ Uploaded: **{f.name}** ({len(file_bytes) / 1024:.1f} KB)")
        except Exception as e:
            err = str(e)
            if "Duplicate" in err or "already exists" in err.lower():
                try:
                    client.storage.from_(BUCKET).update(
                        safe_name, file_bytes,
                        file_options={"content-type": content_type},
                    )
                    st.success(f"✅ Updated: **{f.name}**")
                except Exception as e2:
                    st.error(f"❌ Upload failed: {e2}")
            elif "bucket" in err.lower() and "not found" in err.lower():
                st.error(f"❌ Bucket `{BUCKET}` doesn't exist! Create it in Supabase → Storage.")
            else:
                st.error(f"❌ Upload failed for {f.name}: {err}")

    if st.button("🔄 Refresh file list"):
        st.rerun()

st.markdown("---")

# ── File Browser — Card Layout ───────────────────────────────────────────────
st.markdown("### 📋 Files in Storage")

try:
    file_list = client.storage.from_(BUCKET).list()
except Exception as e:
    file_list = []
    st.error(f"❌ Could not list files: {e}")

files = [f for f in file_list if f.get("name") and f.get("id")]

if not files:
    st.info("No files in the bucket yet. Upload some above!")
    with st.expander("🔍 Debug"):
        st.write(f"Bucket: `{BUCKET}`, Raw items: {len(file_list)}")
        if file_list:
            st.json(file_list[:3])
        try:
            buckets = client.storage.list_buckets()
            st.write(f"Buckets: {[b.name for b in buckets]}")
        except Exception as be:
            st.write(f"Cannot list buckets: {be}")
else:
    # Search
    search = st.text_input("🔍 Filter files…", key="fm_search", placeholder="type to filter by name")
    if search:
        files = [f for f in files if search.lower() in f.get("name", "").lower()]

    st.caption(f"📦 {len(files)} file(s)")

    # Helper: get icon by extension
    def _file_icon(name):
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        icons = {
            "pdf": "📕", "xlsx": "📗", "xls": "📗", "csv": "📊",
            "doc": "📘", "docx": "📘", "txt": "📄", "json": "📋",
            "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️",
            "mp4": "🎬", "zip": "📦", "rar": "📦", "pptx": "📙",
        }
        return icons.get(ext, "📄")

    # Helper: extract note from filename (between double underscores)
    def _extract_note(name):
        parts = name.split("__")
        if len(parts) >= 3:
            return parts[1].replace("_", " ")
        return None

    # Helper: extract clean display name
    def _display_name(name):
        parts = name.split("__")
        if len(parts) >= 3:
            return parts[-1]
        elif len(parts) == 2:
            return parts[-1]
        return name

    # Render cards in 3-column grid
    cols_per_row = 3
    for i in range(0, len(files), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(files):
                break

            f = files[idx]
            name = f.get("name", "")
            raw_size = f.get("metadata", {}).get("size", 0) if f.get("metadata") else 0

            # Size
            if raw_size < 1024:
                size_str = f"{raw_size} B"
            elif raw_size < 1024 * 1024:
                size_str = f"{raw_size / 1024:.1f} KB"
            else:
                size_str = f"{raw_size / (1024 * 1024):.1f} MB"

            # Date
            created_raw = f.get("created_at", "")
            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                date_str = created_dt.strftime("%b %d, %Y  %H:%M")
            except Exception:
                date_str = created_raw[:19] if created_raw else "—"

            icon = _file_icon(name)
            note_text = _extract_note(name)
            display_name = _display_name(name)

            # Build note HTML
            note_html = ""
            if note_text:
                note_html = f'<div class="file-card-note">📝 {note_text}</div>'

            with col:
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-icon">{icon}</div>
                    <div class="file-card-name">{display_name}</div>
                    {note_html}
                    <div class="file-card-meta">
                        <span>📅 {date_str}</span>
                        <span>💾 {size_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Action buttons
                bc1, bc2 = st.columns(2)

                # Download
                dl_url = None
                try:
                    signed = client.storage.from_(BUCKET).create_signed_url(name, 3600)
                    dl_url = signed.get("signedURL") or signed.get("signedUrl")
                except Exception:
                    pass
                if not dl_url:
                    try:
                        dl_url = client.storage.from_(BUCKET).get_public_url(name)
                    except Exception:
                        dl_url = None

                with bc1:
                    if dl_url:
                        st.markdown(
                            f'<a href="{dl_url}" target="_blank" '
                            f'style="display:block;text-align:center;padding:0.4rem;'
                            f'background:linear-gradient(135deg,#3b82f6,#6366f1);'
                            f'color:white;border-radius:8px;text-decoration:none;'
                            f'font-size:0.8rem;font-weight:500;">⬇️ Download</a>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.button("⬇️", disabled=True, key=f"dl_{name}")

                with bc2:
                    if st.button("🗑️ Delete", key=f"del_{name}", use_container_width=True):
                        try:
                            client.storage.from_(BUCKET).remove([name])
                            st.success(f"Deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")
