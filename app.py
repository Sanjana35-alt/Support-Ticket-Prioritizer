"""
Support Ticket Prioritizer - Complete Functional Prototype
AI Classification (Gemini), Local Rule Fallback, Duplicate Detection, and Ticket Details Inspector.
"""

import html
import json
import os
import re
from difflib import SequenceMatcher
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
ALLOWED_CATEGORIES = {
    "Billing",
    "Account/Login",
    "Technical Issue",
    "Delivery",
    "Security",
    "Subscription",
    "General Query",
}

# Allowed Priorities
ALLOWED_PRIORITIES = {"P1", "P2", "P3"}

# Allowed Teams
ALLOWED_TEAMS = {
    "Billing & Payments",
    "Account Support",
    "Technical Support",
    "Logistics",
    "Security Team",
    "Subscription Team",
    "General Support",
}

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
    subject_match = re.search(r"Subject:\s*(.+)", ticket_text, re.IGNORECASE)
    if subject_match:
        subj = subject_match.group(1).strip()
        clean_subj = re.sub(
            r"^(Urgent:\s*|Critical Bug:\s*|Security Alert:\s*|Question regarding\s*)",
            "",
            subj,
            flags=re.IGNORECASE,
        ).strip()
        issue = clean_subj
    else:
        lines = [
            l.strip()
            for l in ticket_text.splitlines()
            if l.strip() and not l.lower().startswith(("ticket", "customer:", "from:", "id:"))
        ]
        if lines:
            first_line = lines[0]
            first_line = re.sub(r"^(Hi|Hello|Dear|Hey)[^,\n]*[,\.]\s*", "", first_line, flags=re.IGNORECASE).strip()
            issue = first_line[:130]
        else:
            issue = "Customer reported an issue."

    # Normalize customer perspective
    issue = re.sub(r"^i\s+was\s+", "Customer was ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+am\s+", "Customer is ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+have\s+", "Customer has ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^i\s+cannot\s+", "Unable to ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"^my\s+", "Customer's ", issue, flags=re.IGNORECASE)
    issue = re.sub(r"\bmy\s+subscription\b", "the subscription", issue, flags=re.IGNORECASE)

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
        has_txn = re.search(r"(TXN[-\d]+|INV[-\d]+|#\s*[A-Z0-9-]{3,}|transaction\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|invoice\s*(?:id|#|number)\s*[:#]?\s*[\w-]+)", ticket_text, re.IGNORECASE)
        if not has_txn:
            return "Transaction ID or payment receipt"
        return "None"

    if category == "Account/Login":
        has_email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", ticket_text)
        if not has_email and not any(k in text_lower for k in ["username is", "account id", "admin@"]):
            return "Account email address"
        return "None"

    if category == "Delivery":
        has_order = re.search(r"(order\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|tracking\s*(?:id|#|number)\s*[:#]?\s*[\w-]+|#\s*[a-z0-9-]{4,})", text_lower)
        if not has_order:
            return "Order ID or tracking number"
        return "None"

    if category == "Technical Issue":
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
# Feature 1: Lightweight Duplicate Detection
# ---------------------------------------------------------
def get_tokens(text: str) -> set[str]:
    """Extracts non-trivial word tokens for similarity comparison."""
    stopwords = {
        "the", "and", "for", "with", "this", "that", "our", "your", "from",
        "have", "has", "been", "was", "are", "not", "please", "can", "hello",
        "dear", "team", "support", "ticket", "customer", "subject", "message"
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {w for w in words if w not in stopwords}


def check_duplicate(current_issue: str, current_text: str, current_cat: str, past_tickets: list[dict]) -> tuple[bool, str | None]:
    """
    Compares current ticket against previously triaged tickets using token overlap and SequenceMatcher.
    Returns (is_duplicate, similar_ticket_id).
    """
    curr_issue_tokens = get_tokens(current_issue)
    curr_text_tokens = get_tokens(current_text)

    best_match_id = None
    max_sim = 0.0

    for past in past_tickets:
        past_id = past["Ticket ID"]
        past_issue = past["Customer Issue"]
        past_text = past.get("Original Text", "")
        past_cat = past["Category"]

        past_issue_tokens = get_tokens(past_issue)
        past_text_tokens = get_tokens(past_text)

        # Jaccard + Sequence similarity on customer issue
        jaccard_issue = len(curr_issue_tokens & past_issue_tokens) / len(curr_issue_tokens | past_issue_tokens) if (curr_issue_tokens and past_issue_tokens) else 0.0
        seq_issue = SequenceMatcher(None, current_issue.lower(), past_issue.lower()).ratio()
        issue_sim = max(jaccard_issue, seq_issue)

        # Jaccard + Sequence similarity on full text
        jaccard_text = len(curr_text_tokens & past_text_tokens) / len(curr_text_tokens | past_text_tokens) if (curr_text_tokens and past_text_tokens) else 0.0
        seq_text = SequenceMatcher(None, current_text.lower(), past_text.lower()).ratio()
        text_sim = max(jaccard_text, seq_text)

        combined_sim = max(issue_sim, text_sim * 0.85)

        # Category alignment boost
        if current_cat == past_cat:
            combined_sim += 0.08

        if combined_sim > max_sim:
            max_sim = combined_sim
            best_match_id = past_id

    # Similarity threshold to declare a duplicate
    if max_sim >= 0.48:
        return True, best_match_id

    return False, None


# ---------------------------------------------------------
# Core Local Triage Function (Rule-Based Fallback)
# ---------------------------------------------------------
def triage_ticket(ticket_text: str) -> dict:
    """
    Performs deterministic rule-based triage on a single support ticket.
    Returns: category, priority (P1/P2/P3), customer_issue, missing_information, recommended_team.
    """
    text_lower = ticket_text.lower()

    # 1. Determine Category
    if any(k in text_lower for k in [
        "security breach", "data breach", "breach", "suspicious login", "unauthorized login",
        "unauthorized access", "unauthorized", "foreign ip", "unknown ip", "russian ip",
        "security alert", "compromised", "hacked", "malware", "phishing", "firewall",
        "terminate active sessions", "revoke session", "account takeover"
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

    recommended_team = TEAM_MAPPING.get(category, "General Support")

    # 2. Determine Priority (P1 / P2 / P3)
    priority = "P3"

    is_p1_security = (category == "Security")
    is_p1_billing = any(k in text_lower for k in ["charged twice", "unauthorized transaction", "duplicate charge", "fraudulent"])
    is_p1_outage = (
        any(k in text_lower for k in ["500 error", "internal server error", "outage", "system down", "completely down", "service down"])
        or (
            any(k in text_lower for k in ["down", "offline", "unresponsive", "cannot access"])
            and any(k in text_lower for k in ["multiple", "all users", "no users", "team members", "persistent", "completely"])
        )
    )
    is_p1_explicit = any(k in text_lower for k in ["major outage", "service completely unavailable", "critical system failure", "completely down"])

    if is_p1_security or is_p1_billing or is_p1_outage or is_p1_explicit:
        priority = "P1"

    elif (
        any(k in text_lower for k in ["locked out", "account locked", "cannot access account", "admin account"])
        or any(k in text_lower for k in ["typeerror", "cannot read properties", "export crashes", "blocking", "critical bug"])
        or any(k in text_lower for k in ["delayed over two weeks", "delayed two weeks", "lost package"])
        or any(k in text_lower for k in ["cannot cancel auto-renew", "unable to cancel", "stripe customer portal"])
        or ("500 error" in text_lower or "login problem" in text_lower)
        or ("payment" in text_lower and "failed" in text_lower)
    ):
        priority = "P2"

    else:
        priority = "P3"

    customer_issue = extract_customer_issue(ticket_text)
    missing_information = detect_missing_information(category, ticket_text)

    return {
        "category": category,
        "priority": priority,
        "customer_issue": customer_issue,
        "missing_information": missing_information,
        "recommended_team": recommended_team,
    }


# ---------------------------------------------------------
# Gemini AI Triage Function with Strict Error Safety
# ---------------------------------------------------------
def validate_ai_response(response_text: str) -> dict | None:
    """
    Validates Gemini output. Guarantees:
    - Valid JSON parsing (with markdown strip)
    - All required fields present
    - Category strictly in ALLOWED_CATEGORIES
    - Priority strictly in {'P1', 'P2', 'P3'}
    - Team strictly in ALLOWED_TEAMS
    Returns parsed dictionary or None if any check fails.
    """
    if not response_text:
        return None
    try:
        clean_str = response_text.strip()
        if clean_str.startswith("```"):
            clean_str = re.sub(r"^```(?:json)?\s*", "", clean_str)
            clean_str = re.sub(r"\s*```$", "", clean_str)

        data = json.loads(clean_str)

        required_keys = {"category", "priority", "customer_issue", "missing_information", "recommended_team"}
        if not required_keys.issubset(data.keys()):
            return None

        category = str(data["category"]).strip()
        priority = str(data["priority"]).strip()
        recommended_team = str(data["recommended_team"]).strip()
        customer_issue = str(data["customer_issue"]).strip()
        missing_information = str(data["missing_information"]).strip()

        if category not in ALLOWED_CATEGORIES:
            return None
        if priority not in ALLOWED_PRIORITIES:
            return None
        if recommended_team not in ALLOWED_TEAMS:
            return None

        return {
            "category": category,
            "priority": priority,
            "customer_issue": customer_issue,
            "missing_information": missing_information or "None",
            "recommended_team": recommended_team,
        }
    except Exception:
        return None


def ai_triage_ticket(ticket_text: str, api_key: str | None = None) -> dict | None:
    """
    Calls Google Gemini API to triage a ticket.
    Returns valid triage dict on success, or None on any failure (triggering local fallback).
    Never crashes the application.
    """
    if not api_key:
        return None

    prompt = (
        "You are an expert customer support ticket triaging engine.\n"
        "Analyze the following support ticket and return a JSON object with EXACTLY these fields:\n"
        "{\n"
        '  "category": "<one of: Billing, Account/Login, Technical Issue, Delivery, Security, Subscription, General Query>",\n'
        '  "priority": "<one of: P1, P2, P3>",\n'
        '  "customer_issue": "<concise 1-sentence summary of the customer\'s actual problem>",\n'
        '  "missing_information": "<missing details like Order ID, Transaction ID, browser info, or \'None\'>",\n'
        '  "recommended_team": "<one of: Billing & Payments, Account Support, Technical Support, Logistics, Security Team, Subscription Team, General Support>"\n'
        "}\n\n"
        "Priority Rules:\n"
        "- P1: Major outage, security incident, account compromise, unauthorized transaction, critical payment failure, service completely unavailable.\n"
        "- P2: Important functionality broken, significant account issue, repeated payment problem, significant delivery issue, important technical issue.\n"
        "- P3: General question, minor bug, refund request, password reset, general information.\n\n"
        "Team Mapping:\n"
        "- Billing -> Billing & Payments\n"
        "- Account/Login -> Account Support\n"
        "- Technical Issue -> Technical Support\n"
        "- Delivery -> Logistics\n"
        "- Security -> Security Team\n"
        "- Subscription -> Subscription Team\n"
        "- General Query -> General Support\n\n"
        "Rules:\n"
        "Return valid JSON only.\n"
        "Do not return markdown.\n"
        "Do not add extra fields.\n"
        "Use only the allowed values.\n\n"
        f"Ticket Content:\n{ticket_text}"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        if response and response.text:
            validated = validate_ai_response(response.text)
            if validated:
                return validated
    except Exception:
        return None

    return None


# ---------------------------------------------------------
# Batch Triage Orchestrator (with Duplicate Detection)
# ---------------------------------------------------------
def run_batch_triage(raw_text: str, api_key: str | None = None) -> tuple[list[dict], str]:
    """
    Parses tickets and runs triage on each.
    Performs duplicate detection against preceding tickets in the batch.
    """
    tickets = parse_tickets(raw_text)
    results = []
    ai_count = 0

    for idx, t in enumerate(tickets, start=1):
        triage_data = None
        source_label = "Local Fallback"

        # Attempt Gemini AI if key is present
        if api_key:
            try:
                triage_data = ai_triage_ticket(t, api_key=api_key)
                if triage_data:
                    source_label = "AI Classification"
                    ai_count += 1
            except Exception:
                triage_data = None

        # Fallback to local classifier if Gemini not used or failed
        if not triage_data:
            triage_data = triage_ticket(t)
            source_label = "Local Fallback"

        ticket_id = f"TKT-{idx:03d}"
        priority_code = triage_data["priority"]
        priority_label = f"{priority_code} - {PRIORITY_NAMES.get(priority_code, 'Normal')}"

        # Duplicate Detection against previously processed tickets
        is_dup, similar_id = check_duplicate(
            current_issue=triage_data["customer_issue"],
            current_text=t,
            current_cat=triage_data["category"],
            past_tickets=results,
        )

        duplicate_status = f"Yes ({similar_id})" if (is_dup and similar_id) else "No"

        results.append({
            "Ticket ID": ticket_id,
            "Category": triage_data["category"],
            "Priority": priority_label,
            "Customer Issue": triage_data["customer_issue"],
            "Missing Information": triage_data["missing_information"],
            "Recommended Team": triage_data["recommended_team"],
            "Duplicate": duplicate_status,
            "Similar Ticket": similar_id if is_dup else "None",
            "Classification": "AI" if source_label == "AI Classification" else "Local",
            "Original Text": t,
        })

    # Mode summary
    if ai_count > 0:
        mode = "AI Classification" if ai_count == len(tickets) else f"Hybrid ({ai_count} AI / {len(tickets) - ai_count} Local)"
    else:
        mode = "Local Fallback"

    return results, mode


# ---------------------------------------------------------
# API Key Discovery
# ---------------------------------------------------------
def get_gemini_api_key() -> str | None:
    """
    Retrieves Gemini API Key without crashing.
    Checks st.secrets['GEMINI_API_KEY'], then os.environ['GEMINI_API_KEY'].
    """
    try:
        if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
            val = str(st.secrets["GEMINI_API_KEY"]).strip()
            if val:
                return val
    except Exception:
        pass

    env_val = os.environ.get("GEMINI_API_KEY")
    if env_val and env_val.strip():
        return env_val.strip()

    return None


# ---------------------------------------------------------
# Header & Subtitle
# ---------------------------------------------------------
st.title("🎫 Support Ticket Prioritizer")
st.caption("Intelligent customer support ticket prioritization")
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
# Sidebar: Ticket Input & Controls
# ---------------------------------------------------------
st.sidebar.subheader(":material/inbox: Ticket Intake")

# 1. File Uploader for .txt and .csv tickets
uploaded_file = st.sidebar.file_uploader(
    "Upload support tickets (.txt, .csv)",
    type=["txt", "csv"],
    help="Upload a text file or CSV containing customer tickets"
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df_upload = pd.read_csv(uploaded_file)
            col_candidates = [c for c in df_upload.columns if any(k in c.lower() for k in ["ticket", "text", "message", "body", "issue", "desc", "subject"])]
            target_col = col_candidates[0] if col_candidates else df_upload.columns[0]
            file_content = "\n---\n".join(df_upload[target_col].dropna().astype(str).tolist())
        else:
            file_content = uploaded_file.read().decode("utf-8")
        st.session_state["ticket_input"] = file_content
    except Exception as e:
        st.sidebar.error(f"Error reading file: {e}")

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
    height=200,
    placeholder="Paste ticket subjects and bodies here (separated by '---' or newlines)..."
)

# 3. Action Button: Run Triage (Prominent primary button)
run_triage_clicked = st.sidebar.button("Run Triage", icon=":material/bolt:", type="primary", use_container_width=True)

# ---------------------------------------------------------
# Triage Processing State
# ---------------------------------------------------------
if run_triage_clicked:
    active_text = st.session_state.get("ticket_input", "").strip()
    if not active_text:
        st.sidebar.warning("No ticket content found. Please paste tickets or load samples.", icon=":material/warning:")
    else:
        with st.spinner("Triaging tickets..."):
            results_data, mode_str = run_batch_triage(active_text)
            st.session_state["triage_results"] = results_data
            st.session_state["classification_mode"] = mode_str
            st.sidebar.success(f"Triaged {len(results_data)} tickets", icon=":material/check_circle:")

# Initial run if no results yet exist in session
if "triage_results" not in st.session_state:
    initial_text = st.session_state.get("ticket_input", default_sample_text).strip()
    if initial_text:
        results_data, mode_str = run_batch_triage(initial_text)
        st.session_state["triage_results"] = results_data
        st.session_state["classification_mode"] = mode_str
    else:
        st.session_state["triage_results"] = []
        st.session_state["classification_mode"] = "Local Fallback"

# Prepare Dataframe & Dynamic Metrics
results = st.session_state.get("triage_results", [])
classification_mode = st.session_state.get("classification_mode", "Local Fallback")
df_tickets = pd.DataFrame(results)

if not df_tickets.empty:
    total_count = len(df_tickets)
    p1_count = int(df_tickets["Priority"].str.startswith("P1").sum())
    p2_count = int(df_tickets["Priority"].str.startswith("P2").sum())
    p3_count = int(df_tickets["Priority"].str.startswith("P3").sum())
    dup_count = int(df_tickets["Duplicate"].str.startswith("Yes").sum())
else:
    total_count = p1_count = p2_count = p3_count = dup_count = 0

# ---------------------------------------------------------
# Main Dashboard: Summary Metrics Cards
# ---------------------------------------------------------
st.subheader("📋 Support Ticket Overview")

with st.container(border=True):
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
        st.metric(
            label="Possible Duplicates",
            value=str(dup_count),
            delta=f"{dup_count} Flagged" if dup_count > 0 else "0 Detected",
            delta_color="off",
        )

# ---------------------------------------------------------
# Priority Legend Section
# ---------------------------------------------------------
with st.expander(":material/info: Priority Classification Guide", expanded=False):
    leg_col1, leg_col2, leg_col3 = st.columns(3)
    with leg_col1:
        st.markdown(":material/error: **P1 — Critical**")
        st.caption("Service outages, security alerts, unauthorized transactions, critical payment failures.")
    with leg_col2:
        st.markdown(":material/warning: **P2 — High**")
        st.caption("Feature broken, account locks, repeated payment errors, severe shipment delays.")
    with leg_col3:
        st.markdown(":material/check_circle: **P3 — Normal**")
        st.caption("General queries, minor bugs, refund requests, password resets, doc inquiries.")

st.divider()

# ---------------------------------------------------------
# Section: Dynamic Ticket Triage Results Table
# ---------------------------------------------------------
st.subheader("📋 Support Ticket Results")

if df_tickets.empty:
    st.info("No tickets have been triaged yet. Paste tickets or click 'Load Sample Tickets' and press 'Run Triage'.", icon=":material/info:")
else:
    # ---------------------------------------------------------
    # Priority Filter Controls (All, P1, P2, P3)
    # ---------------------------------------------------------
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        selected_priority = st.radio(
            "Filter by Priority:",
            options=["All", "P1", "P2", "P3"],
            horizontal=True,
            index=0,
            help="Filter table rows by priority tier",
        )

    # Filter Dataframe
    display_columns = [
        "Ticket ID",
        "Category",
        "Priority",
        "Customer Issue",
        "Missing Information",
        "Recommended Team",
        "Duplicate",
    ]
    df_display = df_tickets[display_columns]

    if selected_priority != "All":
        df_filtered = df_display[df_display["Priority"].str.startswith(selected_priority)]
    else:
        df_filtered = df_display

    with filter_col2:
        st.caption(f"Showing **{len(df_filtered)}** of **{len(df_display)}** tickets")

    # High-contrast color styling for visual distinguishability
    def style_priority(val):
        if "P1" in str(val):
            return "background-color: #ffebee; color: #c62828; font-weight: 700; border-radius: 4px;"
        elif "P2" in str(val):
            return "background-color: #fff3e0; color: #ef6c00; font-weight: 700; border-radius: 4px;"
        elif "P3" in str(val):
            return "background-color: #e8f5e9; color: #2e7d32; font-weight: 700; border-radius: 4px;"
        return ""

    def style_missing(val):
        if str(val) != "None":
            return "color: #d84315; font-weight: 700;"
        return "color: #757575;"

    def style_duplicate(val):
        if str(val).startswith("Yes"):
            return "color: #c62828; font-weight: 700;"
        return ""

    styled_df = (
        df_filtered.style
        .map(style_priority, subset=["Priority"])
        .map(style_missing, subset=["Missing Information"])
        .map(style_duplicate, subset=["Duplicate"])
    )

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

# ---------------------------------------------------------
# Feature 2: Clean Ticket Details Inspector
# ---------------------------------------------------------
if results:
    st.divider()
    st.subheader(":material/search: Ticket Details")

    ticket_options = [
        f"{r['Ticket ID']} — {r['Priority']} | {r['Category']} | {r['Customer Issue'][:50]}"
        for r in results
    ]

    selected_index = st.selectbox(
        "Select a ticket to inspect:",
        options=list(range(len(ticket_options))),
        format_func=lambda idx: ticket_options[idx],
        key="selected_ticket_idx",
        help="Select any ticket to view original customer message and missing information status.",
    )

    selected = results[selected_index]

    with st.container(border=True):
        top_c1, top_c2, top_c3, top_c4 = st.columns(4)

        with top_c1:
            st.markdown(f"**Ticket ID:** `{selected['Ticket ID']}`")
            st.markdown(f"**Priority:** {selected['Priority']}")

        with top_c2:
            st.markdown(f"**Category:** {selected['Category']}")
            st.markdown(f"**Assigned Team:** {selected['Recommended Team']}")

        with top_c3:
            if selected["Duplicate"].startswith("Yes"):
                st.markdown(f"**Duplicate:** :red[**{selected['Duplicate']}**]")
            else:
                st.markdown("**Duplicate:** :material/check_circle: None (Unique)")

        with top_c4:
            missing_val = selected["Missing Information"]
            if missing_val and missing_val != "None":
                st.markdown(f"**Information:** :orange[**:material/warning: Incomplete**]")
            else:
                st.markdown("**Information:** :green[**:material/check_circle: Complete**]")

        st.markdown("---")

        # Noticeable Missing Information Callout
        if missing_val and missing_val != "None":
            st.warning(f":material/warning: **Missing Information:** {missing_val} is required.", icon=":material/warning:")
        else:
            st.success(":material/check_circle: **Information Complete** — All required details are provided.", icon=":material/check_circle:")

        # Customer Issue Summary
        st.markdown(f"**Customer Issue Summary:**\n> {selected['Customer Issue']}")

        # Original Customer Message
        st.markdown("**Original Customer Message:**")
        msg_text = selected.get("Original Text", "").strip()
        escaped_msg = html.escape(msg_text)
        st.markdown(
            f"""<div style="padding: 12px 16px; border-radius: 6px; border: 1px solid rgba(128, 128, 128, 0.25); background: rgba(128, 128, 128, 0.08); line-height: 1.6; word-break: break-word; white-space: pre-wrap; font-family: inherit;">{escaped_msg}</div>""",
            unsafe_allow_html=True,
        )

# Subtle hackathon footer
st.markdown("<br><center><small style='color: gray;'>Support Ticket Prioritizer • Hackathon Prototype</small></center>", unsafe_allow_html=True)

