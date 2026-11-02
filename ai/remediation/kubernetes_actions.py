
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KubernetesActionExecutor:

    ALLOWED_ACTIONS = {
        "RESTART_POD",
        "SCALE_DEPLOYMENT",
        "ROLLBACK_DEPLOYMENT",
    }

    def __init__(self):
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.apps_api = client.AppsV1Api()
        self.core_api = client.CoreV1Api()

    def execute(self, action, approved=False):

        if not approved:
            return {
                "status": "APPROVAL_REQUIRED",
                "action_id": action.action_id,
                "message": "Human approval is required."
            }

        if action.action_type != "REMEDIATION":
            return {
                "status": "NOT_EXECUTED",
                "action_id": action.action_id,
                "message": "Action is not a remediation operation."
            }

        if action.action_id not in self.ALLOWED_ACTIONS:
            return {
                "status": "BLOCKED",
                "action_id": action.action_id,
                "message": "Action is not allowlisted."
            }

        try:
            if action.action_id == "RESTART_POD":
                return self.restart_pod(action)

            if action.action_id == "SCALE_DEPLOYMENT":
                return self.scale_deployment(action)

            if action.action_id == "ROLLBACK_DEPLOYMENT":
                return self.rollback_deployment(action)

        except ApiException as e:
            return {
                "status": "FAILED",
                "action_id": action.action_id,
                "message": (
                    f"Kubernetes API error: "
                    f"{e.status} {e.reason}"
                )
            }

        return {
            "status": "BLOCKED",
            "action_id": action.action_id,
            "message": "No execution handler exists for this action."
        }

    def restart_pod(self, action):

        pod_name = action.metadata["pod_name"]
        namespace = action.metadata["namespace"]

        pod = self.core_api.read_namespaced_pod(
            name=pod_name,
            namespace=namespace
        )

        # Only delete a pod managed by a supported controller.
        owners = pod.metadata.owner_references or []

        if not any(
            owner.kind in {"ReplicaSet", "StatefulSet", "DaemonSet"}
            for owner in owners
        ):
            return {
                "status": "BLOCKED",
                "action_id": action.action_id,
                "message": (
                    "Pod is not managed by a supported controller. "
                    "It will not be deleted."
                )
            }

        self.core_api.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace
        )

        return {
            "status": "EXECUTED",
            "action_id": action.action_id,
            "pod_name": pod_name,
            "namespace": namespace,
            "message": (
                f"Deletion requested for pod {pod_name}. "
                "The controller may create a replacement pod."
            )
        }

    def scale_deployment(self, action):

        deployment_name = action.metadata["deployment_name"]
        namespace = action.metadata["namespace"]
        replicas = action.metadata["replicas"]

        if (
            not isinstance(replicas, int)
            or isinstance(replicas, bool)
            or not 1 <= replicas <= 10
        ):
            return {
                "status": "BLOCKED",
                "action_id": action.action_id,
                "message": "Replicas must be an integer from 1 to 10."
            }

        self.apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace
        )

        self.apps_api.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body={"spec": {"replicas": replicas}}
        )

        return {
            "status": "EXECUTED",
            "action_id": action.action_id,
            "deployment_name": deployment_name,
            "namespace": namespace,
            "replicas": replicas,
            "message": (
                f"Scaling requested for {deployment_name}: "
                f"{replicas} replicas."
            )
        }

    def rollback_deployment(self, action):

        return {
            "status": "NOT_IMPLEMENTED",
            "action_id": action.action_id,
            "message": (
                "Rollback is not implemented. "
                "No deployment changes were made."
            )
        }

    def verify_pod(self, pod_name, namespace):

        try:
            pod = self.core_api.read_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )

            phase = pod.status.phase or "Unknown"
            container_statuses = (
                pod.status.container_statuses or []
            )

            ready = (
                bool(container_statuses)
                and all(
                    container.ready
                    for container in container_statuses
                )
            )

            return {
                "pod": pod_name,
                "namespace": namespace,
                "phase": phase,
                "ready": ready,
                "status": (
                    "HEALTHY"
                    if phase == "Running" and ready
                    else "UNHEALTHY"
                )
            }

        except ApiException as e:
            return {
                "pod": pod_name,
                "namespace": namespace,
                "status": "UNKNOWN",
                "error": (
                    f"Kubernetes API error: "
                    f"{e.status} {e.reason}"
                )
            }

    def execute_approved_proposal(self, proposal):
        """
        Execute a supported remediation from a stored proposal.

        The proposal must already have been approved by the backend.
        This method deliberately does not execute arbitrary shell
        commands stored in the proposal.
        """

        action_id = proposal.get("action_id")

        if proposal.get("action_type") != "REMEDIATION":
            return {
                "status": "BLOCKED",
                "action_id": action_id,
                "message": "Only remediation actions can be executed."
            }

        if action_id not in self.ALLOWED_ACTIONS:
            return {
                "status": "BLOCKED",
                "action_id": action_id,
                "message": "Action is not allowlisted."
            }

        metadata = proposal.get("metadata") or {}
        pod_name = proposal.get("pod_name") or metadata.get("pod_name")
        namespace = (
            proposal.get("namespace")
            or metadata.get("namespace")
            or "default"
        )

        # Reconstruct the approved action using stored proposal data.
        # Do not accept an arbitrary command from the API request.
        from ai.remediation.action_models import RemediationAction

        action_metadata = dict(metadata)
        action_metadata["namespace"] = namespace

        if action_id == "RESTART_POD":
            if not pod_name:
                return {
                    "status": "BLOCKED",
                    "action_id": action_id,
                    "message": "The proposal does not contain a pod name."
                }

            action_metadata["pod_name"] = pod_name

        elif action_id == "SCALE_DEPLOYMENT":
            if not action_metadata.get("deployment_name"):
                return {
                    "status": "BLOCKED",
                    "action_id": action_id,
                    "message": (
                        "The proposal does not contain a deployment name."
                    )
                }

            if "replicas" not in action_metadata:
                return {
                    "status": "BLOCKED",
                    "action_id": action_id,
                    "message": (
                        "The proposal does not contain a replica count."
                    )
                }

        action = RemediationAction(
            action_id=action_id,
            action_type="REMEDIATION",
            description="Approved remediation proposal",
            command="",
            risk_level="MEDIUM",
            requires_approval=True,
            reason="Approved through the remediation proposal workflow.",
            metadata=action_metadata
        )

        # Approval is checked by the proposal API before this method
        # is called. This method still enforces action-type and
        # allowlist checks in execute().
        return self.execute(action, approved=True)

    def verify_deployment_rollout(self, deployment_name, namespace):
        """
        Check whether a deployment rollout has completed.

        This verifies rollout readiness. It does not independently
        establish that the original incident has been resolved.
        """

        try:
            deployment = self.apps_api.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace
            )

            spec = deployment.spec
            status = deployment.status

            desired_replicas = (
                spec.replicas if spec.replicas is not None else 1
            )

            observed_generation = status.observed_generation or 0
            generation = deployment.metadata.generation or 0
            updated_replicas = status.updated_replicas or 0
            available_replicas = status.available_replicas or 0
            ready_replicas = status.ready_replicas or 0

            rollout_complete = (
                observed_generation >= generation
                and updated_replicas == desired_replicas
                and available_replicas == desired_replicas
                and ready_replicas == desired_replicas
            )

            return {
                "status": (
                    "SUCCEEDED"
                    if rollout_complete
                    else "IN_PROGRESS"
                ),
                "deployment_name": deployment_name,
                "namespace": namespace,
                "desired_replicas": desired_replicas,
                "updated_replicas": updated_replicas,
                "available_replicas": available_replicas,
                "ready_replicas": ready_replicas,
                "observed_generation": observed_generation,
                "generation": generation,
                "checked_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "message": (
                    "Deployment rollout completed successfully."
                    if rollout_complete
                    else "Deployment rollout is not complete yet."
                )
            }

        except ApiException as e:
            return {
                "status": "FAILED",
                "deployment_name": deployment_name,
                "namespace": namespace,
                "message": (
                    f"Kubernetes API error: "
                    f"{e.status} {e.reason}"
                )
            }

    
    def verify_deployment_rollout(self, deployment_name, namespace):
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
            )

            spec = deployment.spec
            status = deployment.status

            desired = spec.replicas or 0
            updated = status.updated_replicas or 0
            available = status.available_replicas or 0
            observed_generation = status.observed_generation or 0
            generation = deployment.metadata.generation or 0

            rollout_complete = (
                observed_generation >= generation
                and updated == desired
                and available == desired
                and (status.replicas or 0) == desired
            )

            return {
                "status": (
                    "SUCCEEDED" if rollout_complete
                    else "IN_PROGRESS"
                ),
                "deployment": deployment_name,
                "namespace": namespace,
                "desired_replicas": desired,
                "updated_replicas": updated,
                "available_replicas": available,
                "message": (
                    "Deployment rollout completed."
                    if rollout_complete
                    else "Deployment rollout is not complete yet."
                ),
            }

        except ApiException as exc:
            return {
                "status": "FAILED",
                "message": (
                    f"Kubernetes API error ({exc.status}): "
                    f"{exc.reason}"
                ),
            }

