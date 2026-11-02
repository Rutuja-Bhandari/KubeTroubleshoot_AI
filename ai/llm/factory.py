import os

from ai.llm.ollama_provider import (
    OllamaProvider
)


def get_llm():

    provider = os.getenv(
        "LLM_PROVIDER",
        "ollama"
    )

    if provider == "ollama":

        model = os.getenv(
            "OLLAMA_MODEL",
            "llama3.1:8b"
        )

        return OllamaProvider(
            model=model
        )

    raise ValueError(
        f"Unsupported LLM provider: {provider}"
    )