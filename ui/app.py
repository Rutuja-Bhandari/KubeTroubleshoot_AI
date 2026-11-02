import json
import requests
import streamlit as st


# -----------------------------------------
# Configuration
# -----------------------------------------

BACKEND_URL = "http://127.0.0.1:8000"


# -----------------------------------------
# Page configuration
# -----------------------------------------

st.set_page_config(
    page_title="KubeTroubleshoot AI",
    page_icon="K",
    layout="wide"
)


# -----------------------------------------
# Header
# -----------------------------------------

st.title("KubeTroubleshoot AI")
st.subheader(
    "Intelligent Kubernetes Troubleshooting Assistant"
)


# -----------------------------------------
# Backend health check
# -----------------------------------------

try:
    response = requests.get(
        f"{BACKEND_URL}/docs",
        timeout=5
    )

    backend_available = response.status_code == 200

except requests.RequestException:
    backend_available = False


if backend_available:
    st.success("FastAPI backend connected")
else:
    st.error(
        "FastAPI backend is not available. "
        "Start the backend first."
    )


# -----------------------------------------
# Input section
# -----------------------------------------

st.header("Incident Analysis")

namespace = st.text_input(
    "Namespace",
    value="default"
)

pod_name = st.text_input(
    "Pod Name"
)


# -----------------------------------------
# Analyze incident
# -----------------------------------------

if st.button(
    "Analyze Incident",
    type="primary"
):

    if not pod_name:
        st.warning(
            "Please enter a Pod name."
        )

    else:

        try:

            response = requests.get(
                f"{BACKEND_URL}/kubernetes/incidents/"
                f"{pod_name}/analyze",
                params={
                    "namespace": namespace
                },
                timeout=480
            )

            if response.status_code != 200:

                st.error(
                    f"Backend returned "
                    f"{response.status_code}"
                )

            else:

                result = response.json()

                st.session_state[
                    "analysis"
                ] = result

        except requests.RequestException as e:

            st.error(
                f"Unable to connect to backend: {e}"
            )


# -----------------------------------------
# Display analysis
# -----------------------------------------

if "analysis" in st.session_state:

    result = st.session_state[
        "analysis"
    ]

    health = result.get(
        "health",
        {}
    )

    rca = result.get(
        "root_cause_analysis"
    )

    metrics = result.get(
        "metrics"
    )

    anomaly = result.get(
        "anomaly"
    )


    # -------------------------------------
    # Health
    # -------------------------------------

    st.header("Incident Status")

    health_status = health.get(
        "status",
        "UNKNOWN"
    )

    if health_status == "HEALTHY":

        st.success(
            "HEALTHY"
        )

    elif health_status == "UNHEALTHY":

        st.error(
            "UNHEALTHY"
        )

    else:

        st.warning(
            health_status
        )


    # -------------------------------------
    # Health issues
    # -------------------------------------

    issues = health.get(
        "issues",
        []
    )

    if issues:

        st.subheader(
            "Detected Issues"
        )

        for issue in issues:

            st.write(
                f"- {issue}"
            )


    # -------------------------------------
    # RCA
    # -------------------------------------

    if rca:

        st.header(
            "Root Cause Analysis"
        )

        if "error" in rca:

            st.error(
                "RCA generation failed"
            )

            st.write(
                rca.get(
                    "raw_response",
                    ""
                )
            )

        else:

            col1, col2 = st.columns(2)

            with col1:

                st.subheader(
                    "Root Cause"
                )

                st.write(
                    rca.get(
                        "root_cause",
                        "Not available"
                    )
                )

            with col2:

                st.subheader(
                    "Confidence"
                )

                st.write(
                    rca.get(
                        "confidence",
                        "Not available"
                    )
                )


            st.subheader(
                "Impact"
            )

            st.write(
                rca.get(
                    "impact",
                    "Not available"
                )
            )


            # ---------------------------------
            # Evidence
            # ---------------------------------

            st.subheader(
                "Evidence"
            )

            evidence = rca.get(
                "evidence",
                []
            )

            for item in evidence:

                st.write(
                    f"- {item}"
                )


            # ---------------------------------
            # Recommended fix
            # ---------------------------------

            st.subheader(
                "Recommended Fix"
            )

            fixes = rca.get(
                "recommended_fix",
                []
            )

            for fix in fixes:

                st.write(
                    f"- {fix}"
                )


            # ---------------------------------
            # Investigation commands
            # ---------------------------------

            st.subheader(
                "Investigation Commands"
            )

            commands = rca.get(
                "investigation_commands",
                []
            )

            for command in commands:

                st.code(
                    command,
                    language="powershell"
                )


            # ---------------------------------
            # Verification
            # ---------------------------------

            st.subheader(
                "Verification Steps"
            )

            verification = rca.get(
                "verification_steps",
                []
            )

            for step in verification:

                st.write(
                    f"- {step}"
                )


            # ---------------------------------
            # Prevention
            # ---------------------------------

            st.subheader(
                "Prevention"
            )

            prevention = rca.get(
                "prevention",
                []
            )

            for item in prevention:

                st.write(
                    f"- {item}"
                )


    # -------------------------------------
    # Metrics
    # -------------------------------------

    if metrics:

        st.header(
            "Prometheus Metrics"
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            cpu_usage = metrics.get("cpu_usage")
            st.metric(
                "CPU Usage",
                cpu_usage if cpu_usage is not None else "Unavailable"
            )

        with col2:
            memory_usage = metrics.get("memory_usage")
            st.metric(
                "Memory Usage",
                memory_usage if memory_usage is not None else "Unavailable"
            )

        with col3:

            st.metric(
                "Restart Count",
                metrics.get(
                    "restart_count",
                    0
                )
            )


    # -------------------------------------
    # ML Anomaly
    # -------------------------------------

    if anomaly:

        st.header(
            "ML Anomaly Detection"
        )

        anomaly_data = anomaly.get(
            "anomaly"
        )

        if anomaly_data:

            st.write(
                "Status:",
                anomaly_data.get(
                    "status"
                )
            )

            st.write(
                "Anomaly Score:",
                anomaly_data.get(
                    "anomaly_score"
                )
            )

        else:

            st.info(
                anomaly.get(
                    "reason",
                    "Anomaly detection unavailable."
                )
            )


    # -------------------------------------
    # Remediation
    # -------------------------------------

    st.header("Remediation Actions")

    # Use the pod and namespace associated with the analysis.
    analyzed_pod = result.get("pod", pod_name)
    analyzed_namespace = result.get(
        "namespace",
        namespace
    )

    if not analyzed_pod:
        st.info("Analyze a pod to view remediation actions.")

    else:
        try:
            remediation_response = requests.get(
                f"{BACKEND_URL}/kubernetes/incidents/"
                f"{analyzed_pod}/remediation",
                params={
                    "namespace": analyzed_namespace
                },
                timeout=480
            )

            if remediation_response.status_code == 200:
                remediation = remediation_response.json()

                actions = remediation.get("actions", [])

                if actions:
                    for index, action in enumerate(actions):
                        action_id = action.get(
                            "action_id",
                            f"Action {index + 1}"
                        )

                        with st.expander(action_id):
                            st.write(
                                "Description:",
                                action.get(
                                    "description",
                                    "Not available"
                                )
                            )

                            st.write(
                                "Action Type:",
                                action.get(
                                    "action_type",
                                    "Not available"
                                )
                            )

                            st.write(
                                "Risk:",
                                action.get(
                                    "risk_level",
                                    "Not specified"
                                )
                            )

                            st.write(
                                "Reason:",
                                action.get(
                                    "reason",
                                    "Not specified"
                                )
                            )

                            command = action.get("command")

                            if command:
                                st.code(
                                    command,
                                    language="powershell"
                                )

                            if action.get("requires_approval"):
                                st.warning(
                                    "Human approval is required before execution."
                                )

                                proposal_id = action.get("proposal_id")

                                if not proposal_id:
                                    st.info(
                                        "Approval is unavailable because the backend "
                                        "did not return a proposal ID. Update the "
                                        "generate_remediation endpoint first."
                                    )
                                else:
                                    if st.button(
                                        "Approve & Execute",
                                        key=f"approve_{proposal_id}"
                                    ):
                                        try:
                                            approval_response = requests.post(
                                                f"{BACKEND_URL}/kubernetes/remediation/"
                                                f"{proposal_id}/approve",
                                                timeout=480
                                            )

                                            if approval_response.status_code == 200:
                                                approval_result = approval_response.json()

                                                st.success(
                                                    "Remediation request processed."
                                                )
                                                st.json(approval_result)

                                            else:
                                                st.error(
                                                    f"Approval failed: HTTP "
                                                    f"{approval_response.status_code}"
                                                )
                                                st.code(approval_response.text)

                                        except requests.RequestException as exc:
                                            st.error(
                                                "Unable to connect to the approval API."
                                            )
                                            st.caption(str(exc))

                            elif action.get("action_type") == "INVESTIGATION":
                                st.info(
                                    "Investigation action. Review the command and "
                                    "evidence before running it."
                                )

                else:
                    st.info(
                        "No remediation actions are available "
                        "for this incident. Review the RCA and "
                        "Kubernetes evidence."
                    )

                    if remediation.get("message"):
                        st.caption(remediation["message"])

            else:
                st.error(
                    "The remediation API returned HTTP "
                    f"{remediation_response.status_code}."
                )
                st.code(remediation_response.text)

        except requests.RequestException as e:
            st.error(
                "Unable to connect to the remediation API."
            )
            st.caption(str(e))