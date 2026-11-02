import streamlit as st
import requests


# --------------------------------------------------
# Page Configuration
# --------------------------------------------------

st.set_page_config(
    page_title="KubeTroubleshoot AI",
    page_icon="☸️",
    layout="wide"
)


# --------------------------------------------------
# Backend Configuration
# --------------------------------------------------

BACKEND_URL = "http://127.0.0.1:8000"


# --------------------------------------------------
# Functions
# --------------------------------------------------

def check_backend_health():
    try:
        response = requests.get(
            f"{BACKEND_URL}/health",
            timeout=5
        )

        if response.status_code == 200:
            return True

        return False

    except requests.exceptions.RequestException:
        return False


# --------------------------------------------------
# Application Header
# --------------------------------------------------

st.title("☸️ KubeTroubleshoot AI")

st.subheader("Intelligent Kubernetes Troubleshooting Assistant")

st.write(
    "KubeTroubleshoot AI automatically investigates Kubernetes "
    "incidents, analyzes logs, events, metrics, and provides "
    "AI-powered root cause analysis."
)


# --------------------------------------------------
# Cluster Overview
# --------------------------------------------------

st.divider()

st.header("Cluster Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Cluster Status",
        value="Not Connected"
    )

with col2:
    st.metric(
        label="Running Pods",
        value="0"
    )

with col3:
    st.metric(
        label="Failed Pods",
        value="0"
    )

with col4:
    st.metric(
        label="Active Incidents",
        value="0"
    )


# --------------------------------------------------
# Incident Investigation
# --------------------------------------------------

st.divider()

st.header("Incident Investigation")

st.write(
    "Click the button below to investigate unhealthy "
    "Kubernetes workloads."
)

if st.button("🔍 Analyze Incident", type="primary"):

    st.info(
        "Incident investigation will be implemented "
        "in the upcoming steps."
    )


# --------------------------------------------------
# System Status
# --------------------------------------------------

st.divider()

st.header("System Status")

status_col1, status_col2 = st.columns(2)

backend_healthy = check_backend_health()

with status_col1:

    if backend_healthy:
        st.success("Streamlit Frontend: Running")

    else:
        st.error("Streamlit Frontend: Running")


with status_col2:

    if backend_healthy:
        st.success("FastAPI Backend: Connected")

    else:
        st.error("FastAPI Backend: Not Connected")