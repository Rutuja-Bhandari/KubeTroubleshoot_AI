# Root Cause Analysis Runbook: CreateContainerConfigError (`CreateContainerConfigError.md`)

This runbook defines the structured, evidence-based diagnostic framework for analyzing `CreateContainerConfigError` and `CreateContainerError` states in Kubernetes pods. It focuses on mapping container runtime configuration mismatches and missing dependent objects to verified root causes before the container application engine starts execution.

---

## 1. Taxonomic Classification & Meaning of Statuses

A `CreateContainerConfigError` occurs strictly during the initialization phase *after* an image has been successfully pulled, but *before* the container process is executed by the container runtime interface (CRI). It represents a structural mismatch between the requested configuration in the Pod specification and the actual state of the cluster control plane dependencies.

### 1.1 Status Differentiating (Config vs. Execution)
*   **CreateContainerConfigError**: The Kubelet cannot compile the configuration context required to orchestrate the container. This is primarily caused by missing dependencies like `ConfigMaps`, `Secrets`, or invalid mounting points.
*   **CreateContainerError**: The Kubelet has all configuration definitions present, but the underlying container runtime (e.g., `containerd`, `CRI-O`) failed to generate the isolation boundaries (e.g., namespace creation, cgroup allocations, mounting system paths, or resolving invalid entrypoint commands).

### 1.2 Container State vs. Pod Condition
*   The overall Pod status is typically marked as **`Waiting`** or **`Pending`**.
*   The targeted container within the status array explicitly presents `Reason: CreateContainerConfigError`.
*   The `Ready` and `ContainersReady` Pod conditions are set to `False`.

---

## 2. Evidence-to-Cause Mapping Matrix

Primary diagnostic data must be extracted from the `Events` log section using `kubectl describe pod <pod-name>`. Do not infer an unconfirmed diagnosis without an explicit message signature pattern match.

| Event Type | Reason Field | Message Signature Pattern | Inferred Root Cause |
| :--- | :--- | :--- | :--- |
| `Warning` | `FailedValidation` | `configmap "..." not found` | **Missing or Undefined ConfigMap Dependency** |
| `Warning` | `FailedValidation` | `secret "..." not found` | **Missing or Undefined Secret Dependency** |
| `Warning` | `FailedValidation` | `keys [...] not found in ConfigMap "..."` | **Missing Explicit Data Key in Specified ConfigMap** |
| `Warning` | `FailedValidation` | `keys [...] not found in Secret "..."` | **Missing Explicit Data Key in Specified Secret** |
| `Warning` | `Failed` | `container_linux.go:... starting container process caused: exec: "...": executable file not found in $PATH` | **Invalid Entrypoint Command or Missing Binary in Image** |
| `Warning` | `Failed` | `failed to create containerd task: ... OCI runtime create failed: container_linux.go:... path "..." is not a directory` | **Volume Mounting Conflict (Mounting Directory onto a File)** |

---

## 3. Deep-Dive Diagnostic & Verification Vectors

### 3.1 Object Reference & Namespace Isolation Vector
Kubernetes resource references within a Pod manifest are explicitly bound by namespace isolation rules.
*   **Cross-Namespace Blindspots**: A Pod cannot mount or ingest a `ConfigMap` or `Secret` located in a different namespace. If the resource exists in `default` but the deployment manifest targets `production`, the Kubelet will fail to resolve the object references.
*   **ServiceAccount Token Automounting**: If `automountServiceAccountToken` is set to `true`, but the designated `ServiceAccount` configuration or its associated token secret has been deleted by an external control loop, the pod will cycle in a configuration error state.

### 3.2 Environment Variable Ingestion vs. Structural Keys
*   **`envFrom` Cascades**: When ingesting an entire resource via `envFrom`, if the object is missing, the Kubelet will fail the container creation entirely unless the `optional: true` parameter is explicitly defined in the manifest.
*   **`valueFrom` Specificity**: When mapping a specific key (`key: db-password`), if the parent resource exists but the target key is dropped or mistyped, the Kubelet throws a validation exception visible exclusively in the `Events` payload.

### 3.3 Container Runtime Interface (CRI) & Storage Vectors
*   **OCI Runtime Violations**: When `CreateContainerError` manifests, the breakdown sits at the host layer. This occurs if subpath mounts conflict with existing symbolic links on the worker node filesystem or if the image defines a non-root `UID` that does not match local host cgroup file permission masks.

---

## 4. Anti-Patterns & Common Automated Troubleshooting Pitfalls

*   **Anti-Pattern 1: Prioritizing Application Logs**
    *   *Why it is wrong*: The application process **never starts**. Inspecting application stdout/stderr logs will result in zero telemetry. The diagnostic pipeline must bypass log checks and parse `kubectl describe pod` and cluster events instead.
*   **Anti-Pattern 2: Defaulting to `kubectl rollout restart`**
    *   *Why it is wrong*: Restarting the deployment does not regenerate a missing `Secret` or fix an invalid `subPath`. The new pods will encounter the exact same configuration validation obstacle on the Kubelet.
*   **Anti-Pattern 3: Exposing Secret Payloads During Audits**
    *   *Why it is wrong*: When confirming the existence of a missing data key within a secret, the automation must check for the presence of the key name inside the resource metadata map. It **must never** base64 decode or dump data payloads into logs or reports.

---

## 5. Cause-Specific Remediation Manual

### 5.1 Remediation: Missing Dependent ConfigMap/Secret
*   **Evidence Pattern**: `secret "app-credentials" not found`
*   **Remediation**: Create the missing dependent resource in the target namespace or switch the container declaration to optional ingestion.

```yaml
# Fix 1: Generate the object in the matching namespace
kubectl create secret generic app-credentials --from-literal=DB_PASS=secure --namespace=<pod-namespace>

# Fix 2: Modify Pod specification to mark reference as optional
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: app-credentials
        key: DB_PASS
        optional: true # Prevents container from failing if resource is absent
```

### 5.2 Remediation: Key Reference Mismatch
*   **Evidence Pattern**: `keys [api-token] not found in Secret "vault-token"`
*   **Remediation**: Align the structural manifest reference path with the exact key defined inside the existing resource payload map.

```yaml
# Corrected Pod Specification Entry
env:
  - name: VAULT_TOKEN
    valueFrom:
      secretKeyRef:
        name: vault-token
        key: corrected-token-key-name # Must match the exact string key in the secret map
```

---

## 6. Verification & Closure Criteria

An active configuration incident is officially resolved only when all three statements evaluate to `True`:

1.  **Container Phase Shift**: The targeted container moves past the `Waiting` phase into a running operational status.
2.  **Quiescent Event Streams**: The Kubelet ceases writing `Warning / FailedValidation` entries into the core object event buffer for a period exceeding 5 minutes.
3.  **Condition Validation**: The top-level `Ready` condition flags inside the Pod descriptor return a value of `True`.

---

## 7. Uncertainty Handling Protocol

*   **Ambiguous Root Causes**: If the events return a generic `CreateContainerError` without specifying the OCI system call failure path, the AI engine must set the analysis indicator to `UNCONFIRMED_HOST_ENVIRONMENT_FAULT`.
*   **Operator Checklist Action**: Request the system operator to provide:
    *   Output of `kubectl get configmap -n <namespace>` to audit object availability.
    *   Host cgroup status logs directly from the node runtime platform.
