from ai.rag.retriever import search_knowledge_base



def build_search_query(incident_context):
    """
    Build a focused RAG query using Kubernetes
    failure signals, previous termination details,
    and relevant events and logs.
    """

    pod_details = incident_context.get(
        "pod_details", {}
    )

    container_states = incident_context.get(
        "container_states", []
    )

    events = incident_context.get(
        "events", []
    )

    query_parts = []

    def add_signal(signal):
        if signal and signal not in query_parts:
            query_parts.append(signal)

    # ---------------------------------------------
    # 1. Pod status
    # ---------------------------------------------

    pod_status = pod_details.get("status")

    if pod_status and pod_status not in (
        "Running",
        "Succeeded"
    ):
        add_signal(f"Pod status: {pod_status}")

    # ---------------------------------------------
    # 2. Current container state and reason
    # ---------------------------------------------

    for container in container_states:
        name = container.get("name")
        state = container.get("state")
        reason = container.get("reason")
        message = container.get("message")

        prefix = f"Container {name}" if name else "Container"

        if reason:
            add_signal(
                f"{prefix} current reason: {reason}"
            )

        if state in ("waiting", "terminated"):
            add_signal(
                f"{prefix} state: {state}"
            )

        if message and reason not in (
            "CrashLoopBackOff",
            "ImagePullBackOff"
        ):
            add_signal(
                f"{prefix} message: {message}"
            )

        # -----------------------------------------
        # 3. Previous termination — critical signal
        # -----------------------------------------

        last_termination = container.get(
            "last_termination",
            {}
        )

        termination_reason = last_termination.get(
            "reason"
        )

        exit_code = last_termination.get(
            "exit_code"
        )

        termination_message = last_termination.get(
            "message"
        )

        if termination_reason:
            add_signal(
                f"Previous container termination reason: "
                f"{termination_reason}"
            )

        if exit_code is not None:
            add_signal(
                f"Previous container termination exit code: "
                f"{exit_code}"
            )

        if termination_message:
            add_signal(
                f"Previous termination message: "
                f"{termination_message}"
            )

        # Add targeted context for known failure types.
        if termination_reason == "OOMKilled":
            add_signal(
                "Kubernetes container memory limit exceeded "
                "or out-of-memory termination; investigate "
                "OOMKilled, memory limits, memory usage, "
                "and exit code 137"
            )

        elif termination_reason == "Error" and exit_code == 137:
            add_signal(
                "Container exited with code 137; investigate "
                "SIGKILL and possible out-of-memory termination"
            )

    # ---------------------------------------------
    # 4. Relevant Kubernetes events only
    # ---------------------------------------------

    relevant_event_reasons = {
        "OOMKilling",
        "BackOff",
        "Failed",
        "FailedScheduling",
        "FailedMount",
        "FailedAttachVolume",
        "FailedCreate",
        "FailedPull",
        "ErrImagePull",
        "ImagePullBackOff",
        "Unhealthy",
        "Evicted",
        "FailedToStartContainer",
    }

    relevant_event_keywords = (
        "oomkilled",
        "out of memory",
        "memory",
        "failed to pull",
        "imagepullbackoff",
        "errimagepull",
        "failedmount",
        "failed scheduling",
        "failed to create",
        "probe failed",
        "liveness",
        "readiness",
        "insufficient memory",
        "insufficient cpu",
    )

    for event in events:
        reason = event.get("reason", "")
        message = event.get("message", "")

        text = f"{reason} {message}".lower()

        is_relevant = (
            reason in relevant_event_reasons
            or any(
                keyword in text
                for keyword in relevant_event_keywords
            )
        )

        if not is_relevant:
            continue

        if reason:
            add_signal(f"Relevant event reason: {reason}")

        if message:
            add_signal(f"Relevant event message: {message}")

    # ---------------------------------------------
    # 5. Relevant log evidence
    # ---------------------------------------------

    logs = incident_context.get("logs", "")

    failure_keywords = [
        "OOMKilled",
        "out of memory",
        "MemoryError",
        "memory limit",
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "FailedMount",
        "FailedScheduling",
        "Connection refused",
        "probe failed",
        "Unhealthy",
        "permission denied",
        "no such file or directory",
    ]

    for keyword in failure_keywords:
        if keyword.lower() in logs.lower():
            add_signal(
                f"Log failure indicator: {keyword}"
            )

    # ---------------------------------------------
    # 6. Return focused search query
    # ---------------------------------------------

    return " ".join(query_parts)


def retrieve_incident_knowledge(
    incident_context,
    top_k=3
):
    """
    Retrieve knowledge relevant to the
    current Kubernetes incident.
    """

    query = build_search_query(
        incident_context
    )

    if not query.strip():
        return {
            "query": "",
            "results": []
        }

    results = search_knowledge_base(
        query,
        top_k=top_k
    )

    formatted_results = []

    for document in results:

        formatted_results.append({
            "source": document.metadata.get(
                "source"
            ),
            "content": document.page_content
        })

    return {
        "query": query,
        "results": formatted_results
    }