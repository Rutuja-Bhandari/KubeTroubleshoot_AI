from ai.anomaly.kubernetes_anomaly import (
    KubernetesAnomalyService
)


def main():

    service = KubernetesAnomalyService()

    historical_data = [
        [0, 0.01, 100000000],
        [0, 0.02, 110000000],
        [1, 0.03, 120000000],
        [0, 0.02, 105000000],
        [1, 0.04, 115000000],
        [0, 0.03, 108000000],
        [1, 0.02, 112000000],
        [0, 0.01, 102000000],
        [0, 0.03, 118000000],
        [1, 0.04, 125000000]
    ]

    service.train(
        historical_data
    )

    result = service.analyze_pod(
        pod_name="kube-demo-server-6b5786d66d-52hk5",
        namespace="default"
    )

    print("\n==============================")
    print("KUBERNETES METRICS")
    print("==============================")

    print(result)


if __name__ == "__main__":
    main()