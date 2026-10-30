"""Semantic retrieval over catalog metadata and authorized document content.

Index build/refresh goes through the LibraryToolAdapter, so it works the
same against fixtures (mock) and the real backend (http). Query-time:
embed -> vector search -> access filter -> metadata filters -> group by
resource -> verify each resource still exists in the catalog."""
import asyncio
import logging
from datetime import datetime, timedelta

from app.adapters.base import LibraryToolAdapter
from app.adapters.errors import ToolError
from app.auth.access import can_access
from app.auth.context import UserContext
from app.rag.embedder import Embedder
from app.rag.ingest import content_chunks, dedup_key, metadata_chunk, normalize_resource
from app.rag.store import FaissStore

logger = logging.getLogger("smartlibrary.rag")

MAX_PASSAGES_PER_RESOURCE = 2
MAX_PAGES = 1000                       # safety bound for GET /resources paging
WINDOW_OVERLAP = timedelta(minutes=5)  # updated_since is strictly newer-than; overlap absorbs clock/edit races


class Retriever:
    def __init__(self, embedder: Embedder, adapter: LibraryToolAdapter, indexer: UserContext,
                 min_score: float = 0.3, page_limit: int = 100):
        self.embedder = embedder
        self.adapter = adapter
        self.indexer = indexer          # service identity used only for ingestion
        self.min_score = min_score
        self.page_limit = page_limit
        self.store: FaissStore | None = None  # created on first refresh (model dim known then)
        self.last_updated_at: datetime | None = None   # high-water mark for updated_since
        self.duplicates: dict[str, str] = {}           # duplicate resource_id -> canonical id
        self._indexed_at: dict[str, datetime] = {}      # resource_id -> updated_at when indexed
        self._keys: dict[str, str] = {}                 # dedup key -> canonical id
        self._lock = asyncio.Lock()
        self._ready = False

    # ------------------------------------------------------------ indexing

    async def ensure_ready(self) -> None:
        if not self._ready:
            await self.refresh()

    async def _list_changed(self, since: datetime | None) -> list:
        """Page through GET /resources (limit 100 + offset). Offset paging is not a
        frozen snapshot, so results are de-duplicated by resource_id."""
        by_id, offset = {}, 0
        for _ in range(MAX_PAGES):
            page = await self.adapter.search_resources(self.indexer, "", limit=self.page_limit,
                                                       offset=offset, updated_since=since)
            for r in page.items:
                by_id[r.resource_id] = r
            offset += len(page.items)
            if not page.items or offset >= page.total:
                break
        return list(by_id.values())

    async def refresh(self, full: bool = False) -> dict:
        """Index resources changed since the last refresh (all of them the first time).
        The time window overlaps the previous one; unchanged records are skipped, and
        the watermark only advances after every page was processed."""
        async with self._lock:
            if self.store is None:
                self.store = FaissStore(await asyncio.to_thread(lambda: self.embedder.dim))
            since = None
            if not full and self._ready and self.last_updated_at:
                since = self.last_updated_at - WINDOW_OVERLAP
            changed = await self._list_changed(since)
            stats = {"seen": len(changed), "indexed": 0, "unchanged": 0, "duplicates": 0, "documents": 0}
            watermark = self.last_updated_at

            for raw in changed:
                if watermark is None or raw.updated_at > watermark:
                    watermark = raw.updated_at
                if not full and self._indexed_at.get(raw.resource_id) == raw.updated_at:
                    stats["unchanged"] += 1  # seen again only because of the window overlap
                    continue
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
                self._indexed_at[r.resource_id] = raw.updated_at
                stats["indexed"] += 1

            self.last_updated_at = watermark  # only after all pages succeeded
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
                    "source_type": "document", "section": chunk.metadata.get("section", ""),
                    "source": chunk.metadata.get("source", ""), "text": chunk.text,
                })

        ranked = sorted(grouped.items(), key=lambda kv: -kv[1]["score"])[:limit]
        verified = await asyncio.gather(*(self._verify(user, rid) for rid, _ in ranked))

        items = []
        for (rid, g), resource in zip(ranked, verified):
            if resource is None:  # deleted from catalog since indexing
                continue
            # access_level can change after indexing: re-check against the live record
            passages = g["passages"] if can_access(role, resource.access_level) else []
            items.append({
                "resource_id": rid,
                "title": resource.title,             # title from the live catalog, not the index
                "type": resource.type,
                "level": resource.level,
                "authors": resource.authors,
                "topics": resource.topics,
                "description": resource.description,
                "relevance": round(g["score"], 3),
                "passages": passages,
            })
        return {"query": query, "items": items, "total": len(items)}

    async def _verify(self, user, resource_id):
        try:
            return await self.adapter.get_resource(user, resource_id)
        except ToolError as e:
            if e.code == ToolError.NOT_FOUND:
                return None
            raise
