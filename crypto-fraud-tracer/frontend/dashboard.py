"""
Crypto Fraud Wallet Tracer — Investigator Dashboard
Streamlit-based triage tool for law enforcement investigators.

Run from project root:
    .\venv\Scripts\streamlit.exe run frontend/dashboard.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Path setup: ensure the project root is on sys.path so "backend.*" imports
# resolve correctly regardless of where Streamlit launches the script from.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.trace_engine import trace_wallet
from backend.tron_trace_engine import trace_tron_wallet
from backend.bitcoin_trace_engine import trace_bitcoin_wallet, is_bitcoin_address
from backend.exchange_match import annotate_tree
from backend.risk_score import calculate_risk_score
from backend.correlation import find_convergence
from backend.graph_builder import build_graph_html
from backend.utils import is_ethereum_address, is_tron_address
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TRACE-X Crypto Tracer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');

* {
    font-family: 'JetBrains Mono', monospace !important;
    border-radius: 0px !important;
    box-shadow: none !important;
}

/* Base colors */
.stApp {
    background-color: #0a0a0a !important;
    color: #e8e8e8 !important;
}

/* Headers */
h1, h2, h3, h4, h5, h6 {
    color: #e8e8e8 !important;
    text-transform: uppercase !important;
    letter-spacing: 1.5px !important;
    font-weight: 600 !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0a0a0a !important;
    border-right: 1px solid #2a2a2a !important;
}

/* Cards/Containers */
div[data-testid="stExpander"],
div[data-testid="stMetric"],
div[data-testid="stAlert"] {
    background-color: #131313 !important;
    border: 1px solid #2a2a2a !important;
}

/* Buttons */
button[kind="primary"], div.stButton > button {
    background-color: transparent !important;
    border: 1px solid #00ff9d !important;
    color: #00ff9d !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
button[kind="primary"]:hover, div.stButton > button:hover {
    background-color: #00ff9d !important;
    color: #000000 !important;
}

/* Muted text scoped */
.stCaption, small, p.st-caption {
    color: #888888 !important;
}

/* Additional inputs/tables styling just for consistency (sharp, dark) */
input[type="text"], input[type="number"], div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
    background-color: #131313 !important;
    border: 1px solid #2a2a2a !important;
    color: #e8e8e8 !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "cases" not in st.session_state:
    st.session_state.cases = []  # list of case result dicts

if "convergence" not in st.session_state:
    st.session_state.convergence = []  # convergence findings list


# ===================================================================
# Helper: colour-code a risk score
# ===================================================================
def risk_color(score: int) -> str:
    """Return a colour string based on risk-score thresholds."""
    if score > 60:
        return "red"
    if score >= 30:
        return "orange"
    return "green"


def risk_emoji(score: int) -> str:
    if score > 60:
        return "🔴"
    if score >= 30:
        return "🟡"
    return "🟢"




# ===================================================================
# Helper: recursively render a trace tree as nested expanders
# ===================================================================
def render_tree_node(node: dict, chain: str = "ethereum", depth: int = 0):
    """Render a single trace-tree node and recurse into its children."""
    addr = node.get("to_address") or node.get("address", "?")
    hop = node.get("hop_number", 0)
    value = node.get("value_eth")
    exchange = node.get("exchange_match")
    obf = node.get("obfuscation", {})
    
    unit = "ETH"
    if chain == "bitcoin":
        unit = "BTC"
    elif chain == "tron":
        unit = "TRX"

    # Build a compact label for the expander
    parts = [f"**Hop {hop}** — `{addr}`"]
    if value is not None:
        parts.append(f"({value:.6f} {unit})")
    if exchange:
        parts.append(f"🏦 **{exchange}**")
    if obf.get("is_obfuscated"):
        parts.append(f"⚠️ {obf.get('type','?').upper()}: {obf.get('name','')}")

    label = "  ".join(parts)
    children = node.get("children", [])

    if children:
        with st.expander(label, expanded=(depth < 2)):
            tx_hash = node.get("tx_hash")
            ts = node.get("timestamp")
            if tx_hash:
                st.caption(f"tx: `{tx_hash}`")
            if ts and ts != "0":
                try:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    st.caption(f"timestamp: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                except (ValueError, OSError):
                    st.caption(f"timestamp: {ts}")
            for child in children:
                render_tree_node(child, chain, depth + 1)
    else:
        # Leaf node — just display, no expander needed
        st.markdown(f"{'&nbsp;' * 4 * depth}{label}", unsafe_allow_html=True)
        tx_hash = node.get("tx_hash")
        if tx_hash:
            st.caption(f"{'  ' * depth}tx: `{tx_hash}`")


# ===================================================================
# Sidebar — case submission form
# ===================================================================
st.sidebar.title("📋 Submit New Case")
st.sidebar.markdown("Enter the details for a reported wallet to begin tracing.")

with st.sidebar.form("case_form", clear_on_submit=True):
    case_id = st.text_input("Case ID", placeholder="e.g. CASE-2024-001")
    wallet_address = st.text_input("Reported Wallet Address", placeholder="0x... or T...")
    max_hops = st.number_input("Max Hops", min_value=1, max_value=5, value=3, step=1)
    submitted = st.form_submit_button("🚀 Trace Wallet")

if submitted:
    wallet_address_clean = wallet_address.strip()
    
    # --- Input validation ---
    is_eth = is_ethereum_address(wallet_address_clean)
    is_tron = is_tron_address(wallet_address_clean)
    is_btc = is_bitcoin_address(wallet_address_clean)
    
    if not case_id.strip():
        st.sidebar.error("Case ID cannot be empty.")
    elif not wallet_address_clean:
        st.sidebar.error("Wallet address cannot be empty.")
    elif not (is_eth or is_tron or is_btc):
        st.sidebar.error("Invalid address format. Must be an Ethereum, TRON, or Bitcoin address.")
    elif any(c["case_id"] == case_id.strip() for c in st.session_state.cases):
        st.sidebar.error(f"Case ID **{case_id.strip()}** already exists. Use a unique ID.")
    else:
        if is_eth:
            chain = "ethereum"
        elif is_tron:
            chain = "tron"
        else:
            chain = "bitcoin"
        
        # --- Run the full pipeline ---
        try:
            with st.sidebar.status(f"Tracing {chain.capitalize()} wallet…", expanded=True) as status:
                st.write(f"Fetching transactions for `{wallet_address_clean}` (max {max_hops} hops)…")
                
                if chain == "ethereum":
                    raw_tree = trace_wallet(wallet_address_clean, max_hops=int(max_hops))
                    st.write("Matching exchange addresses…")
                    annotated = annotate_tree(raw_tree, chain=chain)
                elif chain == "tron":
                    raw_tree = trace_tron_wallet(wallet_address_clean, max_hops=int(max_hops))
                    st.write("Matching exchange addresses…")
                    annotated = annotate_tree(raw_tree, chain=chain)
                else:
                    st.write("Matching exchange addresses…")
                    # Bitcoin trace engine does exchange matching inline to truncate correctly
                    annotated = trace_bitcoin_wallet(wallet_address_clean, max_hops=int(max_hops))

                st.write("Calculating risk score & obfuscation…")
                scored_tree, summary = calculate_risk_score(annotated)

                case_result = {
                    "case_id": case_id.strip(),
                    "reported_address": wallet_address_clean,
                    "chain": chain,
                    "max_hops": int(max_hops),
                    "trace_tree": scored_tree,
                    "summary": summary,
                }
                st.session_state.cases.append(case_result)
                # Clear cached convergence since a new case was added
                st.session_state.convergence = []
                status.update(label="✅ Trace complete!", state="complete", expanded=False)

        except Exception as e:
            st.sidebar.error(f"Pipeline error: {e}")

# Show case count in sidebar
if st.session_state.cases:
    st.sidebar.divider()
    st.sidebar.metric("Cases in session", len(st.session_state.cases))


# ===================================================================
# Main panel — header
# ===================================================================
st.title("🔍 TRACE-X Crypto Fraud Wallet Tracer")
st.markdown(
    "_An investigator dashboard by **TRACE-X** for tracing cryptocurrency fund flows, identifying exchange "
    "off-ramps, mixer/bridge obfuscation, and cross-case convergence patterns. "
    "Designed as a triage tool for law enforcement and compliance teams._"
)
st.divider()

# ===================================================================
# Main panel — submitted cases table
# ===================================================================
if not st.session_state.cases:
    st.info("No cases submitted yet. Use the sidebar to trace a reported wallet address.")
else:
    st.subheader("📊 Case Overview")

    # Build a table of all submitted cases
    table_rows = []
    for c in st.session_state.cases:
        s = c["summary"]
        table_rows.append(
            {
                "Case ID": c["case_id"],
                "Reported Address": c["reported_address"],
                "Hops": c["max_hops"],
                "Risk Score": s["risk_score"],
                "Reached Exchange": ", ".join(s["exchange_names"]) if s["reached_exchange"] else "No",
                "Obfuscation": ", ".join(s["obfuscation_types"]) if s["obfuscation_detected"] else "None",
            }
        )

    # Sort by risk score descending
    table_rows.sort(key=lambda r: r["Risk Score"], reverse=True)
    st.table(table_rows)

    # ---------------------------------------------------------------
    # Summary cards for each case
    # ---------------------------------------------------------------
    st.subheader("📝 Case Summaries")
    cols_per_row = 3
    for idx in range(0, len(st.session_state.cases), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, col in enumerate(cols):
            case_idx = idx + col_idx
            if case_idx >= len(st.session_state.cases):
                break
            c = st.session_state.cases[case_idx]
            s = c["summary"]
            score = s["risk_score"]
            emoji = risk_emoji(score)
            color = risk_color(score)

            with col:
                st.markdown(
                    f"#### {emoji} {c['case_id']}\n"
                    f"**Address:** `{c['reported_address']}`\n\n"
                    f"**Risk Score:** :{color}[**{score}/100**]\n\n"
                    f"**Exchange:** {'✅ ' + ', '.join(s['exchange_names']) if s['reached_exchange'] else '❌ None'}\n\n"
                    f"**Obfuscation:** {'⚠️ ' + ', '.join(s['obfuscation_types']) if s['obfuscation_detected'] else '✅ None detected'}"
                )
                st.divider()

    # ---------------------------------------------------------------
    # Correlation analysis
    # ---------------------------------------------------------------
    st.subheader("🔗 Cross-Case Correlation Analysis")

    if len(st.session_state.cases) < 2:
        st.info("At least 2 cases are needed to run correlation analysis.")
    else:
        if st.button("Run Correlation Analysis"):
            print("BUTTON CLICKED", flush=True)
            case_results_for_conv = []
            for c in st.session_state.cases:
                case_results_for_conv.append({
                    "case_id": c["case_id"],
                    "reported_address": c["reported_address"],
                    "trace_tree": c["trace_tree"],
                    "summary": c["summary"],
                })
            
            conv_result = find_convergence(case_results_for_conv)
            st.session_state.convergence = conv_result
            print("CONVERGENCE RESULT:", conv_result, flush=True)

        if st.session_state.convergence:
            st.success(f"Found **{len(st.session_state.convergence)}** convergence point(s) across submitted cases.")
            for f in st.session_state.convergence:
                case_list = ", ".join(f["case_ids"])
                exchange_tag = f" — 🏦 **{f['exchange_name']}**" if f["is_exchange"] else ""
                st.warning(
                    f"⚠️ **{f['num_cases']} cases** converge on address "
                    f"`{f['address']}`{exchange_tag}\n\n"
                    f"Cases: {case_list}"
                )
        elif isinstance(st.session_state.convergence, list) and len(st.session_state.convergence) == 0:
            st.info("Analysis complete — no convergence points found between the submitted cases.")

    # ---------------------------------------------------------------
    # Detailed trace tree viewer
    # ---------------------------------------------------------------
    st.divider()
    st.subheader("🌳 Fund-Flow Trace Viewer")

    case_options = {c["case_id"]: i for i, c in enumerate(st.session_state.cases)}
    selected_case_id = st.selectbox("Select a case to inspect:", options=list(case_options.keys()))

    if selected_case_id:
        selected_case = st.session_state.cases[case_options[selected_case_id]]
        tree = selected_case["trace_tree"]
        s = selected_case["summary"]

        # Quick summary bar
        score = s["risk_score"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Risk Score", f"{score}/100")
        c2.metric("Exchanges Found", len(s["exchange_names"]) if s["exchange_names"] else 0)
        c3.metric("Obfuscation Types", len(s["obfuscation_types"]) if s["obfuscation_types"] else 0)
        c4.metric("Max Hops Traced", selected_case["max_hops"])


        # Render tree as nested expanders
        st.markdown("##### Trace Tree")
        render_tree_node(tree, chain=selected_case.get("chain", "ethereum"))

        # Also provide the raw JSON behind a toggle
        with st.expander("📄 Raw JSON trace data"):
            st.json(tree)
            
        # ---------------------------------------------------------------
        # Pyvis Interactive Graph Visualization
        # ---------------------------------------------------------------
        st.divider()
        st.subheader("🕸️ Fund-Flow Graph")
        st.markdown(
            "**Legend:** "
            "<span style='display:inline-block;width:10px;height:10px;background-color:#a78bfa;margin-right:5px;'></span>[REPORTED ADDRESS (ORIGIN)] &nbsp;&nbsp;|&nbsp;&nbsp; "
            "🔵 Normal wallet &nbsp;&nbsp;|&nbsp;&nbsp; "
            "🔴 Known Exchange &nbsp;&nbsp;|&nbsp;&nbsp; "
            "🟠 Mixer/Bridge (obfuscation detected)",
            unsafe_allow_html=True
        )
        graph_placeholder = st.empty()
        try:
            with st.spinner("Generating interactive graph..."):

                graph_html = build_graph_html(tree, chain=selected_case.get("chain", "ethereum"))
                
            graph_placeholder.empty()  # clear any previous content first
            with graph_placeholder.container():
                components.html(graph_html, height=700, scrolling=False)
        except Exception as e:
            graph_placeholder.warning(f"Failed to render interactive graph: {e}")
