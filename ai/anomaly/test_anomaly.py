from ai.anomaly.anomaly_detector import (
    KubernetesAnomalyDetector
)


def main():

    historical_data = [
        [0, 100, 80],
        [0, 110, 85],
        [1, 120, 90],
        [0, 105, 82],
        [1, 115, 88],
        [0, 108, 84],
        [1, 118, 91],
        [0, 102, 79],
        [0, 112, 86],
        [1, 125, 93]
    ]

    detector = KubernetesAnomalyDetector()

    detector.train(
        historical_data
    )

    normal = detector.predict(
        [0, 110, 85]
    )

    anomalous = detector.predict(
        [20, 950, 250]
    )

    print("\nNormal behavior:")
    print(normal)

    print("\nAnomalous behavior:")
    print(anomalous)


if __name__ == "__main__":
    main()