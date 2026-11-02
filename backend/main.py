from fastapi import FastAPI
from fastapi import HTTPException
from ai.database.incident_repository import (
    get_recent_incidents
)
from .kubernetes_service import (
    get_nodes,
    get_pods,
    get_deployments,
    get_services,
    get_pod_logs,
    get_pod_details
)

from .incident_detector import (
    detect_pod_incidents,
    detect_deployment_incidents
)

from .incident_context import (
    build_incident_context
)

from ai.rag.incident_rag import (
    retrieve_incident_knowledge
)

from ai.rag.analysis import (
    analyze_kubernetes_incident
)

from ai.metrics.metrics_collector import (
    KubernetesMetricsCollector
)

from ai.anomaly.kubernetes_anomaly import (
    KubernetesAnomalyService
)
from ai.remediation.action_engine import (
    RemediationEngine
)

from ai.remediation.kubernetes_actions import (
    KubernetesActionExecutor
)

from ai.remediation.proposal_store import (
    initialize_proposal_store,
    create_proposal,
    get_proposal,
    claim_proposal,
    update_proposal_status,
)

app = FastAPI(
    title="KubeTroubleshoot AI",
    description="Intelligent Kubernetes Troubleshooting Assistant",
    version="1.0.0"
)


# ---------------------------------
# Initialize Metrics and ML Services
# ---------------------------------

metrics_collector = KubernetesMetricsCollector()

anomaly_service = KubernetesAnomalyService()


@app.get("/")
def root():
    return {
        "message": "KubeTroubleshoot AI API is running"
    }

initialize_proposal_store()

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/kubernetes/nodes")
def kubernetes_nodes():
    try:
        return {
            "nodes": get_nodes()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/pods")
def kubernetes_pods(
    namespace: str = "default"
):
    try:
        return {
            "pods": get_pods(namespace)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/deployments")
def kubernetes_deployments(
    namespace: str = "default"
):
    try:
        return {
            "deployments": get_deployments(namespace)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/services")
def kubernetes_services(
    namespace: str = "default"
):
    try:
        return {
            "services": get_services(namespace)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/pods/{pod_name}/logs")
def kubernetes_pod_logs(
    pod_name: str,
    namespace: str = "default"
):
    try:
        return {
            "pod": pod_name,
            "logs": get_pod_logs(
                pod_name,
                namespace
            )
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/pods/{pod_name}/details")
def kubernetes_pod_details(
    pod_name: str,
    namespace: str = "default"
):
    try:
        return get_pod_details(
            pod_name,
            namespace
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/kubernetes/incidents")
def kubernetes_incidents(
    namespace: str = "default"
):

    try:

        pod_incidents = detect_pod_incidents(
            namespace
        )

        deployment_incidents = detect_deployment_incidents(
            namespace
        )

        return {
            "namespace": namespace,
            "incident_count": (
                len(pod_incidents)
                + len(deployment_incidents)
            ),
            "incidents": (
                pod_incidents
                + deployment_incidents
            )
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get(
    "/kubernetes/incidents/{pod_name}/context"
)
def incident_context(
    pod_name: str,
    namespace: str = "default"
):

    try:

        return build_incident_context(
            pod_name,
            namespace
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get(
    "/kubernetes/incidents/{pod_name}/knowledge"
)
def incident_knowledge(
    pod_name: str,
    namespace: str = "default"
):

    try:

        incident_context = build_incident_context(
            pod_name,
            namespace
        )

        knowledge = retrieve_incident_knowledge(
            incident_context,
            top_k=3
        )

        return {
            "pod": pod_name,
            "namespace": namespace,
            "incident_context": incident_context,
            "knowledge": knowledge
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get(
    "/kubernetes/incidents/{pod_name}/metrics"
)
def pod_metrics(
    pod_name: str,
    namespace: str = "default"
):

    try:

        metrics = metrics_collector.get_pod_metrics(
            pod_name,
            namespace
        )

        return {
            "pod": pod_name,
            "namespace": namespace,
            "metrics": metrics
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get(
    "/kubernetes/incidents/{pod_name}/anomaly"
)
def pod_anomaly(
    pod_name: str,
    namespace: str = "default"
):

    try:

        anomaly_result = anomaly_service.analyze_pod(
            pod_name,
            namespace
        )

        return {
            "pod": pod_name,
            "namespace": namespace,
            **anomaly_result
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get(
    "/kubernetes/incidents/{pod_name}/analyze"
)
def analyze_incident_endpoint(
    pod_name: str,
    namespace: str = "default"
):

    try:

        # ---------------------------------
        # STEP 1: Build Kubernetes Context
        # ---------------------------------

        incident_context = build_incident_context(
            pod_name,
            namespace
        )

        # ---------------------------------
        # STEP 2: Collect Prometheus Metrics
        # ---------------------------------

        metrics = metrics_collector.get_pod_metrics(
            pod_name,
            namespace
        )

        # ---------------------------------
        # STEP 3: Run ML Anomaly Detection
        # ---------------------------------

        anomaly_result = None

        if anomaly_service.trained:

            anomaly_result = anomaly_service.analyze_pod(
                pod_name,
                namespace
            )

        # ---------------------------------
        # STEP 4: Advanced RCA
        # ---------------------------------

        result = analyze_kubernetes_incident(
            incident_context=incident_context,
            metrics=metrics,
            anomaly_result=anomaly_result
        )

        # ---------------------------------
        # STEP 5: Return Complete Analysis
        # ---------------------------------

        return {
            "pod": pod_name,
            "namespace": namespace,
            **result
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/incidents")
def get_incidents():

    incidents = get_recent_incidents()

    return [
        {
            "id": incident.id,
            "pod": incident.pod_name,
            "namespace": incident.namespace,
            "status": incident.status,
            "root_cause": incident.root_cause,
            "confidence": incident.confidence,
            "impact": incident.impact,
            "recommended_fix": incident.recommended_fix,
            "evidence": incident.evidence,
            "created_at": incident.created_at
        }
        for incident in incidents
    ]

@app.get(
    "/kubernetes/incidents/{pod_name}/remediation"
)
def generate_remediation(
    pod_name: str,
    namespace: str = "default"
):
    incident_context = build_incident_context(
        pod_name,
        namespace
    )

    analysis = analyze_kubernetes_incident(
        incident_context
    )

    rca = analysis.get(
        "root_cause_analysis"
    )

    if not rca or "error" in rca:
        return {
            "status": "NO_REMEDIATION",
            "message": (
                "A valid RCA is required "
                "before generating remediation actions."
            )
        }

    engine = RemediationEngine()

    actions = engine.generate_actions(
        incident_context,
        rca
    )

    action_results = []

    for action in actions:
        action_data = {
            "action_id": action.action_id,
            "action_type": action.action_type,
            "description": action.description,
            "command": action.command,
            "risk_level": action.risk_level,
            "requires_approval": action.requires_approval,
            "reason": action.reason
        }

        # Create a proposal only for remediation actions
        # that require human approval.
        if (
            action.action_type == "REMEDIATION"
            and action.requires_approval
        ):
            proposal_id = create_proposal(
                action=action,
                pod_name=pod_name,
                namespace=namespace
            )

            action_data["proposal_id"] = proposal_id

        action_results.append(action_data)

    return {
        "pod": pod_name,
        "namespace": namespace,
        "root_cause": rca.get("root_cause"),
        "actions": action_results
    }


@app.post(
    "/kubernetes/remediation/{action_id}/approve"
)
def approve_remediation(action_id: str):

    return {
        "status": "APPROVED",
        "action_id": action_id,
        "message": (
            "Remediation action approved by human. "
            "Execution is still disabled."
        )
    }

@app.post(
    "/kubernetes/remediation/{pod_name}/{action_id}/execute"
)
def execute_remediation(
    pod_name: str,
    action_id: str,
    namespace: str = "default"
):

    try:

        incident_context = build_incident_context(
            pod_name,
            namespace
        )

        analysis = analyze_kubernetes_incident(
            incident_context
        )

        rca = analysis.get(
            "root_cause_analysis"
        )

        if not rca or "error" in rca:

            return {
                "status": "FAILED",
                "message": (
                    "A valid RCA is required "
                    "before remediation."
                )
            }

        engine = RemediationEngine()

        actions = engine.generate_actions(
            incident_context,
            rca
        )

        selected_action = None

        for action in actions:

            if action.action_id == action_id:
                selected_action = action
                break

        if not selected_action:

            return {
                "status": "NOT_FOUND",
                "action_id": action_id,
                "message": (
                    "Requested remediation action "
                    "was not found."
                )
            }

        if not selected_action.requires_approval:

            return {
                "status": "BLOCKED",
                "action_id": action_id,
                "message": (
                    "This action does not represent "
                    "an approved remediation operation."
                )
            }

        executor = KubernetesActionExecutor()

        result = executor.execute(
            selected_action,
            approved=True
        )

        return {
            "pod": pod_name,
            "namespace": namespace,
            "action_id": action_id,
            "result": result
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/kubernetes/remediation/{proposal_id}/approve")
def approve_remediation(proposal_id: str):
    proposal = get_proposal(proposal_id)

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found.",
        )

    if proposal["status"] != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail="Proposal is no longer pending approval.",
        )

    # Reserve the proposal before execution so it cannot be
    # approved twice by concurrent requests.

    if not claim_proposal(proposal_id):
        raise HTTPException(
            status_code=409,
            detail="Proposal has already been processed."
        )



    try:
        executor = KubernetesActionExecutor()
        result = executor.execute_approved_proposal(proposal)

        final_status = (
            "IN_PROGRESS"
            if result.get("status") == "IN_PROGRESS"
            else "FAILED"
            if result.get("status") == "FAILED"
            else "BLOCKED"
        )

        update_proposal_status(
            proposal_id,
            final_status,
            result,
        )

        return {
            "proposal_id": proposal_id,
            "status": final_status,
            "result": result,
        }

    except Exception as exc:
        update_proposal_status(
            proposal_id,
            "FAILED",
            {"status": "FAILED", "message": str(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail="Remediation execution failed.",
        )   




@app.get("/kubernetes/remediation/{proposal_id}/verify")
def verify_remediation(proposal_id: str):
    proposal = get_proposal(proposal_id)

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found.",
        )

    if proposal["status"] not in ("IN_PROGRESS", "SUCCEEDED"):
        raise HTTPException(
            status_code=409,
            detail="The proposal is not awaiting verification.",
        )

    result = proposal.get("result") or {}
    deployment_name = result.get("deployment")

    if not deployment_name:
        raise HTTPException(
            status_code=400,
            detail="No Deployment is associated with this proposal.",
        )

    executor = KubernetesActionExecutor()
    verification = executor.verify_deployment_rollout(
        deployment_name,
        proposal["namespace"],
    )

    if verification["status"] == "SUCCEEDED":
        update_proposal_status(
            proposal_id,
            "SUCCEEDED",
            verification,
        )
    elif verification["status"] == "FAILED":
        update_proposal_status(
            proposal_id,
            "FAILED",
            verification,
        )

    return {
        "proposal_id": proposal_id,
        "status": verification["status"],
        "verification": verification,
    }
