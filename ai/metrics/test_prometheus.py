from ai.metrics.prometheus_client import (
    PrometheusClient
)


def main():

    prometheus = PrometheusClient()

    results = prometheus.query(
        "up"
    )

    print("\n==============================")
    print("PROMETHEUS RESULTS")
    print("==============================")

    for result in results:
        print(result)


if __name__ == "__main__":
    main()