"""Semantic retrieval over catalog metadata and authorized document content.

Index build/refresh goes through the LibraryToolAdapter, so it works the
same against fixtures (mock) and the real backend (http). Query-time:
embed -> vector search -> access filter -> metadata filters -> group by
resource -> verify each resource still exists in the catalog."""
import asyncio
import logging
from datetime import datetime

from app.adapters.base import LibraryToolAdapter
from app.adapters.errors import ToolError
from app.auth.access import can_access
from app.auth.context import UserContext
from app.rag.embedder import Embedder
from app.rag.ingest import content_chunks, dedup_key, metadata_chunk, normalize_resource
from app.rag.store import FaissStore

logger = logging.getLogger("smartlibrary.rag")

MAX_PASSAGES_PER_RESOURCE = 2


class Retriever:
    def __init__(self, embedder: Embedder, adapter: LibraryToolAdapter, indexer: UserContext,
                 min_score: float = 0.3, page_limit: int = 500):
        self.embedder = embedder
        self.adapter = adapter
        self.indexer = indexer          # service identity used only for ingestion
        self.min_score = min_score
        self.page_limit = page_limit
        self.store: FaissStore | None = None  # created on first refresh (model dim known then)
        self.last_updated_at: datetime | None = None   # high-water mark for updated_since
        self.duplicates: dict[str, str] = {}           # duplicate resource_id -> canonical id
        self._keys: dict[str, str] = {}                 # dedup key -> canonical id
        self._lock = asyncio.Lock()
        self._ready = False

    # ------------------------------------------------------------ indexing

    async def ensure_ready(self) -> None:
        if not self._ready:
            await self.refresh()

    async def refresh(self, full: bool = False) -> dict:
        """Index resources changed since the last refresh (all of them the first time)."""
        async with self._lock:
            if self.store is None:
                self.store = FaissStore(await asyncio.to_thread(lambda: self.embedder.dim))
            since = None if full or not self._ready else self.last_updated_at
            page = await self.adapter.search_resources(self.indexer, "", limit=self.page_limit, updated_since=since)
            stats = {"seen": len(page.items), "indexed": 0, "duplicates": 0, "documents": 0}

            for raw in page.items:
                r = normalize_resource(raw)
                key = dedup_key(r.title, r.authors)
                canonical = self._keys.setdefault(key, r.resource_id)
                if canonical != r.resource_id:
                    self.duplicates[r.resource_id] = canonical
                    self.store.remove_resource(r.resource_id)
                    stats["duplicates"] += 1
                    continue

                chunks = [metadata_chunk(r)]
                try:
                    content = await self.adapter.get_resource_content(self.indexer, r.resource_id)
                    chunks += content_chunks(r, content)
                    stats["documents"] += 1
                except ToolError as e:
                    # No content / not readable by the indexer's token: index metadata only
                    if e.code not in (ToolError.NOT_FOUND, ToolError.PERMISSION_DENIED, ToolError.UNAUTHORIZED):
                        logger.warning("Content for %s not indexed: %s", r.resource_id, e.code)

                vectors = await asyncio.to_thread(self.embedder.embed, [c.text for c in chunks])
                self.store.upsert_resource(r.resource_id, chunks, vectors)
                stats["indexed"] += 1
                if self.last_updated_at is None or r.updated_at > self.last_updated_at:
                    self.last_updated_at = r.updated_at

            self._ready = True
            stats["total_chunks"] = len(self.store)
            logger.info("RAG refresh (since=%s): %s", since, stats)
            return stats

    # ------------------------------------------------------------ querying

    async def search(self, user: UserContext | None, query: str, limit: int = 5,
                     type: str | None = None, level: str | None = None) -> dict:
        await self.ensure_ready()
        qvec = (await asyncio.to_thread(self.embedder.embed, [query]))[0]
        role = user.role if user else None

        grouped: dict[str, dict] = {}
        for score, chunk in self.store.search(qvec, k=max(50, limit * 10)):
            if score < self.min_score:
                continue
            # Never surface text the caller is not entitled to, even if it is in the index
            if not can_access(role, chunk.access_level):
                continue
            if (type and chunk.metadata.get("type") != type) or (level and chunk.metadata.get("level") != level):
                continue
            g = grouped.setdefault(chunk.resource_id, {"score": score, "passages": []})
            g["score"] = max(g["score"], score)
            if chunk.source_type == "document" and len(g["passages"]) < MAX_PASSAGES_PER_RESOURCE:
                g["passages"].append({
                    "chunk_id": chunk.chunk_id, "resource_id": chunk.resource_id, "title": chunk.title,
                    "source_type": "document", "section": chunk.metadata.get("section", ""), "text": chunk.text,
                })

        ranked = sorted(grouped.items(), key=lambda kv: -kv[1]["score"])[:limit]
        verified = await asyncio.gather(*(self._verify(user, rid) for rid, _ in ranked))

        items = []
        for (rid, g), resource in zip(ranked, verified):
            if resource is None:  # deleted from catalog since indexing
                continue
            items.append({
                "resource_id": rid,
                "title": resource.title,             # title from the live catalog, not the index
                "type": resource.type,
                "level": resource.level,
                "authors": resource.authors,
                "topics": resource.topics,
                "description": resource.description,
                "relevance": round(g["score"], 3),
                "passages": g["passages"],
            })
        return {"query": query, "items": items, "total": len(items)}

    async def _verify(self, user, resource_id):
        try:
            return await self.adapter.get_resource(user, resource_id)
        except ToolError as e:
            if e.code == ToolError.NOT_FOUND:
                return None
            raise
