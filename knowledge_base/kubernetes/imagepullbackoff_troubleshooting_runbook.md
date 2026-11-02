# ImagePullBackOff Troubleshooting Runbook

## 1. Purpose

Use this runbook to investigate a Kubernetes container that cannot
download its image from a container registry. The goal is to identify
the specific cause from Kubernetes evidence, apply the smallest
appropriate correction, and verify recovery.

## 2. Problem and status meaning

`ImagePullBackOff` means Kubernetes could not pull the image required by
a container and is retrying after progressively longer delays.
`ErrImagePull` commonly appears for the initial failed pull attempt.

The container normally remains in the `Waiting` state until the image
can be pulled. The Pod may be shown as `Pending`, or it may have a
different overall status if it contains multiple containers.

**Important:** `ImagePullBackOff` is a symptom, not a root cause. Do not
diagnose the cause from the status alone. Use the event message and the
Pod's image configuration to narrow it down.

## 3. Common root causes

1.  **Incorrect image reference:** registry hostname, repository path,
    or image name is wrong.
2.  **Missing image or tag:** the requested tag or digest does not
    exist, or the image was moved or deleted.
3.  **Authentication failure:** credentials are missing, invalid, or
    expired.
4.  **Authorization failure:** the identity can authenticate but does
    not have permission to pull the repository.
5.  **Image pull Secret configuration problem:** the Secret is missing,
    is in the wrong namespace, has the wrong registry credentials, or is
    not referenced by the Pod or its ServiceAccount.
6.  **Registry connectivity problem:** the node cannot reach the
    registry because of DNS, routing, firewall, proxy, TLS certificate,
    or registry availability issues.
7.  **Registry rate limiting:** the registry rejects requests because a
    pull or request limit has been reached.
8.  **Node-side image-pull problem:** insufficient node disk space or
    another container-runtime/node issue prevents image download or
    extraction. Confirm this from the event message and node evidence
    rather than assuming it.

## 4. Investigation workflow

Set these values for the commands below:

-   `<namespace>`: namespace containing the Pod.
-   `<pod-name>`: affected Pod name.
-   `<deployment-name>`: owning Deployment, if applicable.
-   `<container-name>`: container name inside the Pod.

### Step 1: Find the affected Pod

``` bash
kubectl get pods -n <namespace>
```

Check the `STATUS` column for `ImagePullBackOff` or `ErrImagePull`.

### Step 2: Inspect Pod details and events

``` bash
kubectl describe pod <pod-name> -n <namespace>
```

Review **Events**, **Containers**, **Image**, and **State**. Capture the
exact failure message, not just the status.

Useful clues include:

-   `manifest unknown` or `not found` --- often an incorrect repository,
    tag, or digest.
-   `pull access denied`, `unauthorized`, or `authentication required`
    --- investigate authentication, authorization, and pull Secret
    configuration.
-   `no such host`, timeout, connection refused, or TLS errors ---
    investigate registry DNS, network access, proxy, firewall, or
    certificates.
-   `toomanyrequests` or a rate-limit message --- investigate registry
    limits and pull frequency.
-   disk-space or unpacking errors --- investigate node storage and
    container-runtime health.

These messages are clues, not absolute proof. Interpret them in the
context of the registry and runtime.

### Step 3: Confirm the configured image

For the Pod:

``` bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{range .spec.containers[*]}{.name}{" : "}{.image}{"\n"}{end}'
```

If the Pod belongs to a Deployment, inspect the Deployment template too:

``` bash
kubectl get deployment <deployment-name> -n <namespace> -o yaml
```

Verify the registry hostname, repository path, tag or digest, and
container name. Also check init-container images if the failure is
associated with an init container.

### Step 4: Check image pull Secret references safely

Inspect the Pod's configured pull Secret names:

``` bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.spec.imagePullSecrets[*].name}'
```

If the Pod uses a ServiceAccount, inspect its name and configured image
pull Secret references:

``` bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.spec.serviceAccountName}'
kubectl get serviceaccount <service-account-name> -n <namespace> -o yaml
```

Confirm that the referenced Secret exists in the **same namespace** as
the Pod and contains valid credentials for the correct registry. Do not
print, paste, or commit decoded Secret credentials to logs, tickets, or
source control.

``` bash
kubectl get secret <secret-name> -n <namespace>
```

This command confirms that the Secret exists; it does not prove that its
credentials are valid. Verify access through your approved
secret-management and registry-authentication process.

### Step 5: Investigate registry and node connectivity when indicated

If the event points to a DNS, timeout, TLS, connection, rate-limit, or
node-side problem:

-   Confirm the registry hostname and endpoint are correct.
-   Check whether the registry is available and whether the affected
    node can reach it.
-   Review the relevant proxy, firewall, DNS, TLS trust, and registry
    access configuration.
-   Check node conditions and container-runtime logs using your
    cluster's approved operational access.
-   If rate-limited, review registry limits and authentication options;
    avoid repeatedly forcing image pulls.

A successful pull from a developer's laptop does **not** prove the
Kubernetes node can pull the image. The node/runtime's network path and
credentials may differ.

## 5. Root-cause and resolution guide

  ---------------------------------------------------------------------------
  Evidence                    Likely cause to         Appropriate next action
                              investigate             
  --------------------------- ----------------------- -----------------------
  `manifest unknown`, tag not Tag or digest is        Confirm the published
  found                       missing or incorrect    image reference and
                                                      update the workload to
                                                      a valid tag or digest

  Repository not found,       Registry or repository  Verify the full
  incorrect repository path   name is wrong, or       registry/repository
                              access is restricted    path and permissions

  `unauthorized`,             Missing, invalid, or    Correct the registry
  `authentication required`   expired credentials     credentials and pull
                                                      Secret reference

  `pull access denied`,       Missing repository-pull Confirm the identity
  permission denied           permission, or          has permission to pull
                              authentication issue    that repository

  `no such host`, timeout,    DNS or network path     Check registry health
  connection refused          problem, or registry    and connectivity from
                              unavailable             the affected node

  TLS or certificate error    Certificate trust,      Correct the registry
                              hostname, or TLS        endpoint or certificate
                              configuration problem   trust configuration

  Rate-limit message          Registry pull limit     Follow registry
                              reached                 guidance; review
                                                      authentication and pull
                                                      frequency

  Disk-space or image         Node storage or         Inspect node disk
  extraction error            container-runtime       pressure and runtime
                              problem                 diagnostics
  ---------------------------------------------------------------------------

Do not treat the table as an automatic one-to-one mapping. If the
evidence is ambiguous, gather more information and report the root cause
as **unconfirmed** until supported.

## 6. Recommended resolution

Apply only the correction supported by the investigation:

-   **Wrong image reference:** correct the registry, repository, tag, or
    digest in the workload manifest.
-   **Missing image:** publish the intended image or point the workload
    to an image that exists and is accessible.
-   **Authentication or authorization:** repair the registry
    credentials, Secret reference, namespace, ServiceAccount
    configuration, or registry permissions.
-   **Connectivity or TLS:** repair the relevant network, DNS, proxy,
    firewall, endpoint, or certificate configuration.
-   **Rate limiting:** address registry limits and authentication; avoid
    unnecessary repeated pull attempts.
-   **Node/runtime issue:** resolve the confirmed node storage or
    container-runtime issue using the cluster's operational procedures.

For a Deployment, updating its Pod template (for example, correcting the
image in the manifest and applying it) normally triggers a rollout
automatically. Check rollout progress:

``` bash
kubectl rollout status deployment/<deployment-name> -n <namespace>
```

Do **not** run `kubectl rollout restart` as a substitute for correcting
an invalid image, missing credentials, or connectivity problem.
Restarting alone does not fix those causes.

## 7. Verification

After applying the correction:

``` bash
kubectl get pods -n <namespace> -w
kubectl describe pod <pod-name> -n <namespace>
```

For a Deployment:

``` bash
kubectl rollout status deployment/<deployment-name> -n <namespace>
kubectl get deployment <deployment-name> -n <namespace>
```

Confirm that:

-   The affected container no longer reports `ErrImagePull` or
    `ImagePullBackOff`.
-   The image pulls successfully and the container starts.
-   The Pod becomes `Ready` when the application is expected to be
    ready.
-   The Deployment reaches its expected available replica count, if
    applicable.
-   New events do not show continuing image-pull failures.

`Running` alone is not always sufficient; check readiness and the
workload's expected replica count as well.

## 8. What to avoid

-   Do not assume `ImagePullBackOff` itself explains the root cause.
-   Do not rely on `kubectl logs` as the first diagnostic step: the
    application container may never have started, so it may have no
    application logs. Start with `kubectl describe pod` and its events.
-   Do not expose or decode registry credentials in shared logs,
    tickets, or source control.
-   Do not repeatedly delete Pods or restart Deployments before
    correcting the underlying cause.
-   Do not change `imagePullPolicy` blindly. It controls when the
    runtime attempts a pull; it does not repair a wrong image reference,
    invalid credentials, or broken network access.
-   Do not assume that a successful image pull from a laptop proves the
    cluster node has the same access.
-   Do not claim a root cause is confirmed unless the collected evidence
    supports it.

## 9. RCA knowledge record for KubeTroubleshoot AI

For each ImagePullBackOff incident used in the project's knowledge base
or test set, record:

-   **Scenario ID:** unique identifier for the test case.
-   **Symptoms:** Pod/container state and relevant event reasons.
-   **Observed evidence:** exact event message, image reference, pull
    Secret references (names only), node condition, and relevant logs or
    metrics.
-   **Known root cause:** the deliberately introduced or independently
    verified cause.
-   **Evidence supporting the cause:** the specific observation that
    distinguishes it from alternative causes.
-   **Recommended investigation:** read-only commands and checks.
-   **Corrective action:** the smallest change appropriate to the
    confirmed cause.
-   **Verification criteria:** observable conditions that prove
    recovery.
-   **Source and provenance:** source URL, retrieval date, and whether
    the scenario was reproduced in the local cluster.

Keep the **general troubleshooting knowledge** separate from
**individual test-case evidence**. For example, the runbook describes
possible causes, while a test record captures the exact event message
and known cause from one controlled failure.

## 10. References

-   Kubernetes documentation --- [Images and image pull
    policy](https://kubernetes.io/docs/concepts/containers/images/)
-   Kubernetes documentation --- [Debugging
    applications](https://kubernetes.io/docs/tasks/debug/debug-application/)
-   Kubernetes documentation --- [Debugging running
    Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/)
-   Kubernetes documentation --- [Resource management for Pods and
    containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

Use the official Kubernetes documentation as the primary reference.
Third-party articles can provide examples, but verify commands and
technical claims against the Kubernetes documentation and your cluster's
actual evidence.
