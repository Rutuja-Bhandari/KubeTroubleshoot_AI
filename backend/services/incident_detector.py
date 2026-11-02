class UnifiedIncidentDetector:

    def evaluate(
        self,
        health_result,
        anomaly_result
    ):
        """
        Combine Kubernetes health status
        and ML anomaly detection.
        """

        health_status = health_result.get(
            "status",
            "UNKNOWN"
        )

        incident_detected = False
        reasons = []

        # -----------------------------------------
        # Kubernetes health
        # -----------------------------------------

        if health_status == "UNHEALTHY":
            incident_detected = True

            reasons.append(
                "Kubernetes health check detected a failure."
            )

        # -----------------------------------------
        # ML anomaly
        # -----------------------------------------

        anomaly = anomaly_result.get(
            "anomaly",
            {}
        )

        anomaly_status = anomaly.get(
            "status"
        )

        if anomaly_status == "ANOMALOUS":
            incident_detected = True

            reasons.append(
                "ML detected abnormal Kubernetes behavior."
            )

        # -----------------------------------------
        # Final decision
        # -----------------------------------------

        if incident_detected:
            status = "INCIDENT"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "incident_detected": incident_detected,
            "reasons": reasons,
            "health_status": health_status,
            "anomaly_status": anomaly_status
        }