# Root Cause Analysis Runbook: Kubernetes Probe Failures (`ProbeFailures.md`)

This runbook defines the structured, evidence-based diagnostic framework for analyzing Kubernetes container probe failures. It focuses on mapping explicit diagnostic evidence to verified root causes, avoiding generic remediations, and ensuring highly reliable automated troubleshooting.

---

## 1. Taxonomic Classification & Meaning of Statuses

A probe failure occurs when the Kubelet periodically evaluates a container's health and receives an invalid response. It is crucial to distinguish between the three types of probes because treating a shallow runtime timeout like a structural application crash leads to incorrect remediations.

### 1.1 Probe Type Categorization
*   **Startup Probe Failure**: Evaluates if the application inside the container has started up. All other probes are disabled until this succeeds. Failure tells the Kubelet to kill and restart the container.
*   **Liveness Probe Failure**: Evaluates if the container needs to be restarted due to deadlocks or unrecoverable frozen states. Continuous failure triggers a container restart loop.
*   **Readiness Probe Failure**: Evaluates if the container is ready to accept network traffic. Failure does **not** restart the container; instead, it immediately removes the Pod's IP address from the Endpoints/EndpointSlices of all matching Services.

### 1.2 Container State vs. Pod Condition
A probe failure shifts the container's status into a `Waiting` or `Running` state (with a degraded readiness bit) and alters the Pod conditions:
*   `ContainersReady` condition is set to `False`.
*   `Ready` condition is set to `False`.

---

## 2. Evidence-to-Cause Mapping Matrix

When analyzing a probe failure, the primary evidence must be pulled from `kubectl describe pod <pod-name>` inside the `Events` stream. Do not infer a cause without matching one of these specific diagnostic signatures.

| Event Type | Reason Field | Message Signature Pattern | Inferred Root Cause |
| :--- | :--- | :--- | :--- |
| `Warning` | `Unhealthy` | `Liveness probe failed: Get "http://...": dial tcp ...: connect: connection refused` | **Application Process Crash / Port Binding Misconfiguration** |
| `Warning` | `Unhealthy` | `Readiness probe failed: HTTP probe failed with statuscode: 503` | **Downstream Dependency Outage / Shaded Bootstrapping** |
| `Warning` | `Unhealthy` | `Readiness probe failed: HTTP probe failed with statuscode: 404` | **Invalid Endpoint Path Configuration** |
| `Warning` | `Unhealthy` | `Liveness probe failed: Client.Timeout exceeded while awaiting headers` | **CPU Throttling / Heavy Thread Pool Exhaustion** |
| `Warning` | `Unhealthy` | `Liveness probe failed: OOMKilled` (Cross-referenced with Container State) | **Probe Handler Triggered Memory Cap Breach** |
| `Warning` | `Unhealthy` | `Liveness probe failed: OOMKilled` (Exit Code 137) | **Memory Leak or Insufficient Memory Limits** |
| `Warning` | `Unhealthy` | `Readiness probe failed: executable file not found in $PATH` | **Missing Binary in Minimal/Distroless Image (`exec` Probe)** |
| `Warning` | `Unhealthy` | `Readiness probe failed: connection timed out` | **Strict NetworkPolicy Blocking Kubelet Ingress Traffic** |

---

## 3. Deep-Dive Diagnostic & Verification Vectors

### 3.1 Network Overlays & Port-Binding Checks
Probes originate directly from the host Node's Kubelet daemon, not from within the Pod network overlay or other pods.
*   **Interface Binding**: Verify that the application binds to `0.0.0.0` (all interfaces) rather than exclusively to `127.0.0.1` (loopback interface), unless the probe is an `exec` type running locally within the container context.
*   **NetworkPolicy Blockades**: Validate if an Ingress `NetworkPolicy` isolates the Pod. The Kubelet typically operates on the host network or a designated system bridge. If a policy blocks all ingress without explicitly permitting the Kubelet or host subnet ranges, the network connection will time out.

### 3.2 Resource Contention & Kernel Throttling
*   **CPU Shares Throttling**: Look at node metrics via `kubectl top pod`. If a container is near its `resources.limits.cpu` ceiling, the Linux kernel throttles its execution time slices. An application that takes 5ms to answer a health check under normal conditions may take $>5000\text{ms}$ when severely throttled, triggering a `timeoutSeconds` breach.
*   **Memory Evictions vs. OOM**: If the execution of an `exec` probe spawns a heavy shell process (e.g., calling a heavy script via `bash`), it can consume enough transient memory to hit `resources.limits.memory`. This causes an instant `OOMKilled` event with **Exit Code 137**.

### 3.3 Authorization vs. Network Firewalls on Endpoints
*   **Authentication/Authorization Barriers**: If the probe returns an HTTP `401 Unauthorized` or `403 Forbidden`, the application's internal security frameworks (e.g., Spring Security, Passport, middleware) are intercepting the probe request. The Kubelet does not natively inject authentication headers unless explicitly configured in the `httpHeaders` field of the probe manifest.
*   **Dependency Cascades**: A `503 Service Unavailable` signature indicates that the health endpoint is written as a "deep check" (e.g., validating connections to PostgreSQL, Redis, or an external API). If any downstream service fails, the probe fails, cascading a external network outage into a Pod routing eviction.

---

## 4. Anti-Patterns & Common Automated Troubleshooting Pitfalls

When designing or operating an automated RCA system like KubeTroubleshoot AI, strict boundaries must be maintained to prevent catastrophic remediation cycles.

*   **Anti-Pattern 1: Defaulting to `kubectl rollout restart`**
    *   *Why it is wrong*: If a probe is failing due to an invalid endpoint path, a blocked firewall port, or an authentication mismatch, restarting the deployment creates a cascading crashloop across all replicas, destroying whatever remaining traffic capacity existed.
*   **Anti-Pattern 2: Prioritizing Application Logs Over Infrastructure Events**
    *   *Why it is wrong*: When a container is frozen by a kernel deadlock or trapped in an intensive CPU-throttled garbage collection cycle, it cannot write out application logs. Relying on application stdout logs will yield blank data. The definitive source of truth is always the Kubelet's `Events` stream inside the `kubectl describe pod` command output.
*   **Anti-Pattern 3: Assuming Every Unready Pod is Failing Its Probes**
    *   *Why it is wrong*: A pod can report `Ready: 0/1` because it is still executing an `initContainer`, because it has been evicted due to node disk pressure, or because it has not yet passed its `initialDelaySeconds` window. Confirm a true probe failure only when an explicit `Unhealthy` event is present.
*   **Anti-Pattern 4: Exposing App-Specific Credentials to Probe Blocks**
    *   *Why it is wrong*: Hardcoding authorization or bearer tokens within the clear-text `httpHeaders` field of the Pod specification exposes production credentials. Secure connections must be verified by evaluating RBAC access to local endpoints or using safe `exec` calls that do not print secrets to standard output streams.
*   **Anti-Pattern 5: Cumulative Error Conflation**
    *   *Why it is wrong*: Do not mark every possible cause as an active diagnosis. Keep potential theoretical vulnerabilities clearly isolated from the concrete, log-matched evidence observed in the active cluster state.

---

## 5. Cause-Specific Remediation Manual

### 5.1 Remediation: Application Boot Timing Out (Startup Probe Failure)
*   **Evidence Pattern**: `Startup probe failed` warnings followed immediately by container restarts.
*   **Remediation**: Implement or extend a `startupProbe` with an increased allocation of `failureThreshold` or `periodSeconds` to give the application adequate headroom to initialize without impacting its runtime liveness sensitivity.

```yaml
# Correct Remediation Manifest Segment
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  periodSeconds: 10
  failureThreshold: 30 # Provides up to 300 seconds of cold-boot time
```

### 5.2 Remediation: CPU Throttling Induced Timeouts
*   **Evidence Pattern**: `Liveness probe failed: Client.Timeout exceeded while awaiting headers` matched with high CPU utilization metrics.
*   **Remediation**: Do not alter the probe parameters. Instead, safely increase the `resources.limits.cpu` field or remove it if using alternative cluster-wide resource management, ensuring the runtime process has sufficient processing slices to respond within the specified `timeoutSeconds`.

```yaml
# Correct Remediation Manifest Segment
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "2000m" # Elevated limit to prevent scheduling starvation during high load
    memory: "512Mi"
```

### 5.3 Remediation: Local Interface Binding Failure
*   **Evidence Pattern**: `dial tcp 10.244.x.x:8080: connect: connection refused`
*   **Remediation**: Modify the application's boot configuration environment variables or code configuration to change its server binding from `127.0.0.1` to `0.0.0.0`.

```yaml
# Example Environment Fix for Node.js / Python web servers
env:
  - name: HOST
    value: "0.0.0.0"
  - name: PORT
    value: "8080"
```

### 5.4 Remediation: Authorization Obstacles
*   **Evidence Pattern**: `HTTP probe failed with statuscode: 403` or `401`
*   **Remediation**: Exclude the specific health check endpoint (`/healthz` or `/v1/status`) from the application's global authentication filters, or use an `exec` probe that bypasses the HTTP stack entirely via local process evaluation.

```yaml
# Bypassing the network security layer via local command execution
livenessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - "pidof app-process-name"
