"""Local embedding backend."""


class EmbeddingClient:
    """Wraps a sentence-transformers model (see config.EMBEDDING_MODEL_NAME)."""

    def __init__(self, model_name: str | None = None) -> None:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Must batch internally, not call the model
        one text at a time.
        """
        raise NotImplementedError
