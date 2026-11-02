# OOMKilled Troubleshooting Runbook

## Problem

A Kubernetes container is terminated because it exceeds its configured memory limit.

`OOMKilled` is a deterministic, kernel-enforced failure mode. It means that a process inside the container attempted to use more memory than the container cgroup or the worker node could safely allow.

The container is typically terminated with:

- `Reason: OOMKilled`
- `Exit Code: 137`

Exit code 137 follows the Unix convention:

```text
128 + signal number
128 + 9 = 137
```

Signal 9 is `SIGKILL`, which cannot be caught, ignored, or handled gracefully by the application. [3][5][11]

## Symptoms

The container or Pod may show one or more of the following:

```text
State:          Waiting
  Reason:       CrashLoopBackOff

Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
```

Common indicators:

- Container repeatedly restarts.
- Pod enters `CrashLoopBackOff`.
- `Restart Count` increases.
- Application logs stop abruptly without a graceful shutdown message.
- Memory usage rises steadily over time or spikes during traffic peaks.
- Kubernetes events mention memory pressure or OOM termination.

## Architecture: How OOMKilled Happens

### Linux OOM Killer

Linux may overcommit virtual memory: it allows applications to reserve more virtual address space than physical RAM and swap can simultaneously support.

When actual memory demand exceeds available RAM and swap, the kernel invokes the Out of Memory Killer to preserve node stability.

The OOM Killer:

1. Evaluates candidate processes using an OOM “badness” score.
2. Prefers terminating processes with high memory consumption and lower system importance.
3. Sends `SIGKILL` to the selected process.
4. Causes the container runtime to record exit code 137.

A process killed by `SIGKILL` cannot perform cleanup, flush buffers, save state, or shut down gracefully. [5][6][12]

### Container Memory Limits and cgroups

A Kubernetes container is not a virtual machine. It is an isolated Linux process group controlled through namespaces and cgroups.

When a memory limit is configured, the container runtime translates it into a cgroup memory constraint:

- cgroups v1: `memory.limit_in_bytes`
- cgroups v2: `memory.max`

When total memory usage within that cgroup reaches the configured limit and further allocation is required, the kernel triggers a cgroup-local OOM event.

This is usually a container-level OOM:

```text
Container memory usage > container memory limit
        ↓
cgroup memory limit reached
        ↓
Kernel OOM Killer targets process in cgroup
        ↓
SIGKILL
        ↓
Exit Code 137
        ↓
Kubernetes status: OOMKilled
```

Kubernetes documents that memory limits are enforced by the kernel through OOM kills. [3]

## Kubernetes Requests, Limits, and QoS

Example Pod resource configuration:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: production-api-gateway
  namespace: production
spec:
  containers:
  - name: application-engine
    image: internal-registry.net/apps/gateway:v2.4.1
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "2000m"
```

### Memory Requests

- Used by the Kubernetes scheduler to select a node with enough allocatable memory.
- Represent the amount of memory reserved for the Pod.
- A Pod using more memory than requested becomes an eviction candidate during node memory pressure.

### Memory Limits

- Represent a hard runtime ceiling enforced through cgroups.
- Unlike CPU, memory is not compressible.
- When a container reaches its memory limit, it cannot simply be throttled; the kernel may terminate it.

### Quality of Service Classes

| QoS Class | Resource Definition | Eviction / OOM Risk |
|---|---|---|
| `Guaranteed` | Every container has CPU and memory requests and limits, and requests equal limits | Lowest risk |
| `Burstable` | At least one request or limit is set, but the Pod does not meet `Guaranteed` criteria | Medium risk |
| `BestEffort` | No requests or limits are set | Highest risk |

Kubernetes uses `oom_score_adj` to influence which processes the Linux OOM Killer prefers during node-level memory pressure. `Guaranteed` Pods receive a highly protective score of `-997`, while `BestEffort` Pods receive `1000`, making them the first likely victims. [1][4][6]

## Investigation

### Step 1: Inspect Pod State

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Example:

```bash
kubectl describe pod production-api-gateway-7f89c6b4-x9z2l -n production
```

Look for:

```text
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
```

If `Reason: OOMKilled` and `Exit Code: 137` are present, the container was terminated due to memory exhaustion.

If `Exit Code: 137` appears with `Reason: Error`, the process may have been killed by an external `kill -9`, a parent process, or another system-level mechanism rather than a direct container cgroup OOM event.

### Step 2: Check Previous Container Logs

After a restart, the current container logs may not include the failed process output. Retrieve logs from the previous container instance:

```bash
kubectl logs <pod-name> -n <namespace> --previous --tail=200
```

Example:

```bash
kubectl logs production-api-gateway-7f89c6b4-x9z2l -n production --previous --tail=200
```

Look for patterns such as:

- Large database result sets loaded into memory.
- Large file uploads, downloads, or image processing.
- Unbounded caches, queues, maps, or lists.
- Excessive concurrent requests.
- Runtime-specific memory errors, such as Java `java.lang.OutOfMemoryError`.

### Step 3: Inspect Kubernetes Events

```bash
kubectl get events -n <namespace> --sort-by='.metadata.creationTimestamp'
```

Look for messages such as:

```text
System OOM encountered
Killed process
invoked oom-killer
```

### Step 4: Inspect Resource Configuration

Check the Pod:

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Check the owning Deployment:

```bash
kubectl get deployment <deployment-name> -n <namespace> -o yaml
```

Confirm:

```yaml
resources:
  requests:
    memory: ...
  limits:
    memory: ...
```

Compare the configured memory limit with actual historical memory usage from Prometheus, Grafana, CloudWatch, Azure Monitor, or another monitoring system.

### Step 5: Check Node-Level Kernel Logs

If multiple Pods are affected, or if the issue appears node-wide, inspect the worker node kernel logs:

```bash
dmesg -T | grep -E -i 'oom|kill'
```

Example output:

```text
Memory cgroup out of memory: Kill process 28491 (node) score 1005 or sacrifice child
Task in /kubepods.slice/kubepods-burstable.slice/pod... killed as a result of limit_in_bytes
```

Interpretation:

- `Memory cgroup out of memory` usually indicates a container exceeded its own memory limit.
- A broader node OOM event may indicate the entire node ran out of memory.
- If the node is affected, check kubelet reservation settings, node allocatable memory, and Pod density.

## Common Root Causes

### 1. Runtime Heap Exceeds Container Limit

Managed runtimes may allocate memory beyond the application heap.

Examples of additional memory consumption:

- JVM metaspace, thread stacks, code cache, GC overhead, and native memory.
- Node.js V8 overhead and native addons.
- Python interpreter overhead and native libraries.
- .NET runtime overhead.

A common Java misconfiguration is:

```text
Container memory limit: 1Gi
JVM maximum heap:       -Xmx1024m
```

The JVM heap alone may consume the entire container limit before accounting for non-heap memory.

Preferred Java configuration:

```bash
java -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -jar application.jar
```

This reserves approximately 25% of the container memory limit for non-heap overhead.

For Node.js, explicitly constrain the V8 heap:

```bash
node --max-old-space-size=800 server.js
```

For a 1Gi container limit, a value around 800 MB is often a safer starting point, but it must be validated with workload-specific testing.

### 2. Application Memory Leak

A memory leak occurs when allocated memory is no longer needed but is not released.

Common examples:

- Unintended global variables.
- Closures retaining large objects.
- Forgotten timers or intervals.
- Unbounded in-memory caches.
- Goroutines blocked indefinitely.
- Event listeners that are never removed.
- Large objects retained in queues or session state.

Typical memory pattern:

```text
Memory Usage
   ^
   |                                             OOMKilled
   |                                          /
   |                                       /
   |                                    /
   |                                 /
   |                              /
   |                           /
   |                        /
   |_____________________/________________________> Time
```

A steady upward trend independent of traffic volume often indicates a leak.

### 3. Traffic Spike or Unbounded Concurrency

A sudden increase in requests can cause memory usage to rise sharply.

Common causes:

- Large JSON, XML, image, or file payloads.
- Loading entire database result sets into memory.
- Missing pagination.
- Excessive concurrent worker threads or goroutines.
- Unbounded request queues.
- Large temporary buffers per request.
- Retry storms amplifying load.

If memory usage correlates directly with request rate or concurrent connections, optimize request handling and enforce concurrency limits.

### 4. Memory Limit Is Too Low

The application may be operating correctly but may simply require more memory than allocated.

Increase the memory limit only after confirming that:

- Memory usage is legitimate for the workload.
- There is no leak or inefficient processing.
- The Pod has sufficient headroom for traffic spikes and runtime overhead.
- Node capacity can support the updated resource request.

### 5. Node-Level Memory Overcommit

If several Pods burst simultaneously, the node may exhaust memory faster than kubelet eviction can respond.

Potential node-level causes:

- Missing or insufficient `--system-reserved` configuration.
- Missing or insufficient `--kube-reserved` configuration.
- Too many Pods scheduled per node.
- Pods consistently using more memory than requested.
- Insufficient node allocatable memory.

In this case, the OOM Killer may terminate processes across the node, not only within one container cgroup.

## Resolution

### 1. Confirm Whether Memory Growth Is Legitimate

Classify the memory pattern:

| Pattern | Likely Cause | Action |
|---|---|---|
| Stable high usage | Limit too low or workload genuinely large | Increase limit after validation |
| Gradual rise over time | Memory leak | Profile and fix application |
| Sharp spike with traffic | Unbounded concurrency or large payloads | Add pagination, streaming, backpressure, concurrency limits |
| Spike after deployment | Regression or runtime misconfiguration | Roll back, compare versions, inspect runtime flags |
| Multiple Pods affected on one node | Node memory pressure | Check node capacity, reservations, and Pod density |

### 2. Correct Runtime Configuration

For Java:

```bash
java -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -jar application.jar
```

For Node.js:

```bash
node --max-old-space-size=800 server.js
```

Avoid hardcoding runtime heap values that equal or exceed the container memory limit.

### 3. Increase Memory Limits Carefully

Example:

```yaml
resources:
  requests:
    memory: "1Gi"
  limits:
    memory: "2Gi"
```

Guidelines:

- Increase the request if the workload consistently needs more memory.
- Increase the limit if short-lived bursts require additional headroom.
- Do not increase limits indefinitely without identifying the underlying cause.
- Ensure the change does not exceed node allocatable capacity.
- Roll out gradually and monitor the new memory baseline.

### 4. Fix Application-Level Issues

Potential fixes include:

- Add pagination for database queries.
- Stream large files instead of loading them fully into memory.
- Bound caches and queues.
- Remove unused global references.
- Fix goroutine, thread, timer, and listener leaks.
- Add request timeouts and concurrency limits.
- Use backpressure for high-volume workloads.
- Optimize serialization and deserialization of large payloads.

### 5. Use Vertical Pod Autoscaling

If memory requirements vary and are difficult to predict, consider Vertical Pod Autoscaler:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-gateway-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: "apps/v1"
    kind: Deployment
    name: production-api-gateway
  updatePolicy:
    updateMode: "Auto"
```

Use VPA cautiously in production:

- It can restart Pods when applying updated resource recommendations.
- Validate recommendations in `Initial` or `Off` mode before enabling automatic updates.
- Ensure Pod Disruption Budgets and rollout strategies protect availability.

## Prevention

- Set realistic memory requests based on observed steady-state usage.
- Set memory limits with enough headroom for bursts and runtime overhead.
- Keep runtime heap settings below the container memory limit.
- Monitor container memory usage, working set, and memory utilization trends.
- Alert before memory usage reaches the configured limit.
- Load-test deployments before major traffic events.
- Configure kubelet and system reservations on worker nodes.
- Avoid running critical workloads as `BestEffort`.
- Use `Guaranteed` QoS for memory-critical, latency-sensitive services where appropriate.
- Review memory usage after every application or dependency upgrade.

## Verification

After applying a fix:

1. Confirm the Pod is running:

```bash
kubectl get pod <pod-name> -n <namespace>
```

2. Confirm no recent OOMKilled events:

```bash
kubectl get events -n <namespace> --sort-by='.metadata.creationTimestamp'
```

3. Confirm the restart count is stable:

```bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.status.containerStatuses[*].restartCount}'
```

4. Monitor memory usage for an appropriate duration:

- At least one normal traffic cycle.
- Preferably through peak traffic.
- Long enough to detect a slow memory leak.

Success criteria:

- Pod remains in `Running` state.
- No new `OOMKilled` events occur.
- Restart count does not increase.
- Memory usage remains below the configured limit with acceptable headroom.
- Application latency, error rate, and throughput remain stable.