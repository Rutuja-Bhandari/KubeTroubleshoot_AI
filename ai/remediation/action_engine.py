
from ai.remediation.action_models import RemediationAction


class RemediationEngine:

    def generate_actions(
        self,
        incident_context,
        rca
    ):
        actions = []

        # Safely read the RCA and incident context.
        rca = rca or {}
        incident_context = incident_context or {}

        root_cause = str(
            rca.get("root_cause", "") or ""
        ).lower()

        pod_details = (
            incident_context.get("pod_details", {}) or {}
        )

        pod_name = pod_details.get("name")
        namespace = pod_details.get("namespace", "default")

        # Do not generate actions without a valid pod name.
        if not pod_name or not root_cause:
            return actions

        metadata = {
            "pod_name": pod_name,
            "namespace": namespace
        }

        container_states = (
            incident_context.get("container_states", []) or []
        )

        events = incident_context.get("events", []) or []

        # Detect restart-related problems using both the RCA
        # and Kubernetes evidence.
        has_crashloop_state = any(
            "crashloopbackoff" in str(
                container.get("reason", "")
            ).lower()
            for container in container_states
        )

        has_backoff_event = any(
            (
                "backoff" in str(
                    event.get("reason", "")
                ).lower()
                or "back-off restarting failed container"
                in str(event.get("message", "")).lower()
            )
            for event in events
        )

        has_repeated_restarts = any(
            int(container.get("restart_count") or 0) > 0
            for container in container_states
        )

        has_restart_issue = (
            "crashloopbackoff" in root_cause
            or has_crashloop_state
            or (
                has_backoff_event
                and has_repeated_restarts
            )
        )

        # Helper for creating investigation actions.
        def add_investigation(
            action_id,
            description,
            command,
            reason
        ):
            actions.append(
                RemediationAction(
                    action_id=action_id,
                    action_type="INVESTIGATION",
                    description=description,
                    command=command,
                    risk_level="LOW",
                    requires_approval=False,
                    reason=reason,
                    metadata=metadata.copy()
                )
            )

        # Rule 1: CrashLoopBackOff or repeated container failures.
        # Investigate first; do not assume restarting the pod
        # will fix the underlying cause.
        if has_restart_issue:

            add_investigation(
                "CHECK_LOGS",
                "Inspect available container logs for the failure message.",
                (
                    f"kubectl logs {pod_name} "
                    f"-n {namespace} --tail=100"
                ),
                (
                    "Use the application logs to identify the failure "
                    "message and correlate it with the container "
                    "termination status."
                )
            )

            add_investigation(
                "DESCRIBE_POD",
                (
                    "Inspect pod events, container state, last "
                    "termination reason, exit code, and restart history."
                ),
                f"kubectl describe pod {pod_name} -n {namespace}",
                (
                    "Determine why the container is restarting using "
                    "Kubernetes status and event evidence before "
                    "recommending a change."
                )
            )

            # Previous logs can help when the container has restarted.
            add_investigation(
                "CHECK_PREVIOUS_LOGS",
                "Inspect logs from the previous container instance.",
                (
                    f"kubectl logs {pod_name} "
                    f"-n {namespace} --previous --tail=100"
                ),
                (
                    "The previous container logs may contain the "
                    "failure message from the last terminated instance."
                )
            )

        # Rule 2: Invalid or unavailable container image.
        elif (
            "image" in root_cause
            and any(
                keyword in root_cause
                for keyword in (
                    "tag",
                    "pull",
                    "non-existent",
                    "invalid",
                    "unavailable"
                )
            )
        ):

            add_investigation(
                "VERIFY_IMAGE",
                "Verify the container image configured for the pod.",
                (
                    f"kubectl get pod {pod_name} "
                    f"-n {namespace} "
                    "-o jsonpath="
                    "'{.spec.containers[*].image}'"
                ),
                (
                    "The RCA indicates a possible invalid or "
                    "unavailable image. Verify the configured image "
                    "before selecting a fix."
                )
            )

            add_investigation(
                "DESCRIBE_POD",
                "Inspect pod events and container state for image-pull errors.",
                f"kubectl describe pod {pod_name} -n {namespace}",
                (
                    "Use Kubernetes events and container status to "
                    "confirm whether an image-pull issue exists."
                )
            )

        # Rule 3: Out-of-memory issues.
        elif any(
            keyword in root_cause
            for keyword in (
                "oom",
                "out of memory",
                "memory limit"
            )
        ):

            add_investigation(
                "CHECK_MEMORY",
                "Inspect the pod's configured resource requests and limits.",
                (
                    f"kubectl get pod {pod_name} "
                    f"-n {namespace} "
                    "-o jsonpath="
                    "'{.spec.containers[*].resources}'"
                ),
                (
                    "The RCA indicates a possible memory-related "
                    "failure. Inspect resource configuration and "
                    "termination evidence before recommending changes."
                )
            )

            add_investigation(
                "CHECK_LOGS",
                "Inspect available container logs for memory-related errors.",
                (
                    f"kubectl logs {pod_name} "
                    f"-n {namespace} --tail=100"
                ),
                (
                    "Correlate available logs with the container "
                    "termination reason to investigate the failure."
                )
            )

        # Rule 4: Configuration, ConfigMap, or Secret issues.
        elif any(
            keyword in root_cause
            for keyword in (
                "configuration",
                "configmap",
                "secret"
            )
        ):

            add_investigation(
                "DESCRIBE_POD",
                (
                    "Inspect pod events and container state for "
                    "evidence of configuration-related errors."
                ),
                f"kubectl describe pod {pod_name} -n {namespace}",
                (
                    "Check Kubernetes events, mount errors, and "
                    "container state before concluding that "
                    "configuration is the root cause."
                )
            )

            add_investigation(
                "CHECK_LOGS",
                "Inspect available container logs for configuration errors.",
                (
                    f"kubectl logs {pod_name} "
                    f"-n {namespace} --tail=100"
                ),
                (
                    "Use log evidence to check for missing or invalid "
                    "configuration values instead of assuming a "
                    "configuration error."
                )
            )

        # Rule 5: Fallback for unrecognized root causes.
        else:

            add_investigation(
                "DESCRIBE_POD",
                (
                    "Inspect pod events, container state, termination "
                    "details, and restart history."
                ),
                f"kubectl describe pod {pod_name} -n {namespace}",
                (
                    "No specific investigation rule matched this "
                    "root cause. Gather additional Kubernetes evidence "
                    "before selecting a corrective action."
                )
            )

            add_investigation(
                "CHECK_LOGS",
                "Inspect recent container logs for the failure message.",
                (
                    f"kubectl logs {pod_name} "
                    f"-n {namespace} --tail=100"
                ),
                (
                    "Review available logs to identify the failure "
                    "message before deciding on a corrective action."
                )
            )

        return actions


    
# from ai.remediation.action_models import (
#     RemediationAction
# )


# class RemediationEngine:

#     def generate_actions(
#         self,
#         incident_context,
#         rca
#     ):

#         actions = []

#         root_cause = (
#             rca.get(
#                 "root_cause",
#                 ""
#             ).lower()
#         )

#         pod_details = incident_context.get(
#             "pod_details",
#             {}
#         )

#         pod_name = pod_details.get(
#             "name"
#         )

#         namespace = pod_details.get(
#             "namespace",
#             "default"
#         )

#         # ---------------------------------
#         # ImagePullBackOff
#         # ---------------------------------

#         if (
#             "image" in root_cause
#             and (
#                 "tag" in root_cause
#                 or "pull" in root_cause
#             )
#         ):

#             actions.append(
#                 RemediationAction(
#                     action_id="VERIFY_IMAGE",
#                     action_type="INVESTIGATION",
#                     description=(
#                         "Verify the container image "
#                         "configured for the deployment."
#                     ),
#                     command=(
#                         f"kubectl get pod {pod_name} "
#                         f"-n {namespace} "
#                         "-o jsonpath="
#                         "'{.spec.containers[*].image}'"
#                     ),
#                     risk_level="LOW",
#                     requires_approval=False,
#                     reason=(
#                         "The RCA indicates a possible "
#                         "invalid or non-existent image."
#                     )
#                 )
#             )

#             actions.append(
#                 RemediationAction(
#                     action_id="DESCRIBE_POD",
#                     action_type="INVESTIGATION",
#                     description=(
#                         "Inspect Kubernetes events "
#                         "and container state."
#                     ),
#                     command=(
#                         f"kubectl describe pod "
#                         f"{pod_name} "
#                         f"-n {namespace}"
#                     ),
#                     risk_level="LOW",
#                     requires_approval=False,
#                     reason=(
#                         "Additional Kubernetes evidence "
#                         "should be verified before remediation."
#                     )
#                 )
#             )

#         # ---------------------------------
#         # CrashLoopBackOff
#         # ---------------------------------

#         elif "crashloopbackoff" in root_cause:

#             actions.append(
#                 RemediationAction(
#                     action_id="CHECK_LOGS",
#                     action_type="INVESTIGATION",
#                     description=(
#                         "Inspect the previous container logs "
#                         "to identify the crash reason."
#                     ),
#                     command=(
#                         f"kubectl logs "
#                         f"{pod_name} "
#                         f"-n {namespace} "
#                         "--previous"
#                     ),
#                     risk_level="LOW",
#                     requires_approval=False,
#                     reason=(
#                         "CrashLoopBackOff requires "
#                         "application-level investigation."
#                     )
#                 )
#             )

#             actions.append(
#                 RemediationAction(
#                     action_id="DESCRIBE_POD",
#                     action_type="INVESTIGATION",
#                     description=(
#                         "Inspect pod events "
#                         "and container state."
#                     ),
#                     command=(
#                         f"kubectl describe pod "
#                         f"{pod_name} "
#                         f"-n {namespace}"
#                     ),
#                     risk_level="LOW",
#                     requires_approval=False,
#                     reason=(
#                         "Kubernetes events may provide "
#                         "additional evidence."
#                     )
#                 )
#             )

#         # ---------------------------------
#         # OOMKilled
#         # ---------------------------------

#         elif "oom" in root_cause:

#             actions.append(
#                 RemediationAction(
#                     action_id="CHECK_MEMORY",
#                     action_type="INVESTIGATION",
#                     description=(
#                         "Inspect pod resource configuration."
#                     ),
#                     command=(
#                         f"kubectl get pod "
#                         f"{pod_name} "
#                         f"-n {namespace} "
#                         "-o jsonpath="
#                         "'{.spec.containers[*].resources}'"
#                     ),
#                     risk_level="LOW",
#                     requires_approval=False,
#                     reason=(
#                         "The RCA indicates a possible "
#                         "memory limit issue."
#                     )
#                 )
#             )

#         return actions
