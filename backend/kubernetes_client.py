from kubernetes import client, config


def load_kubernetes_config():
    """
    Load Kubernetes configuration from the local kubeconfig.
    """

    try:
        config.load_kube_config()
        print("Kubernetes configuration loaded successfully.")

    except Exception as e:
        raise RuntimeError(
            f"Failed to load Kubernetes configuration: {e}"
        )


def get_core_api():
    """
    Return Kubernetes CoreV1Api client.
    """

    load_kubernetes_config()

    return client.CoreV1Api()


def get_apps_api():
    """
    Return Kubernetes AppsV1Api client.
    """

    load_kubernetes_config()

    return client.AppsV1Api()