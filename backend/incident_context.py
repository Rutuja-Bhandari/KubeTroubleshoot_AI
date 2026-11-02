
from .kubernetes_service import (
    get_pod_details,
    get_pod_logs,
    get_pod_events,
    get_deployments
)

from .kubernetes_client import get_core_api
from kubernetes import client

def get_related_deployment_names(pod, namespace):
    """
    Return Deployment names that actually own this Pod,
    directly or through its ReplicaSet.
    """
    related_names = set()
    owner_references = pod.metadata.owner_references or []

    apps_api = client.AppsV1Api()

    for owner in owner_references:
        if owner.kind == "Deployment":
            related_names.add(owner.name)

        elif owner.kind == "ReplicaSet":
            try:
                replica_set = apps_api.read_namespaced_replica_set(
                    name=owner.name,
                    namespace=namespace
                )

                replica_set_owners = (
                    replica_set.metadata.owner_references or []
                )

                for rs_owner in replica_set_owners:
                    if rs_owner.kind == "Deployment":
                        related_names.add(rs_owner.name)

            except Exception:
                # Do not assume a Deployment relationship
                # if the ReplicaSet cannot be resolved.
                continue

    return related_names






def build_incident_context(
    pod_name,
    namespace="default"
):
    """
    Collect Pod state, logs, events, Deployment health,
    and safe container configuration for incident analysis.
    """

    api = get_core_api()

    pod = api.read_namespaced_pod(
        name=pod_name,
        namespace=namespace
    )

    pod_details = get_pod_details(
        pod_name,
        namespace
    )

    # 1. Collect current and previous container logs.
    try:
        logs = get_pod_logs(
            pod_name,
            namespace
        )
    except Exception as exc:
        logs = f"Unable to retrieve logs: {exc}"

    # 2. Collect Kubernetes events.
    try:
        events = get_pod_events(
            pod_name,
            namespace
        )
    except Exception as exc:
        events = [
            {
                "type": "ERROR",
                "reason": "EventCollectionFailed",
                "message": str(exc)
            }
        ]

    # 3. Collect container states and last termination details.
    container_states = []

    for container in (pod.status.container_statuses or []):
        state = container.state

        container_info = {
            "name": container.name,
            "restart_count": container.restart_count,
            "ready": container.ready
        }

        if state and state.waiting:
            container_info["state"] = "waiting"
            container_info["reason"] = state.waiting.reason
            container_info["message"] = state.waiting.message

        elif state and state.running:
            container_info["state"] = "running"

        elif state and state.terminated:
            container_info["state"] = "terminated"
            container_info["reason"] = state.terminated.reason
            container_info["exit_code"] = state.terminated.exit_code
            container_info["message"] = state.terminated.message

        last_state = container.last_state

        if last_state and last_state.terminated:
            termination = last_state.terminated

            container_info["last_termination"] = {
                "reason": termination.reason,
                "exit_code": termination.exit_code,
                "message": termination.message,
                "started_at": (
                    termination.started_at.isoformat()
                    if termination.started_at
                    else None
                ),
                "finished_at": (
                    termination.finished_at.isoformat()
                    if termination.finished_at
                    else None
                )
            }

        container_states.append(container_info)

    # 4. Resolve the Deployment that owns this Pod.
    deployments = []

    try:
        apps_api = client.AppsV1Api()
        related_deployment_names = set()

        owner_references = pod.metadata.owner_references or []

        for owner in owner_references:
            if owner.kind == "Deployment":
                related_deployment_names.add(owner.name)

            elif owner.kind == "ReplicaSet":
                try:
                    replica_set = apps_api.read_namespaced_replica_set(
                        name=owner.name,
                        namespace=namespace
                    )

                    for rs_owner in (
                        replica_set.metadata.owner_references or []
                    ):
                        if rs_owner.kind == "Deployment":
                            related_deployment_names.add(rs_owner.name)

                except Exception as exc:
                    print(
                        f"Unable to resolve ReplicaSet "
                        f"{owner.name}: {exc}"
                    )

        deployment_objects = (
            apps_api.list_namespaced_deployment(
                namespace=namespace
            ).items
        )

        # Use label selectors only when owner references did not
        # identify a Deployment. Accept only a unique match.
        if not related_deployment_names:
            pod_labels = pod.metadata.labels or {}
            selector_matches = []

            for deployment in deployment_objects:
                selector = (
                    deployment.spec.selector.match_labels or {}
                )

                if selector and all(
                    pod_labels.get(key) == value
                    for key, value in selector.items()
                ):
                    selector_matches.append(deployment)

            if len(selector_matches) == 1:
                related_deployment_names.add(
                    selector_matches[0].metadata.name
                )

        # Include only related Deployments and their container specs.
        for deployment in deployment_objects:
            if deployment.metadata.name not in related_deployment_names:
                continue

            pod_template = deployment.spec.template.spec
            deployment_containers = []

            for container in (pod_template.containers or []):
                deployment_containers.append({
                    "name": container.name,
                    "image": container.image,
                    "command": container.command or [],
                    "args": container.args or []
                })

            deployments.append({
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "desired_replicas": deployment.spec.replicas,
                "available_replicas": (
                    deployment.status.available_replicas or 0
                ),
                "ready_replicas": (
                    deployment.status.ready_replicas or 0
                ),
                "containers": deployment_containers
            })

    except Exception as exc:
        print(
            f"Unable to resolve related Deployments "
            f"for Pod {pod_name}: {exc}"
        )
        deployments = []

    # 5. Return the complete incident context.
    return {
        "incident": {
            "pod": pod_name,
            "namespace": namespace
        },
        "pod_details": pod_details,
        "container_states": container_states,
        "logs": logs,
        "events": events,
        "deployments": deployments
    }
