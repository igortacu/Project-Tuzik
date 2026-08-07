"""Local embedding backend."""

from sentence_transformers import SentenceTransformer

from second_brain import config


class EmbeddingClient:
    """Wraps a sentence-transformers model (see config.EMBEDDING_MODEL_NAME)."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model = SentenceTransformer(model_name or config.EMBEDDING_MODEL_NAME)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts in a single batched call to the model."""
        if not texts:
            return []
        vectors = self._model.encode(texts, batch_size=32, convert_to_numpy=True)
        return vectors.tolist()
