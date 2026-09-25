"""
Support Ticket Prioritizer - Initial Prototype UI
A simple Streamlit dashboard for triaging customer support tickets.
"""

import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Support Ticket Prioritizer",
    page_icon=":material/support_agent:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# Header & Subtitle
# ---------------------------------------------------------
st.title(":material/support_agent: Support Ticket Prioritizer")
st.caption("AI-powered customer support ticket triage")
st.divider()

# ---------------------------------------------------------
# Sidebar: Ticket Input Options
# ---------------------------------------------------------
st.sidebar.subheader(":material/inbox: Ticket Ingestion")

# 1. File Uploader for .txt tickets
uploaded_file = st.sidebar.file_uploader(
    "Upload support tickets (.txt)",
    type=["txt"],
    help="Upload a raw text file containing customer tickets"
)

# Pre-populate sample text if file uploaded
default_text = ""
if uploaded_file is not None:
    try:
        default_text = uploaded_file.read().decode("utf-8")
    except Exception:
        default_text = "Error reading uploaded file."

# 2. Text Area for pasting tickets
if "ticket_input" not in st.session_state:
    st.session_state["ticket_input"] = default_text

# Quick action button to load bundled sample tickets
if st.sidebar.button("Load Sample Tickets", icon=":material/file_open:", use_container_width=True):
    try:
        with open("data/sample_tickets.txt", "r", encoding="utf-8") as f:
            st.session_state["ticket_input"] = f.read()
            st.rerun()
    except FileNotFoundError:
        st.sidebar.error("Sample tickets file not found in data/ folder.", icon=":material/error:")

pasted_tickets = st.sidebar.text_area(
    "Or paste tickets directly:",
    key="ticket_input",
    height=220,
    placeholder="Paste ticket subjects and bodies here..."
)

# 3. Action Button: Run Triage
run_triage = st.sidebar.button("Run Triage", icon=":material/bolt:", type="primary", use_container_width=True)

if run_triage:
    st.sidebar.success("Triage triggered (AI pipeline will connect in next step)", icon=":material/check_circle:")

# ---------------------------------------------------------
# Main Dashboard: Summary Metrics Cards
# ---------------------------------------------------------
st.subheader(":material/analytics: Triage Overview")

col1, col2, col3, col4, col5 = st.columns(5)

# Demo summary values for the initial prototype
with col1:
    st.metric(label="Total Tickets", value="10")
with col2:
    st.metric(label="P1 Critical", value="3", delta="High priority", delta_color="inverse")
with col3:
    st.metric(label="P2 High", value="4", delta="Attention")
with col4:
    st.metric(label="P3 Normal", value="3")
with col5:
    st.metric(label="Duplicates", value="1", delta="Candidate", delta_color="off")

st.divider()

# ---------------------------------------------------------
# Priority Legend Section
# ---------------------------------------------------------
with st.expander("Priority Classification Guide", icon=":material/info:", expanded=False):
    leg_col1, leg_col2, leg_col3 = st.columns(3)
    with leg_col1:
        st.markdown(":material/error: **P1 — Critical**")
        st.caption("Service outages, security alerts, duplicate charges, system-wide blockers.")
    with leg_col2:
        st.markdown(":material/warning: **P2 — High**")
        st.caption("Feature failures, billing disputes, login locks blocking single users.")
    with leg_col3:
        st.markdown(":material/check_circle: **P3 — Normal**")
        st.caption("General inquiries, compliance docs, non-urgent feature questions.")

# ---------------------------------------------------------
# Section: Ticket Triage Results Table
# ---------------------------------------------------------
st.subheader(":material/table_chart: Ticket Triage Results")

# Realistic demo dataset without emojis
demo_data = [
    {
        "Ticket ID": "TICK-101",
        "Category": "Billing & Payments",
        "Priority": "P1 - Critical",
        "Customer Issue": "Charged twice ($1,200 x 2) for annual enterprise renewal",
        "Missing Information": "Bank statement screenshot",
        "Recommended Team": "Billing Ops",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-102",
        "Category": "Authentication",
        "Priority": "P1 - Critical",
        "Customer Issue": "HTTP 500 error after 2FA affecting multiple Chicago users",
        "Missing Information": "None (Console error provided)",
        "Recommended Team": "Platform Engineering",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-103",
        "Category": "Account Security",
        "Priority": "P2 - High",
        "Customer Issue": "Admin locked out after 5 invalid attempts before presentation",
        "Missing Information": "Admin email verification",
        "Recommended Team": "Tier 1 Support",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-104",
        "Category": "Logistics & Hardware",
        "Priority": "P3 - Normal",
        "Customer Issue": "FIDO2 security keys delivery delayed by 2 weeks",
        "Missing Information": "Shipping address confirmation",
        "Recommended Team": "Fulfillment Team",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-105",
        "Category": "Bug Report",
        "Priority": "P1 - Critical",
        "Customer Issue": "CSV export crashes with TypeError on September date filter",
        "Missing Information": "Browser version details",
        "Recommended Team": "Core Engineering",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-106",
        "Category": "Billing & Payments",
        "Priority": "P2 - High",
        "Customer Issue": "Pro-rated $350 charge for accidental 10 seats upgrade",
        "Missing Information": "Invoice number",
        "Recommended Team": "Billing Ops",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-107",
        "Category": "Subscription",
        "Priority": "P2 - High",
        "Customer Issue": "Cannot turn off auto-renew; Stripe customer ID missing",
        "Missing Information": "Stripe Customer ID",
        "Recommended Team": "Billing Ops",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-108",
        "Category": "Security Alert",
        "Priority": "P1 - Critical",
        "Customer Issue": "Suspicious login from Saint Petersburg, Russia",
        "Missing Information": "None",
        "Recommended Team": "Security Response",
        "Duplicate": "No",
    },
    {
        "Ticket ID": "TICK-109",
        "Category": "Authentication",
        "Priority": "P2 - High",
        "Customer Issue": "Password reset email not arriving in user inbox",
        "Missing Information": "Mail server logs from customer",
        "Recommended Team": "Tier 1 Support",
        "Duplicate": "Yes (similar to TICK-102)",
    },
    {
        "Ticket ID": "TICK-110",
        "Category": "General Inquiry",
        "Priority": "P3 - Normal",
        "Customer Issue": "Request for SOC2 Type II audit report under NDA",
        "Missing Information": "Signed NDA agreement",
        "Recommended Team": "Compliance & Legal",
        "Duplicate": "No",
    },
]

df_tickets = pd.DataFrame(demo_data)

# Display interactive dataframe with clean styling
st.dataframe(
    df_tickets,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Ticket ID": st.column_config.TextColumn("Ticket ID", width="small"),
        "Category": st.column_config.TextColumn("Category", width="medium"),
        "Priority": st.column_config.TextColumn("Priority", width="small"),
        "Customer Issue": st.column_config.TextColumn("Customer Issue", width="large"),
        "Missing Information": st.column_config.TextColumn("Missing Information", width="medium"),
        "Recommended Team": st.column_config.TextColumn("Recommended Team", width="medium"),
        "Duplicate": st.column_config.TextColumn("Duplicate", width="small"),
    }
)

# Subtle footer
st.markdown("<br><center><small style='color: gray;'>Support Ticket Prioritizer Prototype • Step 1</small></center>", unsafe_allow_html=True)
