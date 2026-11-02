# Kubernetes Troubleshooting Guide

## Pod Troubleshooting

Start by checking the Pod status:

kubectl get pods

If the Pod is not Running, inspect the Pod:

kubectl describe pod <pod-name>

Review the Events section.

## Logs

Application logs can be retrieved using:

kubectl logs <pod-name>

For a previously terminated container:

kubectl logs <pod-name> --previous

## Deployment Troubleshooting

Check Deployment status:

kubectl get deployments

Check the Deployment configuration:

kubectl describe deployment <deployment-name>

Check whether desired replicas match available replicas.

## Service Troubleshooting

Check Services:

kubectl get services

Check Service endpoints:

kubectl get endpoints

Verify that the Service selector matches the Pod labels.

## Events

Kubernetes events provide information about scheduling, image pulling, container startup, networking and other cluster operations.

Use:

kubectl get events

For a specific Pod:

kubectl describe pod <pod-name>

## General Troubleshooting Process

1. Identify the unhealthy resource.
2. Check its current status.
3. Inspect Kubernetes events.
4. Inspect application logs.
5. Check configuration.
6. Check resource usage.
7. Review recent deployment changes.
8. Compare with known incidents.
9. Apply the least risky fix.
10. Verify that the application becomes healthy.