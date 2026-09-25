"""
Support Ticket Prioritizer - Functional Prototype
Rule-based triage engine with dynamic dashboard metrics and triage table.
"""

import re
import os
import streamlit as st
import pandas as pd

# ---------------------------------------------------------
# Page Configuration & Constants
# ---------------------------------------------------------
st.set_page_config(
    page_title="Support Ticket Prioritizer",
    page_icon=":material/support_agent:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Allowed Categories (Strictly restricted to the 7 required categories)
ALLOWED_CATEGORIES = [
    "Billing",
    "Account/Login",
    "Technical Issue",
    "Delivery",
    "Security",
    "Subscription",
    "General Query",
]

# Team Routing Map
TEAM_MAPPING = {
    "Billing": "Billing & Payments",
    "Account/Login": "Account Support",
    "Technical Issue": "Technical Support",
    "Delivery": "Logistics",
    "Security": "Security Team",
    "Subscription": "Subscription Team",
    "General Query": "General Support",
}

PRIORITY_NAMES = {
    "P1": "Critical",
    "P2": "High",
    "P3": "Normal",
}


# ---------------------------------------------------------
# Helper Functions: Ticket Parsing & Issue Extraction
# ---------------------------------------------------------
def parse_tickets(raw_text: str) -> list[str]:
    """
    Splits raw input text into individual tickets.
    Supports separator lines ('---'), ticket headers, or blank lines.
    """
    if not raw_text or not raw_text.strip():
        return []

    cleaned = raw_text.strip()

    # 1. Delimiter: markdown/separator dashes '---'
    if "---" in cleaned:
        tickets = [t.strip() for t in cleaned.split("---") if t.strip()]
        if tickets:
            return tickets

    # 2. Header pattern: 'TICKET-xxx', 'TKT-xxx', 'Ticket 1:', etc.
    header_pattern = r"(?=(?:^|\n)(?:TICKET|TKT|Ticket)\s*[-#:\d]+)"
    splits = re.split(header_pattern, cleaned, flags=re.IGNORECASE)
    tickets = [t.strip() for t in splits if t.strip()]
    if len(tickets) > 1:
        return tickets

    # 3. Double newlines (paragraphs)
    paragraphs = [t.strip() for t in re.split(r"\n\s*\n+", cleaned) if t.strip()]
    if len(paragraphs) > 1:
        return paragraphs

    # Single ticket fallback
    return [cleaned]


def extract_customer_issue(ticket_text: str) -> str:
    """
    Extracts a concise summary of the customer's actual problem.
    Prefers Subject line or the first meaningful sentence.
    """
    issue = ""
    # Check for an explicit Subject header
    subject_match = re.search(r"Subject:\s*(.+)", ticket_text, re.IGNORECASE)
    if subject_match:
        subj = subject_match.group(1).strip()
        # Clean common subject prefixes
        clean_subj = re.sub(
            r"^(Urgent:\s*|Critical Bug:\s*|Security Alert:\s*|Question regarding\s*)",
            "",
            subj,
            flags=re.IGNORECASE,
        ).strip()
        issue = clean_subj
    else:
        # Fallback to first non-header, non-greeting sentence
        lines = [
            l.strip()
            for l in ticket_text.splitlines()
            if l.strip() and not l.lower().startswith(("ticket", "customer:", "from:", "id:"))
        ]
        if lines:
            first_line = lines[0]
            # Strip greetings like 'Hi,', 'Hello support team,'
            first_line = re.sub(r"^(Hi|Hello|Dear|Hey)[^,\n]*[,\.]\s*", "", first_line, flags=re.IGNORECASE).strip()
            issue = first_line[:130]
        else:
            issue = "Customer reported an issue."

    # Normalize customer perspective (e.g. "I was charged twice" -> "Customer was charged twice")
    issue = re.sub(r"^i\s+was\s+", "Customer was ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+am\s+", "Customer is ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+have\s+", "Customer has ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+cannot\s+", "Unable to ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^my\s+", "Customer's ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"\bmy\s+subscription\b", "the subscription", issue, flags=re.IGNORECASE)

    # Capitalize first letter
    if issue:
        issue = issue[0].upper() + issue[1:]
    return issue


def detect_missing_information(category: str, ticket_text: str) -> str:
    """
    Identifies obvious missing information based on category requirements.
    Returns 'None' if sufficient context exists.
    """
    text_lower = ticket_text.lower()

    if category == "Billing":
        # Check if actual transaction ID or invoice ID exists (e.g. TXN-1234, INV-5678, #123)
        has_txn = re.search(r"(TXN[-\d]+|INV[-\d]+|#\s*[A-Z0-9-]{3,}|transaction\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|invoice\s*(?:id|#|number)\s*[:#]?\s*[\w-]+)", ticket_text, re.IGNORECASE)
        if not has_txn:
            return "Transaction ID or payment receipt"
        return "None"

    if category == "Account/Login":
        # Check if email is provided
        has_email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", ticket_text)
        if not has_email and not any(k in text_lower for k in ["username is", "account id", "admin@"]):
            return "Account email address"
        return "None"

    if category == "Delivery":
        # Check for actual order ID or tracking code (e.g. Order #HW-44910, tracking #123)
        has_order = re.search(r"(order\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|tracking\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|#\s*[a-z0-9-]{4,})", text_lower)
        if not has_order:
            return "Order ID or tracking number"
        return "None"

    if category == "Technical Issue":
        # Check for browser / OS or error context
        has_env = any(k in text_lower for k in ["chrome", "firefox", "safari", "edge", "windows", "mac", "linux", "browser", "os version"])
        if not has_env:
            return "Browser/OS details or device info"
        return "None"

    if category == "Security":
        has_identifier = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", ticket_text) or any(k in text_lower for k in ["username is", "account:", "user:"])
        if not has_identifier:
            return "Affected account email or username"
        return "None"

    if category == "Subscription":
        if "stripe" in text_lower and "not found" in text_lower:
            return "Stripe customer portal ID or email"
        return "None"

    if category == "General Query":
        if any(k in text_lower for k in ["soc2", "compliance", "nda", "audit"]):
            return "Signed NDA or organization details"
        return "None"

    return "None"


# ---------------------------------------------------------
# Core Local Triage Function (Rule-Based)
# ---------------------------------------------------------
def triage_ticket(ticket_text: str) -> dict:
    """
    Performs rule-based triage on a single support ticket.
    Returns: category, priority (P1/P2/P3), customer_issue, missing_information, recommended_team.
    """
    text_lower = ticket_text.lower()

    # 1. Determine Category
    if any(k in text_lower for k in [
        "suspicious login", "foreign ip", "security alert", "unauthorized access",
        "compromised", "hacked", "data breach", "terminate active sessions"
    ]):
        category = "Security"

    elif any(k in text_lower for k in [
        "delivery", "shipping", "shipment", "package", "warehouse",
        "fido2 hardware", "hardware security key", "awaiting pickup", "re-ship", "courier"
    ]):
        category = "Delivery"

    elif any(k in text_lower for k in [
        "cancel auto-renew", "auto-renewal", "cancel subscription", "starter plan",
        "manage billing page", "stripe customer portal"
    ]) and not any(k in text_lower for k in ["charged twice", "refund request", "pro-rated charge"]):
        category = "Subscription"

    elif any(k in text_lower for k in [
        "charged twice", "duplicate charge", "refund", "invoice", "corporate card",
        "credit card", "payment", "billing", "pro-rated charge", "transaction id", "deducted twice"
    ]):
        category = "Billing"

    elif any(k in text_lower for k in [
        "unable to log in", "login", "log in", "2fa", "authenticator",
        "account locked", "locked out", "password reset", "forgot password", "reset link"
    ]):
        category = "Account/Login"

    elif any(k in text_lower for k in [
        "bug", "crash", "crashes", "typeerror", "500 error", "500 internal server error",
        "exception", "stack trace", "cannot read properties", "export crashes", "error"
    ]):
        category = "Technical Issue"

    else:
        category = "General Query"

    # Recommended Team Mapping
    recommended_team = TEAM_MAPPING.get(category, "General Support")

    # 2. Determine Priority (P1 / P2 / P3)
    priority = "P3"

    # P1 — Critical:
    # Major outages, security incidents, unauthorized transactions, severe payment failures
    is_p1_security = (category == "Security" and any(k in text_lower for k in ["unauthorized", "foreign ip", "breach", "compromise", "hacked"]))
    is_p1_billing = any(k in text_lower for k in ["charged twice", "unauthorized transaction", "duplicate charge", "fraudulent"])
    is_p1_outage = (
        ("500 error" in text_lower or "internal server error" in text_lower or "outage" in text_lower)
        and any(k in text_lower for k in ["multiple", "all users", "chicago office", "team members", "persistent", "down"])
    )
    is_p1_explicit = any(k in text_lower for k in ["major outage", "service completely unavailable", "critical system failure"])

    if is_p1_security or is_p1_billing or is_p1_outage or is_p1_explicit:
        priority = "P1"

    # P2 — High:
    # Important functionality broken, account locks, repeated payment problems, severe delays
    elif (
        any(k in text_lower for k in ["locked out", "account locked", "cannot access account", "admin account"])
        or any(k in text_lower for k in ["typeerror", "cannot read properties", "export crashes", "blocking", "critical bug"])
        or any(k in text_lower for k in ["delayed over two weeks", "delayed two weeks", "lost package"])
        or any(k in text_lower for k in ["cannot cancel auto-renew", "unable to cancel", "stripe customer portal"])
        or ("500 error" in text_lower or "login problem" in text_lower)
        or ("payment" in text_lower and "failed" in text_lower)
    ):
        priority = "P2"

    # P3 — Normal:
    # General queries, minor bugs, refund requests, password resets
    else:
        priority = "P3"

    # 3. Extract Customer Issue
    customer_issue = extract_customer_issue(ticket_text)

    # 4. Detect Missing Information
    missing_information = detect_missing_information(category, ticket_text)

    return {
        "category": category,
        "priority": priority,
        "customer_issue": customer_issue,
        "missing_information": missing_information,
        "recommended_team": recommended_team,
    }


def run_batch_triage(raw_text: str) -> list[dict]:
    """
    Parses tickets and runs triage on each, assigning IDs TKT-001, TKT-002, etc.
    """
    tickets = parse_tickets(raw_text)
    results = []
    for idx, t in enumerate(tickets, start=1):
        triage_data = triage_ticket(t)
        ticket_id = f"TKT-{idx:03d}"
        priority_code = triage_data["priority"]
        priority_label = f"{priority_code} - {PRIORITY_NAMES.get(priority_code, 'Normal')}"

        results.append({
            "Ticket ID": ticket_id,
            "Category": triage_data["category"],
            "Priority": priority_label,
            "Customer Issue": triage_data["customer_issue"],
            "Missing Information": triage_data["missing_information"],
            "Recommended Team": triage_data["recommended_team"],
            "Duplicate": "No",
        })
    return results


# ---------------------------------------------------------
# Header & Subtitle
# ---------------------------------------------------------
st.title(":material/support_agent: Support Ticket Prioritizer")
st.caption("AI-powered customer support ticket triage")
st.divider()

# ---------------------------------------------------------
# Load Default Sample Tickets if not already in session
# ---------------------------------------------------------
SAMPLE_PATH = os.path.join("data", "sample_tickets.txt")
default_sample_text = ""
if os.path.exists(SAMPLE_PATH):
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        default_sample_text = f.read()

# ---------------------------------------------------------
# Sidebar: Ticket Input Options
# ---------------------------------------------------------
st.sidebar.subheader(":material/inbox: Ticket Ingestion")

# 1. File Uploader for .txt tickets
uploaded_file = st.sidebar.file_uploader(
    "Upload support tickets (.txt)",
    type=["txt"],
    help="Upload a raw text file containing multiple customer tickets"
)

# If a file is newly uploaded, use its contents
if uploaded_file is not None:
    try:
        file_content = uploaded_file.read().decode("utf-8")
        st.session_state["ticket_input"] = file_content
    except Exception as e:
        st.sidebar.error(f"Error reading file: {e}")

# Ensure session state has default sample text if empty
if "ticket_input" not in st.session_state:
    st.session_state["ticket_input"] = default_sample_text

# Quick action button to reload bundled sample tickets
if st.sidebar.button("Load Sample Tickets", icon=":material/file_open:", use_container_width=True):
    st.session_state["ticket_input"] = default_sample_text
    st.rerun()

# 2. Text Area for pasting tickets
pasted_tickets = st.sidebar.text_area(
    "Or paste tickets directly:",
    key="ticket_input",
    height=220,
    placeholder="Paste ticket subjects and bodies here (separated by '---' or newlines)..."
)

# 3. Action Button: Run Triage
run_triage_clicked = st.sidebar.button("Run Triage", icon=":material/bolt:", type="primary", use_container_width=True)

# ---------------------------------------------------------
# Triage Processing State
# ---------------------------------------------------------
# If user clicks "Run Triage", process the active text input
if run_triage_clicked:
    active_text = st.session_state.get("ticket_input", "").strip()
    if not active_text:
        st.sidebar.warning("No ticket content found. Please paste tickets or load samples.", icon=":material/warning:")
    else:
        st.session_state["triage_results"] = run_batch_triage(active_text)
        st.sidebar.success(f"Triaged {len(st.session_state['triage_results'])} tickets successfully!", icon=":material/check_circle:")

# Initial run if no results yet exist in session
if "triage_results" not in st.session_state:
    initial_text = st.session_state.get("ticket_input", default_sample_text).strip()
    if initial_text:
        st.session_state["triage_results"] = run_batch_triage(initial_text)
    else:
        st.session_state["triage_results"] = []

# Prepare Dataframe & Dynamic Metrics
results = st.session_state.get("triage_results", [])
df_tickets = pd.DataFrame(results)

if not df_tickets.empty:
    total_count = len(df_tickets)
    p1_count = int(df_tickets["Priority"].str.startswith("P1").sum())
    p2_count = int(df_tickets["Priority"].str.startswith("P2").sum())
    p3_count = int(df_tickets["Priority"].str.startswith("P3").sum())
    dup_count = 0  # Duplicate detection is deferred to next step
else:
    total_count = p1_count = p2_count = p3_count = dup_count = 0

# ---------------------------------------------------------
# Main Dashboard: Dynamic Summary Metrics Cards
# ---------------------------------------------------------
st.subheader(":material/analytics: Triage Overview")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(label="Total Tickets", value=str(total_count))
with col2:
    st.metric(
        label="P1 Critical",
        value=str(p1_count),
        delta="Critical" if p1_count > 0 else None,
        delta_color="inverse",
    )
with col3:
    st.metric(
        label="P2 High",
        value=str(p2_count),
        delta="Attention" if p2_count > 0 else None,
        delta_color="normal",
    )
with col4:
    st.metric(label="P3 Normal", value=str(p3_count))
with col5:
    st.metric(label="Possible Duplicates", value=str(dup_count), delta="0 Detected", delta_color="off")

st.divider()

# ---------------------------------------------------------
# Priority Legend Section
# ---------------------------------------------------------
with st.expander("Priority Classification Guide", icon=":material/info:", expanded=False):
    leg_col1, leg_col2, leg_col3 = st.columns(3)
    with leg_col1:
        st.markdown(":material/error: **P1 — Critical**")
        st.caption("Service outages, security incidents, unauthorized transactions, critical payment failures.")
    with leg_col2:
        st.markdown(":material/warning: **P2 — High**")
        st.caption("Feature broken, account locks, repeated payment errors, severe shipment delays.")
    with leg_col3:
        st.markdown(":material/check_circle: **P3 — Normal**")
        st.caption("General queries, minor bugs, refund requests, password resets, doc inquiries.")

# ---------------------------------------------------------
# Section: Dynamic Ticket Triage Results Table
# ---------------------------------------------------------
st.subheader(":material/table_chart: Ticket Triage Results")

if df_tickets.empty:
    st.info("No tickets have been triaged yet. Paste tickets or click 'Load Sample Tickets' and press 'Run Triage'.", icon=":material/info:")
else:
    # Color priority column for immediate visual distinction
    def highlight_priority(val):
        if "P1" in str(val):
            return "color: #e53935; font-weight: 600;"
        elif "P2" in str(val):
            return "color: #f57c00; font-weight: 600;"
        elif "P3" in str(val):
            return "color: #2e7d32; font-weight: 600;"
        return ""

    styled_df = df_tickets.style.map(highlight_priority, subset=["Priority"])

    st.dataframe(
        styled_df,
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
st.markdown("<br><center><small style='color: gray;'>Support Ticket Prioritizer Prototype • Step 2</small></center>", unsafe_allow_html=True)
