# High CPU Troubleshooting Runbook

## Problem

A Kubernetes container or Pod is consuming unusually high CPU.

## Symptoms

CPU utilization remains significantly above normal.

## Common Root Causes

1. CPU-intensive application operation
2. Infinite loop
3. Traffic spike
4. Inefficient code
5. Incorrect resource configuration
6. Insufficient CPU allocation

## Investigation

Check Pod resource usage:

kubectl top pods

Check the Deployment:

kubectl get deployment <deployment-name> -o yaml

Review application logs.

Check recent deployment changes.

Check request traffic and application behavior.

## Recommended Resolution

Determine whether the CPU increase is expected.

If required, increase CPU resources.

Scale the application horizontally if traffic has increased.

Investigate application code for unexpected CPU-intensive operations.

## Verification

Monitor CPU usage after the change.

CPU utilization should return to the expected operating range.