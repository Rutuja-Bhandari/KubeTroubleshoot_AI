# ImagePullBackOff Troubleshooting Runbook

## Problem

Kubernetes cannot pull the container image required by a Pod.

## Symptoms

The Pod may show:

- ImagePullBackOff
- ErrImagePull

## Common Root Causes

1. Image name is incorrect
2. Image tag does not exist
3. Container registry is unavailable
4. Registry authentication failed
5. Image is private
6. ImagePullSecret is missing

## Investigation

Check the Pod:

kubectl get pods

Check Pod events:

kubectl describe pod <pod-name>

Look for messages such as:

Failed to pull image

Pull access denied

Manifest unknown

Check the image configured in the Deployment:

kubectl get deployment <deployment-name> -o yaml

## Recommended Resolution

Verify the image name and tag.

Verify that the image exists in the container registry.

For private registries, verify the ImagePullSecret.

Verify registry authentication.

## Verification

After fixing the image configuration:

kubectl rollout restart deployment <deployment-name>

Then:

kubectl get pods

The Pod should become Running.