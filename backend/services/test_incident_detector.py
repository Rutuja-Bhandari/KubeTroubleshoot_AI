from backend.services.incident_detector import (
    UnifiedIncidentDetector
)


def main():

    detector = UnifiedIncidentDetector()

    # -----------------------------------------
    # Scenario 1: Healthy
    # -----------------------------------------

    healthy_result = detector.evaluate(
        health_result={
            "status": "HEALTHY"
        },
        anomaly_result={
            "anomaly": {
                "status": "NORMAL",
                "anomaly_score": 0.12
            }
        }
    )

    print("\nHEALTHY SCENARIO")
    print(healthy_result)

    # -----------------------------------------
    # Scenario 2: Kubernetes failure
    # -----------------------------------------

    failure_result = detector.evaluate(
        health_result={
            "status": "UNHEALTHY"
        },
        anomaly_result={
            "anomaly": {
                "status": "NORMAL",
                "anomaly_score": 0.05
            }
        }
    )

    print("\nKUBERNETES FAILURE")
    print(failure_result)

    # -----------------------------------------
    # Scenario 3: ML anomaly
    # -----------------------------------------

    anomaly_result = detector.evaluate(
        health_result={
            "status": "HEALTHY"
        },
        anomaly_result={
            "anomaly": {
                "status": "ANOMALOUS",
                "anomaly_score": -0.32
            }
        }
    )

    print("\nML ANOMALY")
    print(anomaly_result)

    # -----------------------------------------
    # Scenario 4: Both
    # -----------------------------------------

    both_result = detector.evaluate(
        health_result={
            "status": "UNHEALTHY"
        },
        anomaly_result={
            "anomaly": {
                "status": "ANOMALOUS",
                "anomaly_score": -0.45
            }
        }
    )

    print("\nBOTH")
    print(both_result)


if __name__ == "__main__":
    main()