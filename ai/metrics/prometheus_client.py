import requests


class PrometheusClient:

    def __init__(
        self,
        base_url="http://localhost:9090"
    ):
        self.base_url = base_url.rstrip("/")

    def query(self, promql):
        """
        Execute a PromQL query against Prometheus.
        """

        response = requests.get(
            f"{self.base_url}/api/v1/query",
            params={
                "query": promql
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if data["status"] != "success":
            raise RuntimeError(
                "Prometheus query failed"
            )

        return data["data"]["result"]