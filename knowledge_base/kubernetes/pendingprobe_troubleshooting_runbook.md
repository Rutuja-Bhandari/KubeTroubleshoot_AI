# Pending / Probe Failure Troubleshooting Runbook

## Problem

A Kubernetes Pod is either:

1. Stuck in `Pending` because the scheduler cannot place it on a node, or
2. Running but `NotReady` because a liveness, readiness, or startup probe is failing.

These are separate issues:

| State | Meaning | Primary concern |
|---|---|---|
| `Pending` | Pod has not been scheduled to a node | Scheduler, capacity, affinity, taints, storage |
| `Running` but `NotReady` | Container is running, but the Pod is excluded from Service traffic | Readiness probe or application dependency |
| `Running` then restarted repeatedly | Container is being restarted by kubelet | Liveness or startup probe failure |
| `CrashLoopBackOff` | Container repeatedly exits or is killed | Application error, bad probe command, misconfiguration |

A `Pending` Pod means Kubernetes has accepted the Pod object but has not yet scheduled it onto a node. The most common reason is that no node satisfies its CPU, memory, storage, affinity, taint/toleration, or topology requirements. [18][21][25]

## Symptoms

### Pending Pod

```text
NAME                          READY   STATUS    RESTARTS   AGE
production-api-gateway-xxxx   0/1     Pending   0          5m
```

Common scheduler event:

```text
Warning  FailedScheduling  pod/production-api-gateway-xxxx
0/5 nodes are available: 3 Insufficient cpu, 2 node(s) had untolerated taint.
```

### Probe Failure

```text
NAME                          READY   STATUS    RESTARTS   AGE
production-api-gateway-xxxx   0/1     Running   3          8m
```

Common events:

```text
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
Warning  Unhealthy  Liveness probe failed: Get "http://10.244.1.18:8080/healthz": dial tcp ... connect: connection refused
Warning  Unhealthy  Startup probe failed: command 'healthcheck.sh' exited with code: 1
```

Probe behavior:

- A failing **readiness probe** removes the Pod from Service endpoints; it does not restart the container.
- A failing **liveness probe** causes kubelet to restart the container after the failure threshold is exceeded.
- A failing **startup probe** prevents liveness and readiness probes from running until startup succeeds; if it never succeeds within its configured threshold, kubelet restarts the container. [17][19][24]

## Probe Types

| Probe | Purpose | Effect on failure |
|---|---|---|
| `startupProbe` | Determines whether the application has finished starting | Disables liveness and readiness checks until it succeeds; repeated failure can restart the container |
| `readinessProbe` | Determines whether the Pod can receive traffic | Pod is marked `NotReady` and removed from Service endpoints |
| `livenessProbe` | Determines whether the application is healthy and should continue running | Container is restarted after repeated failures |

Use a startup probe for applications with long initialization time, such as JVM warmup, cache loading, schema migration checks, or dependency initialization. [17][19][23]

## Initial Triage

### 1. Identify the Pod State

```bash
kubectl get pod <pod-name> -n <namespace> -o wide
```

Example:

```bash
kubectl get pod production-api-gateway-7f89c6b4-x9z2l -n production -o wide
```

Determine whether the issue is:

- `Pending`
- `Running` but `0/1` ready
- `Running` with increasing restarts
- `CrashLoopBackOff`

### 2. Inspect Pod Events

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Example:

```bash
kubectl describe pod production-api-gateway-7f89c6b4-x9z2l -n production
```

Focus on:

- `Events`
- `Conditions`
- `Containers`
- `Last State`
- `Restart Count`
- `Readiness`
- `Liveness`
- `Startup`

For a Pending Pod, look for `FailedScheduling`.

For a probe issue, look for `Unhealthy`, `Readiness probe failed`, `Liveness probe failed`, or `Startup probe failed`.

## Debugging a Pending Pod

### Step 1: Read the FailedScheduling Message

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A 20 Events
```

Common messages and meanings:

| Scheduler Message | Likely Cause | Resolution |
|---|---|---|
| `Insufficient cpu` | No node has enough allocatable CPU | Reduce CPU request, scale down workloads, or add node capacity |
| `Insufficient memory` | No node has enough allocatable memory | Reduce memory request, free capacity, or add nodes |
| `node(s) had untolerated taint` | Pod does not tolerate a node taint | Add a matching toleration or schedule to another node pool |
| `node(s) didn't match Pod's node affinity` | Node selector or affinity rules exclude all nodes | Correct `nodeSelector`, `affinity`, labels, or zones |
| `node(s) didn't match Pod's anti-affinity rules` | Anti-affinity prevents placement | Relax topology constraints or add eligible nodes |
| `pod has unbound immediate PersistentVolumeClaims` | PVC cannot bind to a volume | Check StorageClass, PVC, PV, zone, and storage capacity |
| `too many pods` | Node has reached its Pod capacity limit | Add nodes or reduce Pod density |

Kubernetes identifies insufficient CPU or memory as a frequent cause of Pods remaining Pending. [18][21]

### Step 2: Check Node Capacity

```bash
kubectl describe nodes
```

For a specific node:

```bash
kubectl describe node <node-name>
```

Review:

```text
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                3500m (87%)   7200m (180%)
  memory             12Gi (80%)    20Gi (133%)
```

The scheduler schedules based on resource **requests**, not actual current usage. If requested CPU or memory is near node allocatable capacity, new Pods may remain Pending even if actual utilization appears low. [25]

Check node allocatable capacity:

```bash
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
CPU_ALLOCATABLE:.status.allocatable.cpu,\
MEMORY_ALLOCATABLE:.status.allocatable.memory
```

### Step 3: Check Node Labels, Taints, and Affinity

List node labels:

```bash
kubectl get nodes --show-labels
```

List node taints:

```bash
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
TAINTS:.spec.taints
```

Check the Pod scheduling constraints:

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Review:

```yaml
nodeSelector:
  workload: production

affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: topology.kubernetes.io/zone
          operator: In
          values:
          - ap-south-1a

tolerations:
- key: dedicated
  operator: Equal
  value: production
  effect: NoSchedule
```

Common mistakes:

- `nodeSelector` refers to a label that no node has.
- Affinity requires an availability zone with no capacity.
- Pod has a toleration for a taint key but not the correct `value` or `effect`.
- Anti-affinity rules require spreading across more zones or nodes than exist.

### Step 4: Check PersistentVolumeClaims

```bash
kubectl get pvc -n <namespace>
kubectl describe pvc <pvc-name> -n <namespace>
```

A Pending Pod may be waiting for a PVC to bind.

Look for:

```text
Waiting for a volume to be created
```

Check:

- PVC state is `Bound`.
- `storageClassName` exists and is valid.
- Storage provisioner is healthy.
- Requested storage size is available.
- Volume zone matches the node zone.
- `volumeBindingMode: WaitForFirstConsumer` is understood by the StorageClass.

### Step 5: Resolve Pending Pod

Choose the appropriate action:

```bash
# Reduce Deployment replicas temporarily
kubectl scale deployment <deployment-name> -n <namespace> --replicas=<lower-count>

# Reduce resource requests after validating actual usage
kubectl edit deployment <deployment-name> -n <namespace>

# Add worker-node capacity through the cloud provider or Cluster Autoscaler
# Correct nodeSelector, affinity, tolerations, or PVC configuration
kubectl edit deployment <deployment-name> -n <namespace>
```

Do not blindly reduce requests in production. First compare the request with observed memory and CPU usage; reducing requests can improve scheduling but may increase eviction or OOM risk.

## Debugging Probe Failures

### Step 1: Identify the Failing Probe

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Example:

```text
Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
```

Classify the failure:

| Probe failure | Typical meaning | First check |
|---|---|---|
| `connection refused` | Application is not listening on the probe port | Application startup, port, bind address |
| `context deadline exceeded` | Probe timed out | Application latency, dependency latency, timeout settings |
| `HTTP probe failed with statuscode: 404` | Wrong probe path | Probe endpoint and application routes |
| `HTTP probe failed with statuscode: 401/403` | Probe endpoint requires authentication | Remove auth requirement from health endpoint |
| `HTTP probe failed with statuscode: 500/503` | Application or dependency unhealthy | Application logs and dependency health |
| `command exited with code 1` | Exec probe command failed | Run command manually in container |
| `TCP probe failed` | TCP port is not open | Listen address, port, firewall, application startup |

### Step 2: Check Container Logs

```bash
kubectl logs <pod-name> -n <namespace>
```

For a restarted container:

```bash
kubectl logs <pod-name> -n <namespace> --previous
```

Look for:

- Application still initializing.
- Database, cache, message broker, or downstream API unavailable.
- Incorrect listen host or port.
- Missing configuration or secrets.
- Fatal exceptions during startup.
- Health endpoint returning an error.

### Step 3: Test the Probe Endpoint

If the container is running, execute a check inside it:

```bash
kubectl exec -it <pod-name> -n <namespace> -- /bin/sh
```

Then test:

```bash
# HTTP endpoint
wget -qO- http://localhost:8080/healthz
curl -v http://localhost:8080/healthz

# Check listening ports
netstat -lntp || ss -lntp

# Test exec probe command
./healthcheck.sh
echo $?
```

If `curl` or `wget` is unavailable, use the application’s existing diagnostic endpoint or a minimal exec probe.

### Step 4: Review Probe Configuration

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Example probe configuration:

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  initialDelaySeconds: 15
  periodSeconds: 20
  timeoutSeconds: 3
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 30
```

Common misconfigurations:

| Issue | Example | Fix |
|---|---|---|
| Wrong port | Probe uses `80`, app listens on `8080` | Set `port: 8080` |
| Wrong path | Probe calls `/health`, app exposes `/healthz` | Correct the path |
| Wrong scheme | HTTPS endpoint checked as HTTP | Set `scheme: HTTPS` |
| App binds only to localhost | App listens on `127.0.0.1` | Bind to `0.0.0.0` |
| Startup too slow | Liveness starts before app is ready | Add startup probe or increase delay |
| Timeout too low | Probe times out during GC or dependency delay | Increase `timeoutSeconds` |
| Probe checks downstream dependencies | Database outage marks every Pod unready | Keep readiness focused on local service health |

### Step 5: Resolve Probe Failures

#### Fix application startup

If the application needs more time to initialize, add a startup probe:

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 30
```

This allows up to approximately 300 seconds for startup before liveness and readiness checks begin. Kubernetes documents that a startup probe disables the other probes until it succeeds. [17][19][23]

#### Fix readiness behavior

Use readiness to prevent traffic from reaching a Pod that cannot serve requests:

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

Do not use readiness as a restart mechanism. A failing readiness probe removes the Pod from Service endpoints but does not restart it. [17][19][24]

#### Fix liveness behavior

Use liveness only for unrecoverable application deadlock or hang conditions:

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 20
  timeoutSeconds: 3
  failureThreshold: 3
```

Avoid making liveness depend on external systems such as databases or third-party APIs. A temporary downstream outage can otherwise cause a restart storm.

## Recommended Probe Design

For a typical HTTP production service:

```yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  periodSeconds: 20
  timeoutSeconds: 3
  failureThreshold: 3
```

Recommended endpoint semantics:

| Endpoint | Should verify | Should not verify |
|---|---|---|
| `/health/startup` | Process started and basic configuration loaded | Full dependency availability |
| `/health/live` | Process is not deadlocked or hung | External database or API health |
| `/health/ready` | Pod can safely serve traffic | Nonessential optional dependencies |

## Production Checklist

Before declaring the issue resolved, verify:

- [ ] Pod is no longer `Pending`.
- [ ] Pod reaches `Running` and `Ready`.
- [ ] Pod appears as an endpoint behind its Service.
- [ ] Probe endpoint returns success consistently.
- [ ] Restart count is stable.
- [ ] Application logs show no repeated startup or probe errors.
- [ ] Resource requests match observed production usage.
- [ ] Node has sufficient allocatable CPU and memory.
- [ ] Node selector, affinity, tolerations, and topology constraints are valid.
- [ ] PVC is bound, if used.
- [ ] Probe timeouts and thresholds are appropriate for startup and runtime behavior.
- [ ] Alerts exist for `Pending` Pods, `FailedScheduling`, probe failures, and restart count increases.

## Verification

Run:

```bash
kubectl get pod <pod-name> -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl get endpoints <service-name> -n <namespace>
```

Expected result:

```text
NAME                          READY   STATUS    RESTARTS   AGE
production-api-gateway-xxxx   1/1     Running   0          10m
```

The Pod should:

- Leave `Pending` state.
- Reach `1/1` or `N/N` readiness.
- Remain listed in Service endpoints.
- Stop generating `FailedScheduling` or `Unhealthy` events.
- Maintain a stable restart count under normal and peak traffic.