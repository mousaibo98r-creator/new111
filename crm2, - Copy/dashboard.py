"""
dashboard.py
─────────────────────────────────────────────────────────────
Antigravity :: Monitoring Dashboard
A Streamlit web app that connects to Supabase and provides a
real-time view of campaign performance, lead pipeline, and
activity logs.

Run:  streamlit run dashboard.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

import db

load_dotenv()

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Antigravity · Outreach",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    .main { background: #0a0a0f; }
    .stApp { background: #0a0a0f; color: #e8e8f0; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #111118 !important;
        border-right: 1px solid #1e1e2e;
    }
    [data-testid="stSidebar"] * { color: #c0c0d0 !important; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #13131a;
        border: 1px solid #1e1e2e;
        border-radius: 8px;
        padding: 16px 20px;
    }
    [data-testid="stMetricValue"] {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 2rem !important;
        color: #7ee8a2 !important;
    }
    [data-testid="stMetricLabel"] { color: #7070a0 !important; font-size: 0.75rem !important; }

    /* Dataframes */
    [data-testid="stDataFrame"] { border: 1px solid #1e1e2e; border-radius: 8px; }

    /* Headers */
    h1, h2, h3 { font-family: 'IBM Plex Mono', monospace !important; }
    h1 { color: #7ee8a2 !important; letter-spacing: -0.5px; }
    h2 { color: #a0a0c0 !important; font-size: 1rem !important;
         text-transform: uppercase; letter-spacing: 2px; }

    /* Status badges */
    .badge {
        display: inline-block; padding: 2px 10px;
        border-radius: 4px; font-size: 0.72rem;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600; letter-spacing: 0.5px;
    }
    .badge-sent        { background: #1a2a3a; color: #60b4f0; }
    .badge-interested  { background: #1a2e1e; color: #7ee8a2; }
    .badge-pending     { background: #2a2a1a; color: #e8d060; }
    .badge-failed      { background: #2e1a1a; color: #f07070; }
    .badge-follow_up   { background: #2a1a2e; color: #c07ef0; }
    .badge-not_interested { background: #1e1e1e; color: #606070; }

    /* Section divider */
    hr { border-color: #1e1e2e !important; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid #1e1e2e; }
    .stTabs [data-baseweb="tab"] {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem; color: #606080;
        background: transparent; border: none;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        color: #7ee8a2 !important;
        border-bottom: 2px solid #7ee8a2 !important;
        background: transparent !important;
    }

    /* Buttons */
    .stButton button {
        background: #13131a; border: 1px solid #2e2e4e;
        color: #c0c0d0; font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem; border-radius: 6px;
    }
    .stButton button:hover { border-color: #7ee8a2; color: #7ee8a2; }

    /* Input fields */
    .stTextInput input, .stSelectbox select, .stTextArea textarea {
        background: #13131a !important; color: #e8e8f0 !important;
        border: 1px solid #2e2e4e !important; border-radius: 6px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Plotly dark theme ──────────────────────────────────────────
PLOT_THEME = dict(
    paper_bgcolor="#13131a",
    plot_bgcolor="#13131a",
    font=dict(family="IBM Plex Mono", color="#a0a0c0", size=11),
    margin=dict(l=16, r=16, t=32, b=16),
)

STATUS_COLORS = {
    "pending":        "#e8d060",
    "sent":           "#60b4f0",
    "opened":         "#60d4f0",
    "replied":        "#c07ef0",
    "interested":     "#7ee8a2",
    "not_interested": "#606070",
    "follow_up":      "#c07ef0",
    "bounced":        "#f07070",
    "unsubscribed":   "#404050",
}


# ── Helpers ────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_leads() -> pd.DataFrame:
    rows = db.get_all_leads()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def load_logs() -> pd.DataFrame:
    rows = db.get_logs(limit=300)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def load_recent_activity() -> pd.DataFrame:
    rows = db.get_recent_activity(limit=50)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def refresh_all() -> None:
    load_leads.clear()
    load_logs.clear()
    load_recent_activity.clear()
    st.rerun()


def fmt_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d  %H:%M")
    except Exception:
        return ts or "—"


def handle_save_edits(df, edited_data):
    """Callback to persist st.data_editor changes to Supabase."""
    if not edited_data or "edited_rows" not in edited_data:
        return
    
    edited_rows = edited_data["edited_rows"]
    for idx_str, changes in edited_rows.items():
        idx = int(idx_str)
        lead_id = df.iloc[idx]["id"]
        
        if changes:
            try:
                db.update_lead(lead_id, **changes)
                st.toast(f"✅ Updated lead {df.iloc[idx]['name']}", icon="✔️")
            except Exception as e:
                st.error(f"Failed to update lead: {e}")

# ═══════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚡ ANTIGRAVITY")
    st.markdown("---")

    # Connection status
    try:
        db.get_client()
        st.success("● Supabase connected", icon=None)
    except Exception as e:
        st.error(f"✗ Supabase error: {e}")

    st.markdown("---")

    if st.button("⟳  Refresh Data", use_container_width=True):
        refresh_all()

    st.markdown("---")
    st.markdown("#### Add Lead")
    with st.form("add_lead_form", clear_on_submit=True):
        new_name    = st.text_input("Name")
        new_company = st.text_input("Company")
        new_email   = st.text_input("Email")
        submit      = st.form_submit_button("Add Lead", use_container_width=True)
        if submit:
            if not (new_name and new_company and new_email):
                st.warning("All fields required.")
            else:
                try:
                    db.create_lead(new_name, new_company, new_email)
                    st.success(f"Added {new_name}")
                    refresh_all()
                except Exception as e:
                    st.error(str(e))

    st.markdown("---")
    st.caption("Antigravity v1.0 · Built with Streamlit + Supabase")


# ═══════════════════════════════════════════════════════════════
#  MAIN CONTENT
# ═══════════════════════════════════════════════════════════════
st.markdown("# ⚡ Antigravity Outreach")
st.markdown("**B2B Cold Email Campaign Monitor**")
st.markdown("---")

df_leads = load_leads()
df_logs  = load_logs()

# ── KPI row ───────────────────────────────────────────────────
total      = len(df_leads) if not df_leads.empty else 0
sent       = len(df_leads[df_leads["status"] == "sent"])       if not df_leads.empty else 0
interested = len(df_leads[df_leads["status"] == "interested"]) if not df_leads.empty else 0
pending    = len(df_leads[df_leads["status"] == "pending"])    if not df_leads.empty else 0
conv_rate  = f"{(interested / sent * 100):.1f}%" if sent > 0 else "—"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Leads",   total)
c2.metric("Pending",       pending)
c3.metric("Emails Sent",   sent)
c4.metric("Interested",    interested)
c5.metric("Conv. Rate",    conv_rate)

st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📊  Pipeline", "👥  Leads", "📋  Logs", "🔧  Manage"])

# ── TAB 1: PIPELINE ──────────────────────────────────────────
with tab1:
    if df_leads.empty:
        st.info("No leads yet.  Add some from the sidebar.")
    else:
        status_counts = df_leads["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]

        col_a, col_b = st.columns([1, 1])

        with col_a:
            st.markdown("## Status Breakdown")
            fig_pie = go.Figure(go.Pie(
                labels=status_counts["status"],
                values=status_counts["count"],
                hole=0.55,
                marker_colors=[STATUS_COLORS.get(s, "#555566") for s in status_counts["status"]],
                textfont_family="IBM Plex Mono",
                textfont_size=11,
            ))
            fig_pie.update_layout(
                **PLOT_THEME,
                showlegend=True,
                legend=dict(font=dict(family="IBM Plex Mono", size=10), x=1, y=0.5),
                height=300,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            st.markdown("## Lead Volume by Status")
            fig_bar = px.bar(
                status_counts,
                x="status", y="count",
                color="status",
                color_discrete_map=STATUS_COLORS,
                text="count",
            )
            fig_bar.update_traces(textposition="outside", textfont_size=11)
            fig_bar.update_layout(**PLOT_THEME, showlegend=False, height=300)
            st.plotly_chart(fig_bar, use_container_width=True)

        # Timeline
        if "created_at" in df_leads.columns:
            st.markdown("## Lead Intake Over Time")
            df_leads["date"] = pd.to_datetime(df_leads["created_at"]).dt.date
            timeline = df_leads.groupby("date").size().reset_index(name="leads_added")
            fig_line = px.area(timeline, x="date", y="leads_added", line_shape="spline")
            fig_line.update_traces(
                line_color="#7ee8a2", fillcolor="rgba(126,232,162,0.12)"
            )
            fig_line.update_layout(**PLOT_THEME, height=200)
            st.plotly_chart(fig_line, use_container_width=True)


# ── TAB 2: LEADS TABLE ───────────────────────────────────────
with tab2:
    st.markdown("## Lead Pipeline")

    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        search = st.text_input("🔍  Search by name, company, or email", "")
    with col_f2:
        status_options = ["All"] + (sorted(df_leads["status"].unique().tolist()) if not df_leads.empty else [])
        status_filter  = st.selectbox("Filter by status", status_options)

    if not df_leads.empty:
        view = df_leads.copy()

        if search:
            mask = (
                view["name"].str.contains(search, case=False, na=False)
                | view["company"].str.contains(search, case=False, na=False)
                | view["email"].str.contains(search, case=False, na=False)
            )
            view = view[mask]

        if status_filter != "All":
            view = view[view["status"] == status_filter]

        display_cols = ["name", "company", "email", "status", "created_at"]
        display_cols = [c for c in display_cols if c in view.columns]

        if "created_at" in view.columns:
            view["created_at"] = view["created_at"].apply(fmt_time)

        # Interactive Editor
        edited_data = st.data_editor(
            view[display_cols],
            use_container_width=True,
            hide_index=True,
            key="lead_editor_comma",
            column_config={
                "name":       st.column_config.TextColumn("Name"),
                "company":    st.column_config.TextColumn("Company"),
                "email":      st.column_config.TextColumn("Email", disabled=True),
                "status":     st.column_config.SelectboxColumn(
                    "Status",
                    options=[
                        "new", "contacted", "replied", "interested", 
                        "not_interested", "bounced", "wrong_person", 
                        "out_of_office", "unsubscribe", "manual_reply_needed", "paused"
                    ],
                    required=True
                ),
                "created_at": st.column_config.TextColumn("Created", disabled=True),
            },
        )
        
        if st.button("💾 Persist Table Changes", use_container_width=True):
            handle_save_edits(view, st.session_state["lead_editor_comma"])
            refresh_all()
        st.caption(f"Showing {len(view)} of {total} leads")
    else:
        st.info("No leads found.")


# ── TAB 3: LOGS ──────────────────────────────────────────────
with tab3:
    st.markdown("## Activity Log")

    if not df_logs.empty:
        # Event type filter
        event_types   = ["All"] + sorted(df_logs["event_type"].unique().tolist())
        event_filter  = st.selectbox("Filter by event", event_types)

        view_logs = df_logs.copy()
        if event_filter != "All":
            view_logs = view_logs[view_logs["event_type"] == event_filter]

        display_log_cols = ["created_at", "event_type", "email", "subject", "ai_classification", "ai_confidence"]
        display_log_cols = [c for c in display_log_cols if c in view_logs.columns]

        if "created_at" in view_logs.columns:
            view_logs["created_at"] = view_logs["created_at"].apply(fmt_time)

        st.dataframe(
            view_logs[display_log_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "created_at":        st.column_config.TextColumn("Time"),
                "event_type":        st.column_config.TextColumn("Event"),
                "email":             st.column_config.TextColumn("Email"),
                "subject":           st.column_config.TextColumn("Subject"),
                "ai_classification": st.column_config.TextColumn("AI Class"),
                "ai_confidence":     st.column_config.NumberColumn("Confidence", format="%.2f"),
            },
        )

        # Log event breakdown chart
        st.markdown("## Events by Type")
        event_counts = df_logs["event_type"].value_counts().reset_index()
        event_counts.columns = ["event", "count"]
        fig_ev = px.bar(event_counts, x="count", y="event", orientation="h", text="count")
        fig_ev.update_traces(marker_color="#60b4f0", textposition="outside")
        fig_ev.update_layout(**PLOT_THEME, height=250, showlegend=False)
        st.plotly_chart(fig_ev, use_container_width=True)
    else:
        st.info("No log entries yet.")


# ── TAB 4: MANAGE LEADS ──────────────────────────────────────
with tab4:
    st.markdown("## Update Lead Status")

    if not df_leads.empty:
        lead_options = {
            f"{r['name']} ({r['email']})": r["id"]
            for _, r in df_leads.iterrows()
        }
        selected_label = st.selectbox("Select Lead", list(lead_options.keys()))
        selected_id    = lead_options[selected_label]

        current_lead = df_leads[df_leads["id"] == selected_id].iloc[0]
        st.write(f"**Company:** {current_lead['company']}")
        st.write(f"**Current Status:** `{current_lead['status']}`")

        new_status = st.selectbox(
            "New Status",
            ["pending", "sent", "opened", "replied", "interested",
             "not_interested", "follow_up", "bounced", "unsubscribed"],
            index=["pending", "sent", "opened", "replied", "interested",
                   "not_interested", "follow_up", "bounced", "unsubscribed"].index(
                current_lead["status"]
            ) if current_lead["status"] in ["pending", "sent", "opened", "replied",
                "interested", "not_interested", "follow_up", "bounced", "unsubscribed"]
            else 0,
        )

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            if st.button("Update Status", use_container_width=True):
                db.update_lead_status(selected_id, new_status)
                db.create_log(
                    email=current_lead["email"],
                    event_type="status_changed",
                    lead_id=selected_id,
                    metadata={"from": current_lead["status"], "to": new_status},
                )
                st.success(f"Status updated to `{new_status}`")
                refresh_all()
        with col_u2:
            if st.button("🗑️  Delete Lead", type="secondary", use_container_width=True):
                db.delete_lead(selected_id)
                st.warning(f"Lead deleted.")
                refresh_all()

    else:
        st.info("No leads to manage.")

    st.markdown("---")
    st.markdown("## Bulk Import (CSV)")
    st.caption("CSV must have columns: name, company, email")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        import io
        df_upload = pd.read_csv(io.BytesIO(uploaded.read()))
        required = {"name", "company", "email"}
        if not required.issubset(set(df_upload.columns)):
            st.error(f"CSV must contain columns: {required}")
        else:
            preview = df_upload[["name", "company", "email"]].head(10)
            st.dataframe(preview, use_container_width=True, hide_index=True)
            if st.button(f"Import {len(df_upload)} leads", use_container_width=True):
                records = df_upload[["name", "company", "email"]].to_dict("records")
                db.upsert_leads(records)
                st.success(f"Imported {len(records)} leads.")
                refresh_all()
