# CrashLoopBackOff Troubleshooting Runbook

## Problem

A Kubernetes Pod is repeatedly starting and crashing.

## Symptoms

Common symptoms include:

- Pod status shows CrashLoopBackOff
- Container restart count continuously increases
- Application starts and then exits
- Kubernetes events may show BackOff messages

## Common Root Causes

1. Application configuration error
2. Missing environment variable
3. Invalid database connection
4. Application startup failure
5. Incorrect command or arguments
6. Missing configuration file
7. Insufficient resources

## Investigation

Check Pod status:

kubectl get pods

Check Pod details:

kubectl describe pod <pod-name>

Check application logs:

kubectl logs <pod-name>

Check previous container logs:

kubectl logs <pod-name> --previous

Check Kubernetes events:

kubectl get events

## Recommended Resolution

Review the application logs first.

Check environment variables and ConfigMaps.

Verify Secrets and external dependencies.

Check whether the container command and arguments are correct.

Check whether the application is being terminated because of resource limits.

## Verification

After applying the fix:

kubectl get pods

The Pod should eventually show:

Running

The restart count should stop increasing.