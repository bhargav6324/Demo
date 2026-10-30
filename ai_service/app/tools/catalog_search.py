"""Keyword catalog search on top of the backend's literal-substring filter.

GET /resources?query= matches one literal substring and orders by
updated_at, so a natural-language query ("beginner books on machine
learning") would usually match nothing. We query the full phrase plus each
significant keyword in parallel, merge by resource_id, and rank locally by
where keywords appear. Every result is still a backend catalog record."""
import asyncio
import re

from app.adapters.base import LibraryToolAdapter
from app.auth.context import UserContext

MAX_KEYWORDS = 4
PER_CALL_LIMIT = 100  # backend maximum

_STOPWORDS = {
    "a", "an", "the", "on", "of", "for", "to", "in", "and", "or", "about", "with", "by",
    "book", "books", "find", "me", "some", "any", "is", "are", "i", "my", "show", "please",
    "resource", "resources", "available", "good", "best", "learn", "learning", "want", "need",
}


def keywords(query: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9+#.-]*", query.lower()) if w not in _STOPWORDS and len(w) > 1]
    # Light stemming so "papers" also matches "paper" as a substring
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]
    seen: list[str] = []
    for w in sorted(words, key=len, reverse=True):  # longer words are more specific
        if w not in seen:
            seen.append(w)
    return seen[:MAX_KEYWORDS]


def _score(item, phrase: str, kws: list[str]) -> tuple[float, int, bool]:
    """Returns (rank score, number of keywords matched, whole phrase matched)."""
    title = item.title.lower()
    topics = " ".join(item.topics).lower()
    authors = " ".join(item.authors).lower()
    desc = item.description.lower()
    score, matched = 0.0, 0
    phrase_hit = bool(phrase) and phrase in f"{item.resource_id.lower()} {title} {topics} {desc} {authors}"
    if phrase_hit:
        score += 5
    for kw in kws:
        hit = False
        if kw in title:
            score, hit = score + 3, True
        if kw in topics or kw in authors:
            score, hit = score + 2, True
        if kw in desc:
            score, hit = score + 1, True
        matched += hit
    return score, matched, phrase_hit


WAITLIST_CONCURRENCY = 10


async def longest_waitlists(adapter: LibraryToolAdapter, user: UserContext | None, top: int = 5) -> list[dict]:
    """Rank titles by live waitlist_count. The analytics summary has no waitlist
    data, so (per the backend team) page the catalog and read each availability."""
    resources, offset = [], 0
    while True:
        page = await adapter.search_resources(user, "", limit=PER_CALL_LIMIT, offset=offset)
        resources += page.items
        offset += len(page.items)
        if not page.items or offset >= page.total:
            break

    gate = asyncio.Semaphore(WAITLIST_CONCURRENCY)  # don't flood the backend with 60+ parallel calls

    async def availability(r):
        async with gate:
            return r, await adapter.get_availability(user, r.resource_id)

    rows = await asyncio.gather(*(availability(r) for r in resources))
    waiting = sorted((row for row in rows if row[1].waitlist_count > 0),
                     key=lambda row: (-row[1].waitlist_count, row[0].resource_id))
    return [{"resource_id": r.resource_id, "title": r.title, "waitlist_count": a.waitlist_count,
             "available_copies": a.available_copies, "total_copies": a.total_copies}
            for r, a in waiting[:top]]


async def search_catalog(adapter: LibraryToolAdapter, user: UserContext | None, query: str, *,
                         limit: int = 5, type: str | None = None, level: str | None = None) -> dict:
    result = await _search(adapter, user, query, limit=limit, type=type, level=level)
    if result["items"] or not (type or level):
        return result
    # A guessed filter (e.g. type="book" for what is really a journal) must not hide a real
    # title: retry without filters and say so, so the answer can explain the mismatch.
    relaxed = await _search(adapter, user, query, limit=limit)
    if relaxed["items"]:
        relaxed["filters_relaxed"] = {k: v for k, v in (("type", type), ("level", level)) if v}
        relaxed["note"] = "No matches with the requested filters; these results ignore them."
    return relaxed if relaxed["items"] else result


async def _search(adapter: LibraryToolAdapter, user: UserContext | None, query: str, *,
                  limit: int, type: str | None = None, level: str | None = None) -> dict:
    phrase = query.strip().lower()
    kws = keywords(query)
    terms = list(dict.fromkeys([phrase, *kws]))  # phrase first, de-duplicated
    pages = await asyncio.gather(*(
        adapter.search_resources(user, t, limit=PER_CALL_LIMIT, type=type, level=level) for t in terms
    ))

    merged = {r.resource_id: r for page in pages for r in page.items}
    needed = max(1, round(len(kws) * 0.6))  # most keywords must match, not just one common word
    ranked = []
    for r in merged.values():
        score, matched, phrase_hit = _score(r, phrase, kws)
        if phrase_hit or matched >= needed:
            ranked.append((score, r))
    ranked.sort(key=lambda s: (-s[0], s[1].resource_id))
    return {"items": [r for _, r in ranked[:limit]], "total": len(ranked)}
