# Root Cause Analysis Runbook: Volume Mount and Attach Failures (`VolumeMountFailures.md`)

This runbook defines the structured, evidence-based diagnostic framework for analyzing Kubernetes volume attachment, detachment, and mounting failures. It focuses on mapping storage orchestrator events directly to root causes, allowing automated troubleshooting engines like KubeTroubleshoot AI to isolate storage infra blocks accurately.

---

## 1. Taxonomic Classification & Meaning of Statuses

Volume lifecycle issues occur across separate stages governed by different Kubernetes control loops (Attach/Detach Controller vs. Kubelet Volume Manager). Distinguishing the exact phase prevents treating host-level infrastructure failures as local path errors.

### 1.1 Status and Phase Differentiation
*   **FailedAttachVolume**: The volume cannot be logically attached or linked to the worker Node where the Pod is scheduled. This operation runs asynchronously via the master control plane's Attach/Detach Controller and interacts directly with the cloud/storage provider API.
*   **FailedMountVolume**: The volume is successfully attached to the node hardware, but the local Kubelet daemon cannot format, access, or mount the filesystem path into the container's isolated namespace.
*   **ContainerStuckInContainerCreating**: A physical manifestation where the overall Pod status is caught in `ContainerCreating` or `ContainerWithheld` because the blocking volume lifecycle hook has not cleared successfully.

### 1.2 Pod Conditions & Container States
*   The Pod remains trapped in a **`ContainerCreating`** or **`Pending`** phase.
*   The top-level Pod condition `Ready` is marked `False`.
*   The condition `Initialized` may be `True`, but `ContainersReady` remains `False`.

---

## 2. Evidence-to-Cause Mapping Matrix

Primary diagnostic conclusions must be parsed from the `Events` log section using `kubectl describe pod <pod-name>`. Do not declare a confirmed root cause without an explicit message signature pattern match.

| Event Type | Reason Field | Message Signature Pattern | Inferred Root Cause |
| :--- | :--- | :--- | :--- |
| `Warning` | `FailedAttachVolume` | `Multi-Attach error for volume "..." Volume is already used by pod` | **ReadWriteOnce (RWO) Violations / Stuck Node Detachment** |
| `Warning` | `FailedMountVolume` | `MountVolume.SetUp failed for volume "..." : configmap "..." not found` | **Missing Reference ConfigMap Projection** |
| `Warning` | `FailedMountVolume` | `MountVolume.SetUp failed for volume "..." : secret "..." not found` | **Missing Reference Secret Projection** |
| `Warning` | `FailedAttachVolume` | `AttachVolume.Attach failed for volume ... : rpc error: code = NotFound desc = Volume not found` | **Underlying Physical Storage Object Deleted on Cloud Provider** |
| `Warning` | `FailedMountVolume` | `MountVolume.SetUp failed for volume ... path "..." is not a directory` | **SubPath Mount Type Mismatch (Mounting File onto Folder)** |
| `Warning` | `FailedMountVolume` | `mount failed: exit status 32 ... wrong fs type, bad option, bad superblock` | **Corrupted Filesystem or Missing Storage Utilities on Node Host** |
| `Warning` | `FailedAttachVolume` | `cloud provider error ... iops/throughput capacity exceeded` | **Cloud Infrastructure Provider API Throttling** |

---

## 3. Deep-Dive Diagnostic & Verification Vectors

### 3.1 Controller Planes vs. Node Kubelet Subsystems
*   **Attach/Detach Loop Diagnostics**: If the error logs report `FailedAttachVolume`, look closely at the storage driver. In cloud topologies (e.g., AWS EBS, Azure Disk), an enterprise disk using `ReadWriteOnce` access mode cannot cross Availability Zone (AZ) boundaries. If a Pod is scheduled on a Node in `us-east-1b`, but the existing physical volume is provisioned in `us-east-1a`, the cloud controller API will repeatedly reject the attachment request.
*   **Node-Side Path Execution**: If the error logs report `FailedMountVolume`, the cloud block store is successfully linked to the host OS instance, but the Kubelet cannot perform system tasks like `mount -t ext4` or handle permissions mappings inside the container filesystem architecture.

### 3.2 Projected Volume Subsets (Secrets, ConfigMaps, DownwardAPI)
*   **Lifecycle Blocks on Projection**: When mapping a `Secret` or a `ConfigMap` as an inline volume block, the Kubelet tracks the target namespace metadata directly. If an operator removes the target Secret, or if the Pod manifest calls out an invalid Secret identifier name, the volume engine stalls. It will block the entire container startup timeline until the configuration dependencies appear.
*   **Subpath Freezes**: If a manifest targets a tiny individual key (`subPath: configuration.yaml`) instead of mounting the entire folder directory structure, the Kubelet looks for that explicit key path. If the key file is deleted or absent from the source mapping data configuration array, the setup hook errors out instantly.

### 3.3 Access Modes and Stalled Node Detachments
*   **Stuck Nodes During Rollouts**: During normal rolling cluster upgrades or node infrastructure failures, a cloud provider volume can become "stuck" on a terminated or unreachable worker node instance. The master Attach/Detach controller will actively delay forcing a dirty force-detach to avoid risking hard filesystem sector corruption, causing the newly scheduled Pod to wait indefinitely for attachment.

---

## 4. Anti-Patterns & Common Automated Troubleshooting Pitfalls

*   **Anti-Pattern 1: Defaulting to `kubectl rollout restart` or `kubectl delete pod`**
    *   *Why it fails*: If a volume cannot mount because of a hard Availability Zone boundary mismatch, a missing CSI configuration layer, or a non-existent `ConfigMap`, deleting the pod will simply force the scheduler to recreate the pod in an identical, unresolvable loop. This increases cloud provider throttling risk without correcting the block.
*   **Anti-Pattern 2: Prioritizing Application Container Logs**
    *   *Why it fails*: The underlying container process is **prevented from initializing**. No container runtime context is populated by the engine. Checking application stdout or log collectors will result in null data entries. The definitive source of diagnostic truth exists inside the cluster control infrastructure events.
*   **Anti-Pattern 3: Hardcoding Clear-Text Credentials in Mount Specifications**
    *   *Why it fails*: When mounting NFS, CIFS, or SMB filesystems that require administrative authentication, secrets must be projected cleanly from an isolated `Secret` object using safe resource parameters. Credentials should never be hardcoded into the raw execution properties of the manifest definition file.

---

## 5. Cause-Specific Remediation Manual

### 5.1 Remediation: ReadWriteOnce (RWO) Multi-Attach Failures
*   **Evidence Pattern**: `Multi-Attach error for volume "pvc-xxx" Volume is already used by pod`
*   **Remediation**: Adjust deployment termination parameters to ensure the old instance is completely un-scheduled and detached from its host Node execution environment before the new container starts, or modify the storage class definitions to leverage a multi-node shared storage layout (`ReadWriteMany`).

```yaml
# Correct Remediation for Deployment Rolling Updates
spec:
  strategy:
    type: Recreate # Drops old instance completely before binding the storage reference to a new node instance
```

### 5.2 Remediation: Missing ConfigMap or Secret Projection Reference
*   **Evidence Pattern**: `MountVolume.SetUp failed for volume "config-vol" : configmap "app-settings" not found`
*   **Remediation**: Provision the missing projected file dependency configuration directly inside the designated target namespace context to unblock the Kubelet manager hook loop.

```yaml
# Create the structural missing volume block
kubectl create configmap app-settings --from-file=config.json=./config.json -n <target-namespace>
```

### 5.3 Remediation: SubPath Parameter Type Collision
*   **Evidence Pattern**: `MountVolume.SetUp failed ... path "/var/lib/kubelet/.../config.yaml" is not a directory`
*   **Remediation**: Correct the container configuration definitions block inside the Pod manifest file to ensure the layout parameters do not accidentally map a directory target block onto an item file pointer path.

```yaml
# Corrected volume mount block setup entry
volumeMounts:
  - name: shared-storage-pool
    mountPath: /app/config/config.yaml
    subPath: config.yaml # Explicitly declaring the object string key to protect file-to-file paths
```

---

## 6. Verification & Closure Criteria

An active incident involving a volume failure is officially verified as resolved only when the following infrastructure criteria evaluate successfully in sequence:

1.  **Lifecycle Advancement**: The target container context cleanly steps through `ContainerCreating` and advances into a healthy, operational `Running` state phase.
2.  **Mount Confirmation Logs**: A diagnostic evaluation of `kubectl get pvc` displays an active status indicator mapping of `Bound`.
3.  **Event Cessation**: The Kubelet storage controller component stops creating `Warning / FailedMountVolume` or `FailedAttachVolume` error indicators inside the cluster event payload logs.

---

## 7. Uncertainty Handling Protocol

*   **Incomplete Storage State Tracking**: If the event logs return a cloud provider specific error code that does not explicitly map to an access mode block or missing parameter metadata, KubeTroubleshoot AI must report the state as `UNCONFIRMED_STORAGE_PROVIDER_RESTRICTION`.
*   **Operator Troubleshooting Actions**: Output this structured verification checklist directly to the system engineer:
