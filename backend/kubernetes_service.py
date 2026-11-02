from .kubernetes_client import get_core_api, get_apps_api


def get_nodes():
    api = get_core_api()

    nodes = api.list_node()

    result = []

    for node in nodes.items:
        result.append({
            "name": node.metadata.name,
            "status": (
                node.status.conditions[-1].status
                if node.status.conditions
                else "Unknown"
            )
        })

    return result


def get_pods(namespace="default"):
    api = get_core_api()

    pods = api.list_namespaced_pod(namespace)

    result = []

    for pod in pods.items:
        result.append({
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
            "restarts": sum(
                container.restart_count or 0
                for container in (pod.status.container_statuses or [])
            )
        })

    return result


def get_deployments(namespace="default"):
    api = get_apps_api()

    deployments = api.list_namespaced_deployment(namespace)

    result = []

    for deployment in deployments.items:
        result.append({
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "desired_replicas": deployment.spec.replicas,
            "available_replicas": deployment.status.available_replicas or 0,
            "ready_replicas": deployment.status.ready_replicas or 0
        })

    return result


def get_services(namespace="default"):
    api = get_core_api()

    services = api.list_namespaced_service(namespace)

    result = []

    for service in services.items:
        result.append({
            "name": service.metadata.name,
            "namespace": service.metadata.namespace,
            "type": service.spec.type,
            "cluster_ip": service.spec.cluster_ip
        })

    return result


def get_pod_logs(pod_name, namespace="default"):
    api = get_core_api()

    try:
        current_logs = api.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=100
        )
    except Exception as e:
        current_logs = f"Unable to retrieve current logs: {e}"

    try:
        previous_logs = api.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            previous=True,
            tail_lines=100
        )
    except Exception as e:
        previous_logs = (
            f"Previous container logs unavailable: {e}"
        )

    def clean_logs(logs):
        if isinstance(logs, bytes):
            return logs.decode("utf-8", errors="replace")

        if (
            isinstance(logs, str)
            and logs.startswith("b'")
        ):
            import ast
            try:
                decoded = ast.literal_eval(logs)
                if isinstance(decoded, bytes):
                    return decoded.decode(
                        "utf-8", errors="replace"
                    )
            except (ValueError, SyntaxError):
                pass

        return logs

    current_logs = clean_logs(current_logs)
    previous_logs = clean_logs(previous_logs)

    return (
        "=== CURRENT CONTAINER LOGS ===\n"
        f"{current_logs}\n\n"
        "=== PREVIOUS CONTAINER LOGS ===\n"
        f"{previous_logs}"
    )


def get_pod_details(pod_name, namespace="default"):
    api = get_core_api()

    pod = api.read_namespaced_pod(
        name=pod_name,
        namespace=namespace
    )

    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "status": pod.status.phase,
        "node": pod.spec.node_name,
        "ip": pod.status.pod_ip,
        "containers": [
            container.name
            for container in pod.spec.containers
        ]
    }


def get_pod_events(pod_name, namespace="default"):
    api = get_core_api()

    events = api.list_namespaced_event(
        namespace=namespace,
        field_selector=f"involvedObject.name={pod_name}"
    )

    result = []
    seen = set()

    for event in events.items:
        timestamp = (
            event.last_timestamp.isoformat()
            if event.last_timestamp
            else (
                event.event_time.isoformat()
                if event.event_time
                else (
                    event.metadata.creation_timestamp.isoformat()
                    if event.metadata.creation_timestamp
                    else None
                )
            )
        )

        event_record = {
            "type": event.type,
            "reason": event.reason,
            "message": event.message,
            "timestamp": timestamp
        }

        # Remove exact duplicate records, but preserve
        # separate occurrences with different timestamps.
        key = (
            event_record["type"],
            event_record["reason"],
            event_record["message"],
            event_record["timestamp"]
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(event_record)

    return result
