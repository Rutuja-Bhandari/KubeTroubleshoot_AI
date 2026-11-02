
import json

from ai.rag.incident_rag import (
    retrieve_incident_knowledge
)

from ai.llm.factory import get_llm

from ai.health.health_evaluator import (
    evaluate_incident
)

from ai.database.incident_repository import (
    save_incident
)


def retry_rca_as_json(raw_response, incident_context, evidence_items):
    """Ask the LLM to return a valid, evidence-grounded RCA JSON object."""

    prompt = f"""
Convert the RCA below into a valid JSON object.

ORIGINAL RCA:
{raw_response}

AVAILABLE INCIDENT EVIDENCE:
{json.dumps(evidence_items, ensure_ascii=False, default=str)}

Return ONLY a JSON object with exactly these fields:
{{
  "root_cause": "string",
  "evidence": ["E1"],
  "confidence": "HIGH | MEDIUM | LOW",
  "impact": "LOW | MEDIUM | HIGH",
  "recommended_fix": ["string"],
  "investigation_commands": ["string"],
  "verification_steps": ["string"],
  "prevention": ["string"]
}}

Rules:
- Use only evidence IDs present in AVAILABLE INCIDENT EVIDENCE.
- Preserve the original diagnosis where supported by the evidence.
- Do not invent facts or unsupported fixes.
- All array fields must be valid JSON arrays.
- Do not include Markdown fences or explanatory prose.
"""

    llm = get_llm()
    return llm.invoke(prompt)



def classify_impact(incident_context, environment=None, criticality=None):
    """
    Classify impact using workload availability and available metadata.

    Returns: LOW, MEDIUM, or HIGH.
    """

    deployments = incident_context.get("deployments", []) or []
    incident = incident_context.get("incident", {}) or {}
    namespace = str(incident.get("namespace", "default")).strip().lower()
    pod_name = str(incident.get("pod", "")).strip().lower()

    environment = str(environment or "").strip().lower()
    criticality = str(criticality or "").strip().lower()

    production_values = {"prod", "production"}
    nonproduction_values = {
        "dev", "development", "test", "testing",
        "staging", "sandbox", "non-production", "nonproduction"
    }
    critical_values = {
        "critical", "high", "tier-1", "tier1", "mission-critical"
    }

    # Prefer the Deployment associated with the affected Pod.
    deployment = None

    for item in deployments:
        name = str(item.get("name", "")).strip().lower()
        if name and pod_name.startswith(name + "-"):
            deployment = item
            break

    # Fall back to the available Deployment with the most desired replicas.
    if deployment is None and deployments:
        deployment = max(
            deployments,
            key=lambda item: int(item.get("desired_replicas", 0) or 0)
        )

    labels = (deployment or {}).get("labels", {}) or {}

    # Prefer explicit metadata over namespace-based inference.
    if not environment:
        environment = str(
            (deployment or {}).get("environment")
            or labels.get("environment")
            or labels.get("app.kubernetes.io/environment")
            or ""
        ).strip().lower()

    if not environment:
        if namespace in production_values:
            environment = "production"
        elif namespace in nonproduction_values:
            environment = "non-production"

    if not criticality:
        criticality = str(
            (deployment or {}).get("criticality")
            or labels.get("criticality")
            or labels.get("app.kubernetes.io/criticality")
            or ""
        ).strip().lower()

    is_production = environment in production_values
    is_nonproduction = environment in nonproduction_values
    is_critical = criticality in critical_values

    # Without reliable workload availability data, avoid assuming LOW impact.
    if deployment is None:
        return "HIGH" if is_production and is_critical else "MEDIUM"

    desired = int(deployment.get("desired_replicas", 0) or 0)
    available = int(deployment.get("available_replicas", 0) or 0)

    if desired <= 0:
        return "HIGH" if is_production and is_critical else "MEDIUM"

    # No available replicas means complete workload unavailability.
    if available == 0:
        if is_production and is_critical:
            return "HIGH"
        if is_critical:
            return "HIGH"
        if is_production:
            return "MEDIUM"
        if is_nonproduction:
            return "LOW"
        return "MEDIUM"

    # Partial availability means the workload is degraded.
    if available < desired:
        if is_production and is_critical:
            return "HIGH"
        if is_production or is_critical:
            return "MEDIUM"
        if is_nonproduction:
            return "LOW"
        return "MEDIUM"

    # All desired replicas are available, although an incident may remain.
    if is_production and is_critical:
        return "MEDIUM"

    return "LOW"






def parse_llm_json(raw_response):
    """Parse a JSON object returned by the LLM."""

    if not isinstance(raw_response, str) or not raw_response.strip():
        raise ValueError("LLM returned an empty response.")

    raw_response = raw_response.strip()

    # Remove optional Markdown fences.
    if raw_response.startswith("```"):
        lines = raw_response.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        raw_response = "\n".join(lines).strip()

    # First attempt: parse the entire response.
    try:
        result = json.loads(raw_response)

        if isinstance(result, dict):
            return result

        raise ValueError("LLM response must be a JSON object.")

    except json.JSONDecodeError as original_error:
        # Fallback: extract the JSON object if extra text surrounds it.
        decoder = json.JSONDecoder()
        start = raw_response.find("{")

        if start == -1:
            raise ValueError(
                f"No JSON object found: {original_error}"
            ) from original_error

        try:
            result, _ = decoder.raw_decode(raw_response[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Could not parse LLM JSON: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError("LLM response must be a JSON object.")

        return result


def build_numbered_evidence(
    incident_context,
    metrics=None,
    anomaly_result=None
):
    """Flatten incident data and prioritize diagnostically useful evidence."""

    collected_items = []
    seen = set()

    ignored_log_errors = (
        "unable to retrieve container logs",
        "unable to retrieve current logs",
        "failed to retrieve container logs",
        "error retrieving container logs",
        "could not retrieve container logs",
        "container is waiting to start",
        "previous terminated container",
        "previous container logs unavailable",
    )

    def classify_evidence(source, path, value):
        """Assign generic evidence categories and priorities."""

        path_lower = path.lower()
        value_lower = str(value).lower()

        # Direct container diagnostic information.
        if "container_states[" in path_lower:
            if any(path_lower.endswith(suffix) for suffix in (
                ".message",
                ".reason",
                ".exit_code",
            )):
                return "direct", 1

        # Direct termination information.
        if any(term in path_lower for term in (
            "last_termination.exit_code",
            "last_termination.reason",
            "last_termination.message",
        )):
            return "direct", 1

        # Application logs.
        if "logs.line[" in path_lower:
            return "direct", 1

        # Kubernetes events.
        # Handles both events[0].message and nested paths.
        if "events[" in path_lower:
            if path_lower.endswith(".reason"):
                if value_lower in {
                    "failed",
                    "failedscheduling",
                }:
                    return "direct", 1

            if path_lower.endswith(".message"):
                diagnostic_markers = (
                    "failed to pull",
                    "pull access denied",
                    "unauthorized",
                    "insufficient_scope",
                    "manifest unknown",
                    "no matching manifest",
                    "no such host",
                    "i/o timeout",
                    "connection refused",
                    "failed to mount",
                    "failed to attach",
                    "failed to create",
                    "failed to start",
                    "out of memory",
                    "oomkilled",
                    "permission denied",
                    "image pull",
                    "errimagepull",
                    "imagepullbackoff",
                    "failedscheduling",
                    "insufficient cpu",
                    "insufficient memory",
                    "failed to probe",
                    "liveness probe failed",
                    "readiness probe failed",
                    "startup probe failed",
                    "evicted",
                )

                if any(
                    marker in value_lower
                    for marker in diagnostic_markers
                ):
                    return "direct", 1

        # Workload configuration.
        if any(term in path_lower for term in (
            ".command",
            ".args",
            ".image",
            ".imagepullpolicy",
            ".imagepullsecrets",
            ".resources.limits",
            ".resources.requests",
        )):
            return "configuration", 2

        # Resource measurements.
        if any(term in path_lower for term in (
            "memory_usage",
            "cpu_usage",
            "memory_limit",
            "cpu_limit",
            "usage_bytes",
            "working_set",
            "memory_available",
            "cpu_throttling",
        )):
            return "resource", 3

        # Contextual information.
        if any(term in path_lower for term in (
            "restart_count",
            "container_states",
            "conditions",
            "events[",
            "ready_replicas",
            "available_replicas",
            "desired_replicas",
            "pod_details",
            "status",
            "reason",
        )):
            return "context", 4

        return "other", 5

    def add_item(source, path, value):
        if value is None:
            return

        text_value = str(value).strip()

        if not text_value:
            return

        identity = (source, path, text_value)

        if identity in seen:
            return

        seen.add(identity)

        evidence_type, priority = classify_evidence(
            source,
            path,
            text_value
        )

        collected_items.append({
            "source": source,
            "path": path,
            "value": text_value,
            "evidence_type": evidence_type,
            "priority": priority,
        })

    def walk(source, path, value):
        if value is None:
            return

        if isinstance(value, dict):
            for key, nested in value.items():
                nested_path = (
                    f"{path}.{key}" if path else str(key)
                )
                walk(source, nested_path, nested)
            return

        if isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                walk(source, f"{path}[{index}]", nested)
            return

        # Split multiline logs into individually citable evidence.
        if isinstance(value, str) and path.lower().endswith("logs"):
            for line_number, line in enumerate(value.splitlines()):
                line = line.strip()

                if not line or line.startswith("==="):
                    continue

                if any(
                    marker in line.lower()
                    for marker in ignored_log_errors
                ):
                    continue

                add_item(
                    source,
                    f"{path}.line[{line_number}]",
                    line
                )
            return

        add_item(source, path, value)

    # Collect incident evidence.
    walk(
        "kubernetes_incident",
        "",
        incident_context or {}
    )

    walk(
        "prometheus_metrics",
        "",
        metrics or {}
    )

    walk(
        "ml_anomaly_analysis",
        "",
        anomaly_result or {}
    )

    # Prioritize evidence before assigning IDs.
    collected_items.sort(
        key=lambda item: item["priority"]
    )

    evidence_items = []

    for index, item in enumerate(collected_items):
        evidence_items.append({
            "id": f"E{index}",
            "source": item["source"],
            "path": item["path"],
            "value": item["value"],
            "evidence_type": item["evidence_type"],
            "priority": item["priority"],
        })

    return evidence_items





def build_rca_prompt(
    incident_context,
    knowledge,
    metrics=None,
    anomaly_result=None,
    evidence_items=None
):
    """Build a generic, evidence-driven Kubernetes RCA prompt."""

    if evidence_items is None:
        evidence_items = build_numbered_evidence(
            incident_context=incident_context,
            metrics=metrics,
            anomaly_result=anomaly_result
        )

    numbered_evidence = json.dumps(
        evidence_items,
        indent=2,
        ensure_ascii=False,
        default=str
    )

    retrieved_knowledge = json.dumps(
        knowledge,
        indent=2,
        ensure_ascii=False,
        default=str
    )

    expected_impact = classify_impact(incident_context)

    return f"""
You are an evidence-driven Kubernetes root cause analysis assistant.

Your task is to diagnose the underlying cause of a Kubernetes incident
using the supplied live incident evidence.

LIVE INCIDENT EVIDENCE:
{numbered_evidence}

RETRIEVED KNOWLEDGE:
{retrieved_knowledge}

DETERMINISTIC IMPACT CLASSIFICATION:
{expected_impact}


CRITICAL EVIDENCE SELECTION RULES:

1. The LIVE INCIDENT EVIDENCE section is the ONLY valid source of
   evidence IDs.

2. Before writing the RCA, identify the relevant evidence IDs from
   the supplied evidence list.

3. Never invent, modify, regenerate or assume evidence IDs.

4. Every evidence ID in the output must exactly match an ID present
   in LIVE INCIDENT EVIDENCE.

5. Never use IDs from previous incidents, retrieved knowledge,
   previous model responses or earlier analysis requests.

6. Evidence priority must be respected:
   - Priority 1: Direct diagnostic evidence.
   - Priority 2: Workload configuration.
   - Priority 3: Resource measurements.
   - Priority 4: Contextual symptoms.
   - Priority 5: Other information.

7. When relevant Priority 1 evidence exists, use it before lower
   priority evidence.

8. When multiple independent direct diagnostic signals are available,
   cite at least two relevant signals.

9. Configuration evidence should be included when it helps explain
   the failure mechanism. Configuration alone does not establish
   causation.

10. Do not select evidence merely because it appears first or last.
    Select it because its actual value supports the root cause.

11. Do not cite unrelated metrics, Pod metadata or contextual
    information as proof of the root cause.

12. If sufficient direct evidence is unavailable, clearly state
    the limitation and reduce confidence accordingly.


DIAGNOSTIC REQUIREMENTS:

1. Identify the underlying failure mechanism, not merely the Kubernetes
   symptom or status.

2. Examine all relevant evidence, including:
   - Container state and waiting/termination messages.
   - Application logs.
   - Container image, command and arguments.
   - Kubernetes events and event messages.
   - Resource requests, limits and measured usage.
   - Pod conditions and workload configuration.
   - Relevant Prometheus metrics and anomaly results.

3. Correlate evidence before concluding causation.
   A configured value alone does not prove that it caused the failure.
   A Kubernetes symptom alone does not establish the underlying cause.

4. For container startup and image-pull failures:
   - Examine the configured image reference.
   - Examine the container waiting reason and complete error message.
   - Examine relevant Failed, Warning and other Kubernetes events.
   - Distinguish an invalid image reference, missing repository or tag,
     authentication failure, authorization failure, registry
     connectivity problem and platform incompatibility.
   - Use the actual error message to support the diagnosis.
   - Do not assume that an authorization-related message always means
     incorrect credentials.
   - Do not use CPU, memory or restart count as proof of an image-pull
     failure.

5. For command and application failures:
   - Correlate command, arguments, application logs and termination
     details when available.
   - Identify an explicit failure command only when the evidence
     establishes it.
   - Do not treat every non-zero exit code as incorrect behavior.

6. For resource-related failures:
   - Correlate resource limits, measured usage, termination details
     and relevant events.
   - Do not conclude that a resource limit was exceeded based only
     on a current usage measurement.
   - Distinguish current usage from historical or peak usage.

7. Root-cause explanation:
   - Explain what failed and why the evidence supports it.
   - Distinguish established facts from possible explanations.
   - If the mechanism is established but the origin is uncertain,
     explicitly state what remains unconfirmed.
   - Do not invent missing information.

8. Confidence:
   - HIGH: Multiple relevant direct signals establish the cause.
   - MEDIUM: Evidence strongly suggests a cause but an important
     detail remains unconfirmed.
   - LOW: Evidence is insufficient or only symptoms are available.

9. Recommended fix:
   - Recommend a targeted corrective action.
   - Base it on the established failure mechanism.
   - Do not recommend unrelated configuration changes.
   - If the actual cause is not confirmed, recommend investigation
     before making potentially disruptive changes.

10. Investigation commands:
    - Provide relevant commands only when additional investigation
      is necessary.
    - Use actual Pod, namespace, Deployment and container details
      when available.
    - Do not invent resource names.

11. Verification:
    - Verify that the original failure condition is resolved.
    - Verify that the container starts and becomes Ready when expected.
    - Verify that the workload reaches its expected available replica
      count when applicable.
    - Verify that new Kubernetes events do not show recurring failures.
    - Check restart stability over an observation period.
    - Do not claim recovery based only on a single Running status.

12. Prevention:
    - Provide preventive measures relevant to the identified cause.
    - Keep prevention separate from the immediate corrective action.


IMPACT REQUIREMENTS:

Use the deterministic impact classification provided above.
Do not independently change or infer the impact level.


OUTPUT:

Return ONLY a valid JSON object with exactly these fields:

{{
  "root_cause": "Complete evidence-supported causal explanation",
  "evidence": ["E0", "E1"],
  "confidence": "HIGH | MEDIUM | LOW",
  "impact": "{expected_impact}",
  "recommended_fix": ["Targeted corrective action"],
  "investigation_commands": ["Relevant command, if needed"],
  "verification_steps": ["Concrete recovery check"],
  "prevention": ["Relevant preventive measure"]
}}

All evidence IDs must come from LIVE INCIDENT EVIDENCE.
The evidence array must contain only valid evidence IDs.
All array fields must be valid JSON arrays.
Use empty arrays only when no supported recommendation exists.
Do not return Markdown fences, commentary or additional fields.
"""





# def build_rca_prompt(
#     incident_context,
#     knowledge,
#     metrics=None,
#     anomaly_result=None
# ):
#     return f"""
# You are KubeTroubleshoot AI,
# an expert Kubernetes troubleshooting assistant.

# Analyze the ACTIVE Kubernetes incident below.

# Use ONLY the provided evidence and retrieved knowledge.
# Do NOT invent facts.

# ========================
# KUBERNETES INCIDENT
# ========================

# {incident_context}

# ========================
# PROMETHEUS METRICS
# ========================

# {metrics}

# ========================
# ML ANOMALY ANALYSIS
# ========================

# {anomaly_result}

# ========================
# RETRIEVED KNOWLEDGE
# ========================

# {knowledge}

# ========================
# ANALYSIS RULES
# ========================

# 1. Use only the evidence provided above.

# 2. Do not invent logs, metrics, events, configuration, or causes.

# 3. Clearly distinguish evidence from inference.

# 4. If the evidence is insufficient, state that the confidence is LOW.

# 5. Do not assume that an ML anomaly automatically means the application has failed.

# 6. Kubernetes evidence should be prioritized when determining the root cause.

# 7. Prometheus metrics should be used as supporting evidence.

# 8. ML anomaly results should be treated as an additional investigation signal.

# 9. Retrieved knowledge should support the analysis but must not override actual incident evidence.

# 10. Do not recommend destructive Kubernetes commands.

# 11. Do not perform any remediation automatically.

# 12. Recommended commands must be investigation or safe verification commands.

# 13. If Kubernetes evidence contains terms such as:
#     - "manifest unknown"
#     - "not found"
#     - "repository does not exist"
#     - "invalid image"
#     - "invalid tag"
#     - "image tag does not exist"

#     consider an incorrect or non-existent image name/tag as the likely root cause.

# 14. If Kubernetes evidence contains:
#     - "pull access denied"
#     - "authentication required"
#     - "unauthorized"
#     - "insufficient_scope"

#     determine whether the evidence indicates:
#     a) a private image requiring authentication, or
#     b) an invalid/non-existent image or tag.

# 15. Do not automatically conclude that the root cause is registry authentication
#     merely because "pull access denied" or "insufficient_scope" appears.

# 16. When the image name or tag is directly visible in the Kubernetes incident evidence,
#     use that exact image name/tag when explaining the root cause.

# 17. Prioritize specific Kubernetes event messages over generic troubleshooting
#     recommendations from the retrieved knowledge.

# 18. Only assign HIGH confidence when the Kubernetes evidence directly supports
#     the root cause.

# 19. If multiple causes are possible and the evidence cannot distinguish between them,
#     state the uncertainty and use MEDIUM or LOW confidence.

# 20. For ImagePullBackOff incidents, distinguish between:
#     - incorrect/non-existent image or tag
#     - private registry authentication failure
#     - missing ImagePullSecret
#     - registry availability failure

# 21. For containers that have not started and have no meaningful runtime metrics,
#     do not treat CPU=0, memory=0, or restart_count=0 as evidence that the
#     application is healthy.

# 22. If ML anomaly analysis is unavailable because the container has not started,
#     do not infer that the application is normal. Continue RCA using Kubernetes
#     evidence, events, and retrieved knowledge.

# ========================
# TASK
# ========================

# Determine:

# 1. Probable root cause
# 2. Evidence supporting the root cause
# 3. Confidence level
# 4. Application impact
# 5. Recommended fix
# 6. Investigation commands
# 7. Verification steps
# 8. Prevention recommendations

# ========================
# OUTPUT FORMAT
# ========================

# Return ONLY valid JSON.

# Use exactly this structure:

# {{
#     "root_cause": "string",
#     "evidence": [
#         "string"
#     ],
#     "confidence": "HIGH | MEDIUM | LOW",
#     "impact": "string",
#     "recommended_fix": [
#         "string"
#     ],
#     "investigation_commands": [
#         "string"
#     ],
#     "verification_steps": [
#         "string"
#     ],
#     "prevention": [
#         "string"
#     ]
# }}

# Do not add Markdown.
# Do not add ```json.
# Do not add explanations outside the JSON.

# RCA EVIDENCE RULES:
# 1. Use only evidence provided in the incident context.
# 2. CrashLoopBackOff is a symptom, not a root cause.
# 3. Examine container logs, current state, last termination reason,
#    exit code, restart count, and Kubernetes events.
# 4. Do not assume a configuration error without supporting evidence.
# 5. Separate confirmed facts from possible explanations.
# 6. If the evidence is insufficient, report:
#    "Root cause not confirmed."
# 7. Never report missing CPU or memory metrics as zero usage.
# 8. For the known simulated test, if the logs contain
#    "Simulated application failure" and the termination exit code
#    is 1, identify the configured process exit as the root cause.
# 9. Return valid JSON that follows the existing output schema.



# rca_instructions = 
# Analyze this Kubernetes incident using the supplied cluster evidence.

# Requirements:
# 1. Determine the most likely root cause from the actual evidence.
# 2. Do not assume a predefined error scenario or reuse a fixed diagnosis.
# 3. Correlate container states, current and previous logs, exit codes,
#    Kubernetes events, workload status, resource limits, probes,
#    configuration, and available metrics.
# 4. Explain which observations support the diagnosis.
# 5. Distinguish confirmed facts from hypotheses.
# 6. If evidence is insufficient, state what remains unknown and provide
#    investigation commands to collect the missing evidence.
# 7. Recommend fixes specific to the observed problem. Do not recommend
#    changing resource limits or restarting workloads without evidence.
# 8. Set confidence according to the strength of the evidence.
# 9. Return valid JSON with these fields:
#    root_cause, evidence, confidence, impact, recommended_fix,
#    investigation_commands, verification_steps, prevention.


# """






def apply_evidence_based_rca(
    incident_context,
    rca,
    metrics=None,
    evidence_items=None
):
    """
    Validate RCA evidence references and assess their diagnostic strength.

    If LLM-generated citations are invalid or insufficient, select
    relevant evidence deterministically from trusted evidence_items.

    Evidence classification does not automatically verify semantic
    entailment.
    """

    if not isinstance(rca, dict) or rca.get("error"):
        return rca

    metrics = metrics or {}

    if evidence_items is None:
        evidence_items = build_numbered_evidence(
            incident_context=incident_context,
            metrics=metrics
        )

    if not isinstance(evidence_items, list):
        evidence_items = []

    evidence_lookup = {
        str(item["id"]): item
        for item in evidence_items
        if isinstance(item, dict) and item.get("id") is not None
    }

    # ---------------------------------------------------------
    # 1. Evidence classification
    # ---------------------------------------------------------

    def classify_evidence(item):
        path = str(item.get("path", "")).lower()
        value = str(item.get("value", "")).lower()

        if "container_states[" in path:
            if any(term in path for term in (
                ".message",
                ".reason",
                ".exit_code",
                ".last_termination.reason",
                ".last_termination.message",
                ".last_termination.exit_code",
            )):
                return "direct"

        if path.startswith("events[") and any(
            term in path for term in (".message", ".reason")
        ):
            diagnostic_markers = (
                "failed",
                "error",
                "back-off",
                "backoff",
                "imagepull",
                "oomkilled",
                "unhealthy",
                "failedmount",
                "failedscheduling",
                "insufficient",
                "denied",
                "unauthorized",
                "forbidden",
                "timeout",
                "timed out",
                "probe",
                "evicted",
                "killing",
            )

            if any(marker in value for marker in diagnostic_markers):
                return "direct"

        if any(term in path for term in (
            "exit_code",
            "last_termination.reason",
            "last_termination.message",
        )):
            return "direct"

        if ".command" in path or ".args" in path:
            return "configuration"

        if any(term in path for term in (
            ".image",
            "imagepullpolicy",
            "imagepullsecrets",
        )):
            return "configuration"

        if "logs.line[" in path:
            return "direct"

        if any(term in path for term in (
            "memory_usage",
            "cpu_usage",
            "memory_limit",
            "cpu_limit",
            "usage_bytes",
            "working_set",
        )):
            return "resource"

        if any(term in path for term in (
            "restart_count",
            "container_states",
            "conditions",
            "events",
            "ready_replicas",
            "available_replicas",
            "pod_details",
            "desired_replicas",
            "status",
        )):
            return "context"

        return "other"

    # ---------------------------------------------------------
    # 2. Identify incident-specific diagnostic signals
    # ---------------------------------------------------------

    incident_text = str(incident_context).lower()

    incident_families = {
        "image_pull": (
            "imagepullbackoff",
            "errimagepull",
            "failed to pull image",
            "pull access denied",
            "insufficient_scope",
            "manifest unknown",
            "repository does not exist",
            "image pull",
        ),
        "oom": (
            "oomkilled",
            "out of memory",
            "exit code 137",
            "exit_code': 137",
            "memory limit",
        ),
        "crash": (
            "crashloopbackoff",
            "exit code 1",
            "exit_code': 1",
            "terminated",
            "application failure",
            "process exited",
        ),
        "probe": (
            "liveness probe",
            "readiness probe",
            "startup probe",
            "unhealthy",
            "probe failed",
        ),
        "scheduling": (
            "failedscheduling",
            "failed scheduling",
            "insufficient cpu",
            "insufficient memory",
            "nodeaffinity",
            "taint",
            "untolerated",
        ),
        "volume": (
            "failedmount",
            "failed attach",
            "mountvolume",
            "persistentvolumeclaim",
            "volume mount",
        ),
        "network": (
            "connection refused",
            "connection timed out",
            "networkunavailable",
            "dns resolution",
            "no such host",
        ),
        "permission": (
            "permission denied",
            "forbidden",
            "unauthorized",
            "access denied",
            "authentication failed",
        ),
    }

    active_families = {
        family
        for family, markers in incident_families.items()
        if any(marker in incident_text for marker in markers)
    }

    def matching_families(text):
        text = str(text).lower()

        return {
            family
            for family, markers in incident_families.items()
            if any(marker in text for marker in markers)
        }

    # If the context does not identify the incident type clearly,
    # infer it from direct diagnostic evidence.
    if not active_families:
        for item in evidence_items:
            if not isinstance(item, dict):
                continue

            if classify_evidence(item) != "direct":
                continue

            item_text = (
                str(item.get("path", "")) + " " +
                str(item.get("value", ""))
            )

            active_families.update(
                matching_families(item_text)
            )

    # ---------------------------------------------------------
    # 3. Deterministic evidence selection
    # ---------------------------------------------------------

    def select_relevant_evidence():
        scored_direct = []
        scored_configuration = []

        for item in evidence_items:
            if not isinstance(item, dict):
                continue

            evidence_id = item.get("id")

            if evidence_id is None:
                continue

            evidence_id = str(evidence_id)

            path = str(item.get("path", "")).lower()
            value = str(item.get("value", "")).lower()
            combined_text = f"{path} {value}"

            evidence_type = classify_evidence(item)
            matched = matching_families(combined_text)

            # Ignore evidence unrelated to the detected incident
            # when a specific incident family is available.
            if active_families and matched and not (
                matched & active_families
            ):
                continue

            relevance_score = 0

            if matched & active_families:
                relevance_score += 10

            if evidence_type == "direct":
                relevance_score += 3

            if "container_states[" in path:
                relevance_score += 3

            if "last_termination" in path:
                relevance_score += 2

            if "logs.line[" in path:
                relevance_score += 2

            if path.startswith("events["):
                relevance_score += 1

            # Generic failure words alone are not sufficient
            # to make an event useful diagnostic evidence.
            if any(marker in value for marker in (
                "successfully assigned",
                "successfully pulled",
                "started container",
                "created container",
            )):
                relevance_score = 0

            if evidence_type == "direct" and relevance_score > 0:
                scored_direct.append(
                    (relevance_score, item)
                )

            elif evidence_type == "configuration":
                # Configuration is useful only when it
                # corroborates the identified incident family.
                if matched & active_families:
                    scored_configuration.append(
                        (relevance_score + 2, item)
                    )

        scored_direct.sort(
            key=lambda entry: entry[0],
            reverse=True
        )

        scored_configuration.sort(
            key=lambda entry: entry[0],
            reverse=True
        )

        selected = []
        selected_ids = set()

        # Direct diagnostic evidence takes priority.
        for _, item in scored_direct:
            evidence_id = str(item["id"])

            if evidence_id not in selected_ids:
                selected.append(evidence_id)
                selected_ids.add(evidence_id)

            if len(selected) >= 5:
                break

        # Include relevant configuration only when direct
        # diagnostic evidence is already available.
        if selected:
            for _, item in scored_configuration:
                evidence_id = str(item["id"])

                if evidence_id not in selected_ids:
                    selected.append(evidence_id)
                    selected_ids.add(evidence_id)

                if len(selected) >= 7:
                    break

        return selected

    # ---------------------------------------------------------
    # 4. Validate LLM citations
    # ---------------------------------------------------------

    root_cause = rca.get("root_cause")

    if not isinstance(root_cause, str) or not root_cause.strip():
        rca["root_cause"] = "Root cause not confirmed."
        rca["confidence"] = "LOW"
        rca["evidence"] = []
        rca["supporting_evidence_ids"] = []

        rca["rca_validation"] = {
            "status": "missing_root_cause",
            "supporting_evidence_ids": [],
            "direct_diagnostic_signal_cited": False,
            "diagnostic_evidence_types": [],
            "direct_evidence_count": 0,
            "configuration_evidence_count": 0,
            "resource_evidence_count": 0,
            "contextual_evidence_count": 0,
            "semantic_entailment_verified": False,
        }

    else:
        raw_citations = rca.get("evidence", [])

        if not isinstance(raw_citations, list):
            raw_citations = []

        valid_ids = []

        for citation in raw_citations:
            if not isinstance(citation, str):
                continue

            evidence_id = citation.strip()

            if (
                evidence_id in evidence_lookup
                and evidence_id not in valid_ids
            ):
                valid_ids.append(evidence_id)

        # -----------------------------------------------------
        # 5. Check whether existing citations are diagnostic
        # -----------------------------------------------------

        def get_evidence_types(evidence_ids):
            return [
                classify_evidence(evidence_lookup[evidence_id])
                for evidence_id in evidence_ids
            ]

        existing_types = get_evidence_types(valid_ids)

        has_existing_diagnostic_evidence = any(
            evidence_type in {"direct", "resource"}
            for evidence_type in existing_types
        )

        # Recover when IDs are invalid or citations contain
        # no direct/resource diagnostic evidence.
        fallback_used = False

        if not valid_ids or not has_existing_diagnostic_evidence:
            fallback_ids = select_relevant_evidence()

            if fallback_ids:
                valid_ids = fallback_ids
                fallback_used = True

        cited_items = [
            evidence_lookup[evidence_id]
            for evidence_id in valid_ids
        ]

        classified_items = [
            (item, classify_evidence(item))
            for item in cited_items
        ]

        direct_items = [
            item for item, kind in classified_items
            if kind == "direct"
        ]

        configuration_items = [
            item for item, kind in classified_items
            if kind == "configuration"
        ]

        resource_items = [
            item for item, kind in classified_items
            if kind == "resource"
        ]

        context_items = [
            item for item, kind in classified_items
            if kind == "context"
        ]

        evidence_types = [
            kind for _, kind in classified_items
        ]

        # -----------------------------------------------------
        # 6. Build evidence descriptions from trusted data
        # -----------------------------------------------------

        rca["evidence"] = [
            (
                f"[{item['id']}] "
                f"{item.get('source', 'incident')} | "
                f"{item.get('path', '')}: "
                f"{item.get('value', '')}"
            )
            for item in cited_items
        ]

        rca["supporting_evidence_ids"] = valid_ids

        confidence = str(
            rca.get("confidence", "LOW")
        ).upper().strip()

        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            confidence = "LOW"

        root_cause_text = rca["root_cause"].lower().strip()

        symptom_only_terms = (
            "crashloopbackoff",
            "backoff condition",
            "container is restarting",
            "container is in waiting state",
            "pod is not ready",
            "root cause not confirmed",
        )

        is_symptom_only = any(
            term in root_cause_text
            for term in symptom_only_terms
        )

        has_direct_signal = bool(direct_items)
        has_resource_signal = bool(resource_items)

        if not valid_ids:
            confidence = "LOW"
            validation_status = "no_valid_evidence_references"

        elif is_symptom_only and not (
            has_direct_signal or has_resource_signal
        ):
            confidence = "LOW"

            rca["root_cause"] = (
                "Root cause not confirmed. The available cited evidence "
                "identifies symptoms but does not establish the "
                "underlying failure mechanism."
            )

            validation_status = "symptom_only_diagnosis"

        elif not (
            has_direct_signal or has_resource_signal
        ):
            confidence = "LOW"
            validation_status = "insufficient_diagnostic_evidence"

        elif confidence == "HIGH":
            direct_paths = {
                str(item.get("path", "")).lower()
                for item in direct_items
            }

            if len(direct_paths) < 2 and not (
                has_resource_signal and has_direct_signal
            ):
                confidence = "MEDIUM"

                validation_status = (
                    "limited_diagnostic_evidence_for_high_confidence"
                )

            else:
                validation_status = (
                    "diagnostic_evidence_present_semantic_review_needed"
                )

        else:
            validation_status = (
                "diagnostic_evidence_present_semantic_review_needed"
            )

        rca["confidence"] = confidence

        rca["rca_validation"] = {
            "status": validation_status,
            "supporting_evidence_ids": valid_ids,
            "direct_diagnostic_signal_cited": has_direct_signal,
            "diagnostic_evidence_types": sorted(set(evidence_types)),
            "direct_evidence_count": len(direct_items),
            "configuration_evidence_count": len(configuration_items),
            "resource_evidence_count": len(resource_items),
            "contextual_evidence_count": len(context_items),
            "semantic_entailment_verified": False,
            "fallback_evidence_selection_used": fallback_used,
        }

    # ---------------------------------------------------------
    # 7. Preserve deterministic impact classification
    # ---------------------------------------------------------

    rca["impact"] = classify_impact(incident_context)

    # ---------------------------------------------------------
    # 8. Preserve API/UI list fields
    # ---------------------------------------------------------

    for field in (
        "recommended_fix",
        "investigation_commands",
        "verification_steps",
        "prevention",
    ):
        if not isinstance(rca.get(field), list):
            rca[field] = []

    return rca




# def apply_evidence_based_rca(
#     incident_context,
#     rca,
#     metrics=None
# ):
#     """
#     Apply evidence-based corrections for OOMKilled and the
#     known simulated application failure.

#     Current memory metrics are not treated as historical peak usage.
#     """

#     if not isinstance(rca, dict):
#         return rca

#     metrics = metrics or {}

#     container_states = incident_context.get(
#         "container_states",
#         []
#     )

#     # ---------------------------------
#     # CASE 1: OOMKilled
#     # ---------------------------------

#     oom_containers = []

#     for container in container_states:
#         last_termination = (
#             container.get("last_termination") or {}
#         )

#         current_reason = container.get("reason")
#         current_exit_code = container.get("exit_code")

#         last_reason = last_termination.get("reason")
#         last_exit_code = last_termination.get("exit_code")

#         if (
#             current_reason == "OOMKilled"
#             or last_reason == "OOMKilled"
#         ):
#             oom_containers.append({
#                 "name": container.get("name", "unknown"),
#                 "exit_code": (
#                     current_exit_code
#                     if current_reason == "OOMKilled"
#                     else last_exit_code
#                 )
#             })

#     if oom_containers:
#         container_names = ", ".join(
#             item["name"] for item in oom_containers
#         )

#         evidence = []

#         for item in oom_containers:
#             evidence.append(
#                 f"Kubernetes recorded OOMKilled for container "
#                 f"{item['name']}."
#             )

#             if item["exit_code"] == 137:
#                 evidence.append(
#                     f"Container {item['name']} exited with code 137, "
#                     "consistent with SIGKILL."
#                 )

#         memory_usage = metrics.get("memory_usage")

#         if memory_usage is not None:
#             evidence.append(
#                 f"Current observed memory usage: {memory_usage} bytes. "
#                 "This is a current sample and does not establish "
#                 "the historical peak before termination."
#             )
#         else:
#             evidence.append(
#                 "Current memory usage is unavailable. Historical "
#                 "peak memory usage has not been established."
#             )

#         rca["root_cause"] = (
#             f"Memory exhaustion: Kubernetes recorded OOMKilled "
#             f"for container(s) {container_names}."
#         )
#         rca["confidence"] = "HIGH"
#         rca["impact"] = (
#             "The affected container was terminated because of "
#             "memory exhaustion. Repeated terminations can prevent "
#             "the workload from remaining available."
#         )
#         rca["evidence"] = evidence
#         rca["recommended_fix"] = [
#             "Inspect the container's memory limit and resource requests.",
#             "Review application memory consumption and investigate "
#             "possible memory leaks or unusually large allocations.",
#             "Use historical monitoring data, when available, to assess "
#             "memory usage before termination.",
#             "Adjust the memory limit only after validating application "
#             "requirements and available cluster capacity."
#         ]
#         rca["verification_steps"] = [
#             "Inspect the container's current and previous termination state.",
#             "Monitor memory usage and container restarts after applying "
#             "the fix.",
#             "Confirm that the Pod becomes Ready and remains stable."
#         ]
#         rca["prevention"] = [
#             "Set appropriate container memory requests and limits.",
#             "Monitor memory trends and container restart counts.",
#             "Investigate sustained memory growth before it reaches "
#             "the configured limit."
#         ]

#         return rca

#     # ---------------------------------
#     # CASE 2: Known simulated exit code 1
#     # ---------------------------------

#     context_text = json.dumps(
#         incident_context,
#         default=str
#     ).lower()

#     has_test_message = (
#         "simulated application failure" in context_text
#     )

#     has_exit_code = any(
#         container.get("exit_code") == 1
#         or (
#             (container.get("last_termination") or {})
#             .get("exit_code") == 1
#         )
#         for container in container_states
#     )

#     if not (has_test_message and has_exit_code):
#         return rca

#     rca["root_cause"] = (
#         "The container's configured command prints "
#         "'Simulated application failure' and exits with code 1."
#     )
#     rca["confidence"] = "HIGH"
#     rca["impact"] = (
#         "The container repeatedly exits, which can prevent its "
#         "workload from becoming available."
#     )
#     rca["evidence"] = [
#         "Container logs or incident context contain "
#         "'Simulated application failure'.",
#         "The container terminates with exit code 1.",
#         "The pod enters CrashLoopBackOff after repeated failures."
#     ]
#     rca["recommended_fix"] = [
#         "For this deliberate test, replace the failure command "
#         "with the intended application command.",
#         "For a real incident, investigate why the container process exits.",
#         "After applying a fix, verify that the pod becomes Ready."
#     ]
#     rca["verification_steps"] = [
#         "Check the pod status and confirm the container is Running.",
#         "Confirm the pod Ready condition is True.",
#         "If the pod belongs to a Deployment, verify its available replicas."
#     ]
#     rca["prevention"] = [
#         "Test container startup commands before deployment.",
#         "Add readiness checks and deployment health validation."
#     ]

#     return rca



def analyze_kubernetes_incident(
    incident_context,
    metrics=None,
    anomaly_result=None
):
    """
    Main Kubernetes incident analysis pipeline.

    Flow:

    Incident Context
            ↓
    Health Evaluation
            ↓
    HEALTHY → Return result

    UNHEALTHY
            ↓
    Prometheus Metrics
            ↓
    ML Anomaly Detection
            ↓
    RAG
            ↓
    LLM
            ↓
    Root Cause Analysis
            ↓
    Incident Database
    """

    # ---------------------------------
    # STEP 1: Evaluate Pod Health
    # ---------------------------------

    health_result = evaluate_incident(
        incident_context
    )

    # ---------------------------------
    # STEP 2: Stop if Pod is Healthy
    # ---------------------------------

    if not health_result["incident_detected"]:

        return {
            "health": health_result,
            "incident_context": incident_context,
            "metrics": metrics,
            "anomaly": anomaly_result,
            "retrieved_knowledge": None,
            "root_cause_analysis": None
        }

    # ---------------------------------
    # STEP 3: Retrieve Relevant Knowledge
    # ---------------------------------

    knowledge = retrieve_incident_knowledge(
        incident_context,
        top_k=3
    )

    # ---------------------------------
    # STEP 4: Build Advanced RCA Prompt
    # ---------------------------------

    
    # Build one evidence list for both generation and validation.
    evidence_items = build_numbered_evidence(
        incident_context=incident_context,
        metrics=metrics,
        anomaly_result=anomaly_result
    )

    ######   temporary code
    print("\n========== RCA EVIDENCE DEBUG ==========")

    for item in evidence_items:
        if item.get("priority", 5) <= 3:
            print(
                f"ID={item['id']} | "
                f"TYPE={item.get('evidence_type')} | "
                f"PRIORITY={item.get('priority')} | "
                f"PATH={item['path']} | "
                f"VALUE={item['value']}"
            )

    print("========== END RCA EVIDENCE DEBUG ==========\n")


###########temporary code ends 

    prompt = build_rca_prompt(
        incident_context=incident_context,
        knowledge=knowledge,
        metrics=metrics,
        anomaly_result=anomaly_result,
        evidence_items=evidence_items
    )


    # ---------------------------------
    # STEP 5: Get LLM Provider
    # ---------------------------------

    llm = get_llm()

    # ---------------------------------
    # STEP 6: Generate Root Cause Analysis
    # ---------------------------------

    print("=== RCA PROMPT: INCIDENT LOGS ===")
    print(incident_context.get("logs"))

    print("=== RCA PROMPT: FULL PROMPT ===")
    print(prompt)

    raw_rca = llm.generate(
        prompt
    )


    
    # ---------------------------------
    # STEP 7: Parse, Retry, and Validate RCA JSON
    # ---------------------------------

    def parse_and_validate_rca(raw_response):
        """Parse the LLM response and validate the minimum RCA fields."""

        parsed = parse_llm_json(raw_response)

        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object.")

        root_cause = parsed.get("root_cause")

        if not isinstance(root_cause, str) or not root_cause.strip():
            raise ValueError(
                "RCA response is missing a valid root_cause."
            )

        required_list_fields = (
            "evidence",
            "recommended_fix",
            "investigation_commands",
            "verification_steps",
            "prevention",
        )

        for field in required_list_fields:
            if not isinstance(parsed.get(field), list):
                parsed[field] = []

        if parsed.get("confidence") not in ("HIGH", "MEDIUM", "LOW"):
            parsed["confidence"] = "LOW"

        if not isinstance(parsed.get("impact"), str):
            parsed["impact"] = "Impact requires further investigation."

        return parsed

    try:
        # First attempt: parse the original LLM response.
        rca = parse_and_validate_rca(raw_rca)

    except (ValueError, json.JSONDecodeError) as first_error:
        print(
            f"Initial RCA parsing failed: "
            f"{type(first_error).__name__}: {first_error}"
        )

        try:
            # Second attempt: ask the same LLM to return valid JSON.
            retry_response = retry_rca_as_json(
                raw_response=raw_rca,
                evidence_items=evidence_items,
                llm=llm
            )

            rca = parse_and_validate_rca(retry_response)

            print("RCA JSON retry succeeded.")

        except (ValueError, json.JSONDecodeError) as retry_error:
            print(
                f"RCA retry failed: "
                f"{type(retry_error).__name__}: {retry_error}"
            )

            rca = {
                "error": (
                    "Unable to parse or validate RCA after one retry: "
                    f"{retry_error}"
                ),
                "raw_response": raw_rca,
                "retry_response": (
                    retry_response
                    if "retry_response" in locals()
                    else None
                )
            }

    # Apply evidence validation only to a successfully parsed RCA.
    if isinstance(rca, dict) and "error" not in rca:
        rca = apply_evidence_based_rca(
            incident_context=incident_context,
            rca=rca,
            metrics=metrics,
            evidence_items=evidence_items
        )



    # # ---------------------------------
    # # STEP 7: Parse and Validate LLM JSON
    # # ---------------------------------

    # try:
    #     rca = parse_llm_json(raw_rca)

    #     # Validate the minimum fields needed by the UI.
    #     if not isinstance(rca.get("root_cause"), str) or not rca["root_cause"].strip():
    #         rca = {
    #             "error": "RCA response is missing a valid root_cause.",
    #             "raw_response": raw_rca
    #         }

    #     else:
    #         # Ensure optional list fields have safe defaults.
    #         for field in (
    #             "evidence",
    #             "recommended_fix",
    #             "investigation_commands",
    #             "verification_steps",
    #             "prevention"
    #         ):
    #             if not isinstance(rca.get(field), list):
    #                 rca[field] = []

    #         rca.setdefault("confidence", "Not specified")
    #         rca.setdefault("impact", "Not specified")

    # except (ValueError, json.JSONDecodeError) as exc:
    #     print(f"RCA parsing failed: {exc}")

    #     rca = {
    #         "error": "Unable to parse a valid RCA from the LLM response.",
    #         "raw_response": raw_rca
    #     }

    # if isinstance(rca, dict) and "error" not in rca:
    #     rca = apply_evidence_based_rca(
    #         incident_context=incident_context,
    #         rca=rca,
    #         metrics=metrics
    #     )

    # ---------------------------------
    # STEP 8: Save Valid RCA
    # ---------------------------------

    if "error" not in rca:

        pod_details = incident_context.get(
            "pod_details",
            {}
        )

        incident_details = incident_context.get(
            "incident",
            {}
        )

        pod_name = pod_details.get(
            "name"
        )

        if not pod_name:
            pod_name = incident_details.get(
                "pod"
            )

        namespace = pod_details.get(
            "namespace"
        )

        if not namespace:
            namespace = incident_details.get(
                "namespace",
                "default"
            )

        try:

            save_incident(
                pod_name=pod_name,
                namespace=namespace,
                health_result=health_result,
                rca=rca
            )

        except Exception as e:

            # Database failure should not prevent
            # the RCA from being returned.

            print(
                f"Warning: Failed to save incident: {e}"
            )

    # ---------------------------------
    # STEP 9: Return Complete Result
    # ---------------------------------

    return {
        "health": health_result,
        "incident_context": incident_context,
        "metrics": metrics,
        "anomaly": anomaly_result,
        "retrieved_knowledge": knowledge,
        "root_cause_analysis": rca
    }
