"""Ingestion: normalize -> deduplicate -> chunk. Pure functions, no I/O."""
import re
import unicodedata

from app.rag.store import Chunk
from app.schemas.library import Resource, ResourceContent

CHUNK_CHARS = 700
CHUNK_OVERLAP = 120


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def dedup_key(title: str, authors: list[str]) -> str:
    """Same work = same normalized title + first author (catches re-imported catalog records)."""
    t = re.sub(r"[^a-z0-9]+", " ", normalize_text(title).lower()).strip()
    a = re.sub(r"[^a-z]+", "", (authors[0] if authors else "").lower())
    return f"{t}|{a}"


def normalize_resource(r: Resource) -> Resource:
    return r.model_copy(update={
        "title": normalize_text(r.title),
        "description": normalize_text(r.description),
        "authors": [normalize_text(a) for a in r.authors],
        "topics": sorted({normalize_text(t).lower() for t in r.topics}),
    })


def _base_metadata(r: Resource) -> dict:
    return {
        "type": r.type, "level": r.level, "authors": r.authors, "topics": r.topics,
        "resource_access_level": r.access_level, "updated_at": r.updated_at.isoformat(),
    }


def metadata_chunk(r: Resource) -> Chunk:
    text = (f"{r.title}. By {', '.join(r.authors)}. {r.level.capitalize()} {r.type.replace('_', ' ')}. "
            f"Topics: {', '.join(r.topics)}. {r.description}")
    # Catalog metadata is visible to everyone, so the metadata chunk is public
    return Chunk(chunk_id=f"{r.resource_id}#meta", resource_id=r.resource_id, title=r.title,
                 source_type="catalog", access_level="public", text=text, metadata=_base_metadata(r))


def split_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[tuple[str, str]]:
    """Split on markdown sections, then window long sections. Returns (section, text) pairs."""
    sections: list[tuple[str, str]] = []
    current, buf = "", []
    for line in text.splitlines():
        if line.startswith("#"):
            if buf:
                sections.append((current, " ".join(buf)))
            current, buf = line.lstrip("# ").strip(), []
        elif line.strip():
            buf.append(line.strip())
    if buf:
        sections.append((current, " ".join(buf)))

    out = []
    for section, body in sections:
        body = normalize_text(body)
        start = 0
        while start < len(body):
            end = min(len(body), start + size)
            if end < len(body):  # prefer to break on a sentence boundary
                cut = body.rfind(". ", start + size // 2, end)
                end = cut + 1 if cut != -1 else end
            out.append((section, body[start:end].strip()))
            if end >= len(body):
                break
            start = max(end - overlap, start + 1)
    return out


def content_chunks(r: Resource, content: ResourceContent) -> list[Chunk]:
    chunks = []
    for i, (section, text) in enumerate(split_text(content.text)):
        chunks.append(Chunk(
            chunk_id=f"{r.resource_id}#c{i}", resource_id=r.resource_id, title=r.title,
            source_type="document", access_level=content.access_level,
            # Title and section prepended so the passage embeds with its context
            text=f"{r.title} | {section}: {text}" if section else f"{r.title}: {text}",
            metadata={**_base_metadata(r), "section": section},
        ))
    return chunks
