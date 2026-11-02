
import math

from ai.metrics.prometheus_client import PrometheusClient


class KubernetesMetricsCollector:

    def __init__(self):
        self.prometheus = PrometheusClient()

    def get_pod_metrics(self, pod_name, namespace="default"):
        """
        Collect CPU, memory and restart metrics
        for a specific Kubernetes Pod.

        CPU usage is returned in cores.
        Memory usage is returned in bytes.
        Restart count is returned as a numeric value.

        Returns None for metrics that are unavailable
        or contain invalid values.
        """

        # Select the pod-level cgroup series.
        # In the observed Prometheus data, these series
        # have no image label, unlike the pause container.
        cpu_query = f"""
        sum(
            rate(container_cpu_usage_seconds_total{{
                namespace="{namespace}",
                pod="{pod_name}",
                image!~".+"
            }}[5m])
        )
        """

        memory_query = f"""
        sum(
            container_memory_working_set_bytes{{
                namespace="{namespace}",
                pod="{pod_name}",
                image!~".+"
            }}
        )
        """

        restart_query = f"""
        sum(
            kube_pod_container_status_restarts_total{{
                namespace="{namespace}",
                pod="{pod_name}"
            }}
        )
        """

        cpu = self._get_value(cpu_query)
        memory = self._get_value(memory_query)
        restarts = self._get_value(restart_query)

        return {
            "pod": pod_name,
            "namespace": namespace,
            "cpu_usage": cpu,
            "memory_usage": memory,
            "restart_count": restarts
        }

    def _get_value(self, query):
        """
        Execute a Prometheus query and safely extract
        its numeric value.

        Returns None when the query has no usable result.
        """

        results = self.prometheus.query(query)

        if not results:
            return None

        value = results[0].get("value")

        if not value or len(value) < 2:
            return None

        try:
            numeric_value = float(value[1])

            if not math.isfinite(numeric_value):
                return None

            return numeric_value

        except (TypeError, ValueError):
            return None
