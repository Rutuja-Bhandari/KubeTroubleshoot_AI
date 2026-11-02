import numpy as np
from sklearn.ensemble import IsolationForest


class KubernetesAnomalyDetector:
    def __init__(self):
        self.model = IsolationForest(
            contamination=0.1,
            random_state=42
        )

        self.trained = False

    def train(self, historical_data):
        """
        Train the anomaly detector using
        historical normal Kubernetes behavior.
        """

        print("historical_ data :", historical_data)

        data = np.array(historical_data)

        self.model.fit(data)

        self.trained = True

    def predict(self, current_data):
        """
        Detect whether current Kubernetes
        metrics are normal or anomalous.
        """

        if not self.trained:
            raise RuntimeError(
                "Anomaly detector has not been trained."
            )

        data = np.array([current_data])

        prediction = self.model.predict(data)

        score = self.model.decision_function(data)

        if prediction[0] == -1:
            status = "ANOMALOUS"
        else:
            status = "NORMAL"

        return {
            "status": status,
            "anomaly_score": float(score[0])
        }