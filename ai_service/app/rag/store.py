"""FAISS vector store with a JSON metadata sidecar. Chunks are grouped by
resource so a changed resource can be replaced atomically on refresh."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import faiss
import numpy as np


@dataclass
class Chunk:
    chunk_id: str
    resource_id: str
    title: str
    source_type: str     # "catalog" (metadata) | "document" (authorized content)
    access_level: str    # gate for showing this chunk's text
    text: str
    metadata: dict = field(default_factory=dict)


class FaissStore:
    def __init__(self, dim: int):
        self.dim = dim
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
        self._chunks: dict[int, Chunk] = {}
        self._by_resource: dict[str, list[int]] = {}
        self._next_id = 0

    def __len__(self) -> int:
        return self._index.ntotal

    def resource_ids(self) -> set[str]:
        return set(self._by_resource)

    def upsert_resource(self, resource_id: str, chunks: list[Chunk], vectors: np.ndarray) -> None:
        self.remove_resource(resource_id)
        ids = np.arange(self._next_id, self._next_id + len(chunks), dtype="int64")
        self._next_id += len(chunks)
        self._index.add_with_ids(np.ascontiguousarray(vectors, dtype="float32"), ids)
        for i, c in zip(ids.tolist(), chunks):
            self._chunks[i] = c
        self._by_resource[resource_id] = ids.tolist()

    def remove_resource(self, resource_id: str) -> None:
        ids = self._by_resource.pop(resource_id, None)
        if ids:
            self._index.remove_ids(np.array(ids, dtype="int64"))
            for i in ids:
                self._chunks.pop(i, None)

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[float, Chunk]]:
        if len(self) == 0:
            return []
        scores, ids = self._index.search(query_vec.reshape(1, -1).astype("float32"), min(k, len(self)))
        return [(float(s), self._chunks[int(i)]) for s, i in zip(scores[0], ids[0]) if i != -1]

    # ---- persistence ----

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / "index.faiss"))
        (directory / "chunks.json").write_text(json.dumps({
            "next_id": self._next_id,
            "chunks": {str(i): asdict(c) for i, c in self._chunks.items()},
            "by_resource": self._by_resource,
        }), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "FaissStore":
        index = faiss.read_index(str(directory / "index.faiss"))
        meta = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        store = cls(index.d)
        store._index = index
        store._next_id = meta["next_id"]
        store._chunks = {int(i): Chunk(**c) for i, c in meta["chunks"].items()}
        store._by_resource = meta["by_resource"]
        return store
