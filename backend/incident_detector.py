from .kubernetes_client import get_core_api, get_apps_api


def detect_pod_incidents(namespace="default"):
    api = get_core_api()
  
    pods = api.list_namespaced_pod(namespace)

    incidents = []

    for pod in pods.items:

        pod_name = pod.metadata.name
        pod_phase = pod.status.phase

        restart_count = 0

        if pod.status.container_statuses:
            restart_count = sum(
                container.restart_count or 0
                for container in pod.status.container_statuses
            )

        # Check pod phase
        if pod_phase not in ["Running", "Succeeded"]:
            incidents.append({
                "type": "POD_NOT_HEALTHY",
                "severity": "HIGH",
                "pod": pod_name,
                "message": f"Pod status is {pod_phase}",
                "restart_count": restart_count
            })

        # Check excessive restarts
        if restart_count >= 3:
            incidents.append({
                "type": "HIGH_RESTART_COUNT",
                "severity": "HIGH",
                "pod": pod_name,
                "message": (
                    f"Pod has restarted {restart_count} times"
                ),
                "restart_count": restart_count
            })

        # Check container waiting states
        if pod.status.container_statuses:

            for container in pod.status.container_statuses:

                if container.state and container.state.waiting:

                    reason = container.state.waiting.reason

                    if reason:

                        incidents.append({
                            "type": "CONTAINER_WAITING",
                            "severity": "HIGH",
                            "pod": pod_name,
                            "container": container.name,
                            "reason": reason,
                            "message": (
                                f"Container is waiting: {reason}"
                            )
                        })

    return incidents


def detect_deployment_incidents(namespace="default"):
    api = get_apps_api()

    deployments = api.list_namespaced_deployment(namespace)

    incidents = []

    for deployment in deployments.items:

        name = deployment.metadata.name

        desired = deployment.spec.replicas or 0
        available = deployment.status.available_replicas or 0
        ready = deployment.status.ready_replicas or 0

        if available < desired:

            incidents.append({
                "type": "DEPLOYMENT_UNAVAILABLE",
                "severity": "HIGH",
                "deployment": name,
                "message": (
                    f"Deployment has {available}/{desired} "
                    "available replicas"
                ),
                "desired_replicas": desired,
                "available_replicas": available
            })

        if ready < desired:

            incidents.append({
                "type": "DEPLOYMENT_NOT_READY",
                "severity": "MEDIUM",
                "deployment": name,
                "message": (
                    f"Deployment has {ready}/{desired} "
                    "ready replicas"
                ),
                "desired_replicas": desired,
                "ready_replicas": ready
            })

    return incidents