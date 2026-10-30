"""Builds the response's resources and citations from tool evidence only.

Anything the model mentions that no tool returned is dropped. Availability
numbers come exclusively from availability-bearing tool results."""
from dataclasses import dataclass, field

from app.rag.ingest import dedup_key
from app.schemas.chat import ChatResource, Citation
from app.tools.executor import ToolResult


@dataclass
class Evidence:
    resources: dict[str, dict] = field(default_factory=dict)       # resource_id -> {title, type}
    availability: dict[str, int] = field(default_factory=dict)     # resource_id -> available_copies
    reasons: dict[str, str] = field(default_factory=dict)          # resource_id -> engine-provided reason
    documents: list[Citation] = field(default_factory=list)        # retrieved content / chunks
    order: list[str] = field(default_factory=list)                 # resource_ids in retrieval order

    def add(self, result: ToolResult) -> None:
        if result.status not in ("success", "confirmation_required") or result.data is None:
            return
        self._walk(result.data, result.tool)
        if result.tool == "get_resource_content":
            d = result.data
            self._cite(Citation(resource_id=d["resource_id"], source_type="document",
                                source_id=d["resource_id"], title=d["title"]))

    def _walk(self, value, tool: str) -> None:
        if isinstance(value, list):
            for v in value:
                self._walk(v, tool)
            return
        if not isinstance(value, dict):
            return
        rid = value.get("resource_id")
        if isinstance(rid, str):
            title = value.get("title") or value.get("resource_title")
            if title:
                if rid not in self.resources:
                    self.order.append(rid)
                self.resources.setdefault(rid, {"title": title, "type": value.get("type"),
                                                "authors": value.get("authors") or []})
            # Only availability records (with locations) or recommender output (which
            # verified availability through the tool) count as live availability
            avail = value.get("available_copies")
            if isinstance(avail, int) and ("locations" in value or tool == "generate_recommendations"):
                self.availability[rid] = avail
            if tool == "generate_recommendations" and value.get("reason"):
                self.reasons[rid] = value["reason"]
            if value.get("chunk_id") and title:
                self._cite(Citation(resource_id=rid, source_type=value.get("source_type", "chunk"),
                                    source_id=value["chunk_id"], title=title))
        for v in value.values():
            if isinstance(v, (dict, list)):
                self._walk(v, tool)

    def _cite(self, c: Citation) -> None:
        if all((x.source_type, x.source_id) != (c.source_type, c.source_id) for x in self.documents):
            self.documents.append(c)


def build_resources(model_resources: list, evidence: Evidence, fallback: bool) -> list[ChatResource]:
    out: list[ChatResource] = []
    seen: set[str] = set()  # resource_ids and dedup keys (duplicate catalog records collapse)

    def add(rid: str, reason: str | None) -> None:
        info = evidence.resources[rid]
        key = dedup_key(info["title"], info["authors"])
        if rid in seen or key in seen:
            return
        seen.update({rid, key})
        out.append(_resource(rid, evidence, reason))

    for item in model_resources or []:
        rid = item.get("resource_id") if isinstance(item, dict) else None
        if rid in evidence.resources:  # unverified IDs are silently dropped
            add(rid, item.get("reason"))
    if not out and fallback:
        for rid in evidence.order:
            if len(out) >= 5:
                break
            add(rid, None)
    return out


def _resource(rid: str, evidence: Evidence, model_reason: str | None) -> ChatResource:
    reason = evidence.reasons.get(rid) or (model_reason or "").strip() or "Verified match in the library catalog."
    return ChatResource(
        resource_id=rid,
        title=evidence.resources[rid]["title"],
        reason=reason,
        available_copies=evidence.availability.get(rid),
    )


def build_citations(resources: list[ChatResource], evidence: Evidence) -> list[Citation]:
    ids = {r.resource_id for r in resources}
    cites = [Citation(resource_id=r.resource_id, source_type="catalog", source_id=r.resource_id, title=r.title)
             for r in resources]
    # Document/chunk sources: cite those backing the returned resources (or all, for pure summaries)
    cites += [d for d in evidence.documents if not ids or d.resource_id in ids]
    return cites
