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


async def search_catalog(adapter: LibraryToolAdapter, user: UserContext | None, query: str, *,
                         limit: int = 5, type: str | None = None, level: str | None = None) -> dict:
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
