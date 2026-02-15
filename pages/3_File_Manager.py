"""
Page 3 — File Manager: Upload, browse, download, delete files in Supabase Storage
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
st.set_page_config(page_title="OBSIDIAN — File Manager", page_icon="📁", layout="wide")

from datetime import datetime

from ui.style import inject_css
from ui.components import render_sidebar_brand, render_sidebar_nav
from services.supabase_client import get_client

inject_css()

# ── Sidebar ──────────────────────────────────────────────────────────────────
render_sidebar_brand()
render_sidebar_nav()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📁 File Manager</div>', unsafe_allow_html=True)
st.markdown("")

BUCKET = "archives"

# ── Supabase check ───────────────────────────────────────────────────────────
client = get_client()
if not client:
    st.error(
        "⚠️ Supabase is not configured. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to secrets."
    )
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
    upload_ok = 0
    upload_fail = 0
    for f in uploaded_files:
        # Add timestamp prefix to avoid duplicates
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Include note in filename if provided — avoid special chars
        if note and note.strip():
            import re
            clean_note = re.sub(r'[^a-zA-Z0-9_\- ]', '', note.strip())[:50].strip().replace(' ', '_')
            safe_name = f"{ts}__{clean_note}__{f.name}"
        else:
            safe_name = f"{ts}_{f.name}"

        # Also clean the final filename of any remaining invalid chars
        import re
        safe_name = re.sub(r'[^\w.\-]', '_', safe_name)

        file_bytes = f.getvalue()
        content_type = f.type or "application/octet-stream"

        try:
            resp = client.storage.from_(BUCKET).upload(
                safe_name,
                file_bytes,
                file_options={"content-type": content_type},
            )
            upload_ok += 1
            st.success(f"✅ Uploaded: **{f.name}** ({len(file_bytes)/ 1024:.1f} KB)")
        except Exception as e:
            err = str(e)
            if "Duplicate" in err or "already exists" in err.lower():
                try:
                    client.storage.from_(BUCKET).update(
                        safe_name,
                        file_bytes,
                        file_options={"content-type": content_type},
                    )
                    upload_ok += 1
                    st.success(f"✅ Updated: **{f.name}**")
                except Exception as e2:
                    upload_fail += 1
                    st.error(f"❌ Upload failed for {f.name}: {e2}")
            elif "policy" in err.lower() or "403" in err or "not allowed" in err.lower():
                upload_fail += 1
                st.error(
                    f"❌ Storage policy blocked **{f.name}**.\n\n"
                    "Go to Supabase → Storage → archives → Policies → Add Policy:\n\n"
                    "- **Operation**: INSERT\n"
                    "- **Policy**: Allow for all users\n"
                    "- **Target roles**: anon, authenticated"
                )
            else:
                upload_fail += 1
                st.error(f"❌ Upload failed for {f.name}: {err}")

    if upload_ok > 0:
        st.balloons()
        # Wait a moment then refresh the file list
        import time
        time.sleep(1)
        st.rerun()

st.markdown("---")

# ── File Browser ─────────────────────────────────────────────────────────────
st.markdown("### 📋 Files in Storage")

try:
    file_list = client.storage.from_(BUCKET).list()
except Exception as e:
    file_list = []
    st.warning(f"Could not list files: {e}")

# Filter out folders / empty entries
files = [f for f in file_list if f.get("name") and f.get("id")]

if not files:
    st.info("No files in the bucket yet. Upload some above!")
    # Debug: show raw response
    with st.expander("🔍 Debug: raw storage response"):
        st.write(f"Bucket: `{BUCKET}`")
        st.write(f"Raw list response ({len(file_list)} items):")
        st.json(file_list[:10] if file_list else [])
else:
    # Search / filter
    search = st.text_input("🔍 Filter files…", key="fm_search", placeholder="type to filter by name")
    if search:
        files = [f for f in files if search.lower() in f.get("name", "").lower()]

    st.caption(f"{len(files)} file(s)")

    # Table header
    h1, h2, h3, h4, h5 = st.columns([4, 1.5, 2, 1.2, 1.2])
    h1.markdown("**Name**")
    h2.markdown("**Size**")
    h3.markdown("**Created**")
    h4.markdown("**⬇️**")
    h5.markdown("**🗑️**")

    for f in files:
        name = f.get("name", "")
        raw_size = f.get("metadata", {}).get("size", 0) if f.get("metadata") else 0

        # Size formatting
        if raw_size < 1024:
            size_str = f"{raw_size} B"
        elif raw_size < 1024 * 1024:
            size_str = f"{raw_size / 1024:.1f} KB"
        else:
            size_str = f"{raw_size / (1024 * 1024):.1f} MB"

        # Created timestamp
        created_raw = f.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            created_str = created_dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_str = created_raw[:19] if created_raw else "—"

        # Public download URL
        try:
            pub_url = client.storage.from_(BUCKET).get_public_url(name)
        except Exception:
            pub_url = None

        c1, c2, c3, c4, c5 = st.columns([4, 1.5, 2, 1.2, 1.2])
        c1.markdown(f"📄 {name}")
        c2.markdown(size_str)
        c3.markdown(created_str)

        with c4:
            if pub_url:
                st.link_button("⬇️", pub_url, use_container_width=True)
            else:
                st.button("⬇️", disabled=True, key=f"dl_{name}")

        with c5:
            if st.button("🗑️", key=f"del_{name}", use_container_width=True):
                try:
                    client.storage.from_(BUCKET).remove([name])
                    st.success(f"Deleted **{name}**")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
