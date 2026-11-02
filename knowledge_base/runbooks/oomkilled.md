# OOMKilled Troubleshooting Runbook

## Problem

A container is terminated because it exceeded its memory limit.

## Symptoms

The container state may show:

OOMKilled

The Pod may restart repeatedly.

## Common Root Causes

1. Application memory leak
2. Memory limit is too low
3. Large workload
4. Unexpected traffic
5. Inefficient application processing

## Investigation

Check Pod details:

kubectl describe pod <pod-name>

Check container state:

kubectl get pod <pod-name> -o yaml

Check resource configuration:

kubectl get deployment <deployment-name> -o yaml

Check memory usage using monitoring tools.

## Recommended Resolution

Determine whether the application has abnormal memory consumption.

Increase the memory limit if the workload legitimately requires more memory.

Investigate possible memory leaks.

Optimize the application if memory consumption is unexpectedly high.

## Verification

Monitor the Pod after the change.

The Pod should remain Running without repeated OOMKilled events.