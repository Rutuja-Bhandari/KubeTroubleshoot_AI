from ai.anomaly.anomaly_detector import (
    KubernetesAnomalyDetector
)

from ai.metrics.metrics_collector import (
    KubernetesMetricsCollector
)


class KubernetesAnomalyService:

    def __init__(self):
        self.metrics_collector = (
            KubernetesMetricsCollector()
        )

        self.detector = (
            KubernetesAnomalyDetector()
        )

        self.trained = False

    def train(self, historical_data):
        """
        Train the anomaly detection model
        using historical Kubernetes metrics.
        """

        self.detector.train(
            historical_data
        )

        self.trained = True

    def analyze_pod(
        self,
        pod_name,
        namespace="default"
    ):
        """
        Analyze current Kubernetes metrics
        for a specific Pod.

        If the container has not started or
        there are no meaningful runtime metrics,
        ML anomaly detection is skipped.
        """

        # ---------------------------------
        # STEP 1: Check if model is trained
        # ---------------------------------

        if not self.trained:
            raise RuntimeError(
                "Anomaly detector has not been trained."
            )

        # ---------------------------------
        # STEP 2: Collect Prometheus metrics
        # ---------------------------------

        metrics = self.metrics_collector.get_pod_metrics(
            pod_name,
            namespace
        )

        # ---------------------------------
        # STEP 3: Check whether runtime
        # metrics are available
        # ---------------------------------

        if (
            metrics["cpu_usage"] == 0
            and metrics["memory_usage"] == 0
            and metrics["restart_count"] == 0
        ):
            return {
                "status": "NOT_AVAILABLE",
                "reason": (
                    "Container has not started or "
                    "has no runtime metrics."
                ),
                "metrics": metrics,
                "anomaly": None
            }

        # ---------------------------------
        # STEP 4: Prepare ML features
        # ---------------------------------

        features = [
            metrics["restart_count"],
            metrics["cpu_usage"],
            metrics["memory_usage"]
        ]

        # ---------------------------------
        # STEP 5: Run anomaly detection
        # ---------------------------------

        anomaly = self.detector.predict(
            features
        )

        # ---------------------------------
        # STEP 6: Return anomaly result
        # ---------------------------------

        return {
            "status": "AVAILABLE",
            "metrics": metrics,
            "anomaly": anomaly
        }

