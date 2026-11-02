
def evaluate_incident(incident_context):
    """
    Evaluate whether the Kubernetes Pod
    has an active incident.

    Checks:
    1. Pod status
    2. Container state and readiness
    3. Kubernetes events
    4. Deployment availability

    Duplicate Kubernetes event issue messages are
    reported only once per event reason. The original
    event history in incident_context remains unchanged.
    """

    pod_details = incident_context.get(
        "pod_details",
        {}
    )

    container_states = incident_context.get(
        "container_states",
        []
    )

    events = incident_context.get(
        "events",
        []
    )

    deployments = incident_context.get(
        "deployments",
        []
    )

    pod_status = pod_details.get(
        "status"
    )

    issues = []

    # ---------------------------------
    # 1. Check Pod Status
    # ---------------------------------

    unhealthy_pod_statuses = [
        "Failed",
        "Unknown",
        "Pending"
    ]

    if pod_status in unhealthy_pod_statuses:
        issues.append(
            f"Pod status is {pod_status}"
        )

    # ---------------------------------
    # 2. Check Container State
    # ---------------------------------

    unhealthy_states = [
        "waiting",
        "terminated"
    ]

    for container in container_states:

        state = container.get("state")
        reason = container.get("reason")
        ready = container.get("ready")
        container_name = container.get("name")

        if state in unhealthy_states:

            issue = (
                f"Container {container_name} "
                f"is in {state} state"
            )

            if reason:
                issue += f": {reason}"

            issues.append(issue)

        # Running but not ready

        if state == "running" and not ready:

            issues.append(
                f"Container {container_name} "
                "is running but not ready"
            )

    # ---------------------------------
    # 3. Check Kubernetes Events
    # ---------------------------------

    error_event_reasons = {
        "Failed",
        "FailedScheduling",
        "FailedMount",
        "FailedPull",
        "BackOff",
        "Unhealthy"
    }

    # Track reported event reasons to avoid
    # duplicate issue messages.
    reported_event_reasons = set()

    for event in events:

        reason = event.get("reason", "")

        if (
            reason in error_event_reasons
            and reason not in reported_event_reasons
        ):

            issues.append(
                f"Kubernetes event: {reason}"
            )

            reported_event_reasons.add(reason)

    # ---------------------------------
    # 4. Check Deployment Health
    # ---------------------------------

    for deployment in deployments:

        desired = deployment.get(
            "desired_replicas"
        )

        available = deployment.get(
            "available_replicas"
        )

        if (
            desired is not None
            and available is not None
            and available < desired
        ):

            issues.append(
                f"Deployment {deployment.get('name')} "
                f"has {available}/{desired} "
                "available replicas"
            )

    # ---------------------------------
    # 5. Return Health Result
    # ---------------------------------

    if not issues:

        return {
            "status": "HEALTHY",
            "incident_detected": False,
            "issues": [],
            "message": (
                "No active Kubernetes incident "
                "detected. Pod appears healthy."
            )
        }

    return {
        "status": "UNHEALTHY",
        "incident_detected": True,
        "issues": issues,
        "message": (
            "Kubernetes incident detected."
        )
    }
