# CrashLoopBackOff Troubleshooting Runbook

## 1. Purpose

Use this runbook to investigate Kubernetes Pods whose containers
repeatedly start, crash, and restart. The goal is to identify the
underlying cause from Kubernetes state, events, container logs, and
resource information before recommending a fix.

## 2. Problem and status meaning

`CrashLoopBackOff` is a container waiting reason, not an application
error code. It means Kubernetes is repeatedly restarting a container
that has exited or failed, and is delaying subsequent restart attempts
using a backoff period.

The backoff delay increases between attempts and is capped at
approximately five minutes. The container can continue to restart until
the underlying problem is corrected.

`ImagePullBackOff` is different: Kubernetes cannot pull the container
image, so the container has not started successfully. Do not treat
`ImagePullBackOff` and `CrashLoopBackOff` as interchangeable diagnoses.

## 3. Symptoms

Common indicators include:

-   Pod status shows `CrashLoopBackOff` or, for an init container,
    `Init:CrashLoopBackOff`.
-   The container restart count keeps increasing.
-   The container starts and exits, often with a non-zero exit code.
-   Pod events include messages such as
    `Back-off restarting failed container`.
-   The Pod is not Ready or its workload has fewer available replicas
    than desired.

A high restart count or a non-Ready Pod is a useful signal, but neither
alone proves the root cause.

## 4. Common root causes

  -----------------------------------------------------------------------
  Potential cause                     Evidence to look for
  ----------------------------------- -----------------------------------
  Application error or unhandled      Previous container logs contain
  exception                           errors, exceptions, or stack traces

  Incorrect configuration             Missing environment variable,
                                      invalid argument, missing
                                      configuration file, or invalid
                                      startup command

  Missing or unavailable dependency   Application logs show connection
                                      failures or timeouts; referenced
                                      ConfigMap or Secret may be missing

  Out-of-memory termination           Container's last termination reason
                                      is `OOMKilled`; exit code is often
                                      `137`

  Liveness probe failure              Pod events report
                                      `Liveness probe failed`; the
                                      kubelet may restart the container

  Incorrect command, entrypoint, or   Logs or termination details
  permissions                         indicate an executable is missing
                                      or a file cannot be accessed

  Persistent storage problem          Events show volume mount errors, or
                                      application logs show file-system,
                                      permission, or read-only errors

  Init container failure              Pod status shows
                                      `Init:CrashLoopBackOff`; the main
                                      application container may never
                                      have started

  Network or DNS dependency issue     Logs show DNS resolution failures,
                                      refused connections, or timeouts to
                                      a required service
  -----------------------------------------------------------------------

Treat exit codes as clues, not definitive proof. For example, `137` can
indicate a SIGKILL and should be interpreted together with the
termination reason and events.

## 5. Investigation workflow

Follow this sequence:

**Get status → Describe Pod → Read previous logs → Check events → Check
resources and dependencies → Identify cause → Apply a targeted fix →
Verify.**

### Step 1: Find the affected Pod

``` bash
kubectl get pods -n <namespace>
```

For additional details, including the node hosting each Pod:

``` bash
kubectl get pods -n <namespace> -o wide
```

Check the `STATUS`, `READY`, and `RESTARTS` columns. Record the Pod
name, namespace, restart count, and whether the status is
`CrashLoopBackOff` or `Init:CrashLoopBackOff`.

### Step 2: Describe the Pod

``` bash
kubectl describe pod <pod-name> -n <namespace>
```

Review:

-   Container and init-container states.
-   `Last State`, termination reason, and exit code.
-   Restart count.
-   Liveness, readiness, and startup probe configuration and failures.
-   Resource requests and limits.
-   Volume mounts and configuration references.
-   The `Events` section, especially `BackOff`, `FailedMount`, probe
    failures, and dependency-related errors.

### Step 3: Read logs from the previous container instance

The current container may have little or no output after a restart.
Retrieve the previous terminated instance's logs:

``` bash
kubectl logs <pod-name> -n <namespace> --previous
```

For a multi-container Pod, specify the container:

``` bash
kubectl logs <pod-name> -n <namespace> -c <container-name> --previous
```

Look for startup exceptions, missing configuration, invalid command or
file paths, permission errors, OOM-related messages, and dependency
connection failures.

For init containers, specify the init-container name:

``` bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.spec.initContainers[*].name}'
```

``` bash
kubectl logs <pod-name> -n <namespace> \
  -c <init-container-name> --previous
```

If a Pod has sidecars, inspect their logs individually as well.

### Step 4: Check events

``` bash
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

To narrow events to a particular Pod:

``` bash
kubectl get events -n <namespace> \
  --field-selector involvedObject.name=<pod-name> \
  --sort-by='.lastTimestamp'
```

Events can help distinguish application exits from probe failures,
volume issues, and other Kubernetes-level problems. Event history may be
limited, so correlate it with the current Pod description and logs.

### Step 5: Check resource usage and termination details

If Metrics Server is installed and reporting data:

``` bash
kubectl top pod <pod-name> -n <namespace> --containers
```

Check the container's last exit code:

``` bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.exitCode}'
```

Check for `OOMKilled` in `kubectl describe pod`. If memory exhaustion is
suspected, inspect the configured memory limit, actual usage where
available, and whether a namespace `LimitRange` applies defaults:

``` bash
kubectl get limitrange -n <namespace>
kubectl describe limitrange -n <namespace>
```

A point-in-time metrics reading may not capture the peak usage that
caused a termination.

### Step 6: Inspect the controlling workload and configuration

Identify the controller in the Pod description (often a ReplicaSet owned
by a Deployment). Inspect the relevant workload configuration:

``` bash
kubectl describe deployment <deployment-name> -n <namespace>
kubectl get deployment <deployment-name> -n <namespace> -o yaml
```

Check the image, command, arguments, environment-variable references,
resource requests and limits, probes, volumes, and ConfigMap/Secret
references. Avoid printing or sharing Secret values.

For a Pod managed by another controller, inspect the corresponding
controller rather than assuming it is a Deployment.

## 6. Cause-specific remediation guidance

### A. Application or configuration errors

**Evidence:** Previous logs show an exception, a required environment
variable is missing, a file cannot be found, or the process exits after
startup.

**Actions:**

-   Correct the application error or invalid configuration.
-   Confirm referenced ConfigMaps and Secrets exist in the same
    namespace and use the intended keys.
-   Check `command` and `args` against the executable and entrypoint
    provided by the container image.
-   Confirm required files exist and have suitable permissions.
-   Build and publish a corrected image if the application code or
    packaged files need changes, then update the workload to use it.

### B. Out-of-memory termination

**Evidence:** The last termination reason is `OOMKilled`, often
accompanied by exit code `137`.

**Actions:**

-   Compare the container's memory limit with observed usage and
    expected startup or workload peaks.
-   Review application memory behavior and, for multi-container Pods,
    inspect each container's resource usage.
-   Adjust memory requests or limits only after checking capacity and
    the workload's actual needs.
-   For JVM workloads, ensure heap settings leave room for non-heap
    memory, native libraries, and thread stacks.

Do not conclude that every exit code `137` is an OOM kill without
checking the termination reason and related evidence.

### C. Liveness or startup probe failures

**Evidence:** Events report `Liveness probe failed`, and the container
is restarted.

**Actions:**

-   Verify the probe's path, port, command, and timing settings.
-   If startup legitimately takes longer, consider a `startupProbe` so
    liveness checks do not begin too early.
-   Tune thresholds and timeouts to reflect the application's startup
    and response characteristics.
-   Avoid making a liveness probe depend on a remote service when a
    temporary dependency outage should not restart the application.

**Important:** A failed liveness probe can cause a container restart. A
failed readiness probe normally marks the Pod as not ready and removes
it from Service endpoints; it does not, by itself, restart the
container.

### D. Missing dependency or network/DNS failure

**Evidence:** Previous logs show DNS lookup failures, connection
timeouts, refused connections, or unavailable dependencies.

**Actions:**

-   Verify the dependency's service name, address, port, and
    configuration.
-   Confirm the dependency is available and that network policies and
    firewall rules allow the required traffic.
-   Check DNS resolution from an appropriate diagnostic environment.
-   Verify credentials and referenced configuration without exposing
    secret values.
-   Add or correct retry and timeout behavior when appropriate, while
    ensuring the application does not hide a persistent configuration
    problem.

### E. Persistent storage or permission issues

**Evidence:** Events show `FailedMount`, or logs report missing files,
read-only file systems, or permission denied.

**Actions:**

-   Verify the PersistentVolumeClaim, volume, mount path, and storage
    configuration.
-   Check whether the application expects to write to a read-only mount.
-   Review the container's user/group settings and applicable security
    context.
-   Correct the storage or permissions configuration based on the
    observed error.

### F. Init container failure

**Evidence:** Pod status shows `Init:CrashLoopBackOff` or `Init:Error`.

**Actions:**

-   Inspect the `Init Containers` section in `kubectl describe pod`.
-   Read logs from the failing init container with
    `kubectl logs ... -c <init-container-name> --previous`.
-   Check for missing ConfigMaps/Secrets, failed volume mounts,
    unavailable dependencies, and invalid init-container commands.
-   Fix the init container's specific failure before investigating the
    main application container, which may not have started yet.

## 7. Verification

After applying a cause-specific fix, check the Pod and its controlling
workload:

``` bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl get deployment <deployment-name> -n <namespace>
```

Where applicable, inspect rollout progress:

``` bash
kubectl rollout status deployment/<deployment-name> -n <namespace>
```

A successful verification should establish that:

-   The container and Pod are Ready and the workload has the expected
    available replicas.
-   The restart count is no longer increasing across subsequent checks.
-   New events do not show the same failure recurring.
-   Application logs indicate successful startup and expected behavior.

A `Running` status alone is not sufficient if the Pod is not Ready or
the restart count continues to rise.

## 8. Safe troubleshooting practices

-   Gather evidence before changing the workload.
-   Prefer `kubectl describe pod` and previous-container logs when the
    application container repeatedly exits.
-   Do not delete or restart Pods repeatedly as a substitute for fixing
    the cause; the same failure may recur.
-   Do not increase memory limits, change probes, or modify networking
    without evidence supporting the change.
-   Avoid printing credentials or Secret contents in logs, terminal
    output, or incident reports.
-   Before making a production change, review the rollout history and
    have a rollback plan:

``` bash
kubectl rollout history deployment/<deployment-name> -n <namespace>
```

If a deployment change causes a regression, an authorized operator can
consider:

``` bash
kubectl rollout undo deployment/<deployment-name> -n <namespace>
```

Use rollback only when appropriate for the workload and deployment
process.

## 9. RCA knowledge record for KubeTroubleshoot AI

Use this structure when storing a CrashLoopBackOff incident as a
knowledge-base record:

-   **Incident type:** CrashLoopBackOff
-   **Observed symptoms:** Pod status, readiness, restart count, and
    affected container
-   **Evidence:** Previous logs, termination reason and exit code,
    events, probe results, resource information, and relevant workload
    configuration
-   **Likely root cause:** A cause directly supported by the evidence
-   **Confidence:** High only when multiple relevant signals support the
    same cause; otherwise mark as medium/low or unknown
-   **Recommended investigation:** The next safe command or evidence
    source needed to distinguish remaining possibilities
-   **Recommended fix:** A targeted action tied to the supported cause
-   **Verification criteria:** Readiness, stable restart count, expected
    replicas, and absence of recurring failure evidence

Do not infer a definitive root cause from `CrashLoopBackOff` alone. If
the available evidence is insufficient, report the uncertainty and
request the next useful diagnostic signal.

## 10. Quick diagnostic checklist

-   [ ] Confirm the affected Pod, namespace, status, and restart count.
-   [ ] Describe the Pod and review container state, exit reason,
    probes, and events.
-   [ ] Read logs from the previous terminated container.
-   [ ] If an init container is failing, inspect its state and previous
    logs.
-   [ ] Check memory/resource information when indicated by evidence.
-   [ ] Inspect the controlling workload, configuration, dependencies,
    and storage as relevant.
-   [ ] Apply a targeted fix rather than repeatedly restarting or
    deleting the Pod.
-   [ ] Verify readiness, stable restarts, expected replicas, and
    absence of recurring errors.
