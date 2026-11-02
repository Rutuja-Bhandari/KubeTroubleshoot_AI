# Previous Kubernetes Incidents

## Incident 001

### Problem

Payment server Pods entered ImagePullBackOff.

### Root Cause

The Deployment referenced an image tag that did not exist in the container registry.

### Evidence

Kubernetes events showed:

Failed to pull image

The Deployment used an incorrect image tag.

### Resolution

The image tag was corrected and the Deployment was restarted.

### Prevention

Validate container image tags before deployment.

---

## Incident 002

### Problem

Backend Pod repeatedly entered CrashLoopBackOff.

### Root Cause

A required environment variable was missing.

### Evidence

Application logs showed that the required configuration value was not available.

### Resolution

The required environment variable was added to the Deployment configuration.

### Prevention

Validate required environment variables during deployment.

---

## Incident 003

### Problem

Application Pod was repeatedly OOMKilled.

### Root Cause

The application's memory consumption exceeded the configured container memory limit.

### Evidence

Kubernetes reported OOMKilled container termination.

### Resolution

Memory usage was investigated and the memory limit was adjusted.

### Prevention

Configure appropriate resource requests and limits and monitor memory usage.