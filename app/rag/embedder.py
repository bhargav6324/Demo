"""Text embedders. All return L2-normalized float32 vectors so inner product == cosine."""
import hashlib
import logging
import re
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger("smartlibrary.rag")


class Embedder(ABC):
    name: str
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder(Embedder):
    """Loads the model on first use (keeps startup and imports fast). If the
    model cannot be loaded (offline, missing package) it falls back to
    HashingEmbedder and says so in `name`, which /health reports."""

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None
        self._fallback: Embedder | None = None

    def _load(self) -> None:
        if self._model is not None or self._fallback is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device="cpu")
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not load embedding model %s (%s); falling back to HashingEmbedder",
                           self._model_name, e)
            self._fallback = HashingEmbedder()

    @property
    def name(self) -> str:
        if self._fallback:
            return f"{self._fallback.name} (fallback: {self._model_name} unavailable)"
        return self._model_name

    @property
    def dim(self) -> int:
        self._load()
        if self._fallback:
            return self._fallback.dim
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        return get_dim()

    def embed(self, texts: list[str]) -> np.ndarray:
        self._load()
        if self._fallback:
            return self._fallback.embed(texts)
        vecs = self._model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype="float32")


class HashingEmbedder(Embedder):
    """Deterministic, dependency-free bag-of-words hashing embedder.
    Used in tests and as a fallback when the model cannot be loaded."""

    def __init__(self, dim: int = 512):
        self.name = f"hashing-{dim}"
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, text in enumerate(texts):
            words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", text.lower())]
            for tok in words + [a + "_" + b for a, b in zip(words, words[1:])]:
                h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
                out[i, h % self.dim] += 1.0 if h & 1 << 31 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def build_embedder(model_name: str) -> Embedder:
    if model_name.startswith("hashing"):
        return HashingEmbedder()
    return SentenceTransformerEmbedder(model_name)
