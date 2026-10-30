"""Personalized, explainable recommendations.

profile -> semantic candidates -> rank (relevance + profile signals)
-> exclude items already on loan -> verify live availability -> explain.

Each item separates `catalog_facts` (verified data from tools) from
`relevance_reasoning` (system-generated reasons for the match)."""
import asyncio
import re

from app.adapters.base import LibraryToolAdapter
from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.rag.retriever import Retriever

INTEREST_WEIGHT = 0.08   # per matched interest (max 2)
COURSE_WEIGHT = 0.05     # if any course keyword matches
_COURSE_STOP = {"fundamentals", "introduction", "intro", "advanced", "and", "of", "the", "to", "for"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _COURSE_STOP}


class Recommender:
    def __init__(self, adapter: LibraryToolAdapter, retriever: Retriever):
        self.adapter = adapter
        self.retriever = retriever

    async def recommend(self, user: UserContext, query: str = "", level: str | None = None,
                        limit: int = 5, available_only: bool = False) -> dict:
        profile, loans = await asyncio.gather(self.adapter.get_profile(user), self.adapter.get_my_loans(user))
        on_loan = {l.resource_id for l in loans if l.status != "returned"}

        # The stated query leads; profile interests fill in when the query is vague or empty
        search_text = query.strip() or " ".join(profile.interests + profile.courses)
        if not search_text:
            return {"profile_used": {"courses": [], "interests": []}, "items": [], "total": 0}
        found = await self.retriever.search(user, search_text, limit=limit * 4, level=level)

        interests = [i.lower() for i in profile.interests]
        course_words = {c: _words(re.sub(r"^[A-Z]+\d+\s*", "", c)) for c in profile.courses}

        scored = []
        for item in found["items"]:
            if item["resource_id"] in on_loan:
                continue
            haystack = " ".join([item["title"], item["description"], " ".join(item.get("topics", []))]).lower()
            matched_interests = [i for i in interests if i in haystack][:2]
            hay_words = _words(haystack)
            # A course counts only if most of its keywords appear (one shared word like "language" is noise)
            matched_courses = [c for c, words in course_words.items()
                               if words and len(words & hay_words) >= min(2, len(words))]
            score = item["relevance"] + INTEREST_WEIGHT * len(matched_interests) + (COURSE_WEIGHT if matched_courses else 0)
            scored.append((score, item, matched_interests, matched_courses))
        scored.sort(key=lambda s: -s[0])

        # Verify live availability for a slightly larger pool so available_only can still fill the list
        pool = scored[: limit * 2 if available_only else limit]
        availabilities = await asyncio.gather(*(self._availability(user, s[1]["resource_id"]) for s in pool))

        items = []
        for (score, item, interests_hit, courses_hit), avail in zip(pool, availabilities):
            available = avail.available_copies if avail else None
            if available_only and not available:
                continue
            branch = next((l.branch for l in avail.locations if l.available_copies > 0), None) if avail else None
            facts = {
                "type": item["type"], "level": item["level"], "authors": item["authors"],
                "available_copies": available,
                "waitlist_count": avail.waitlist_count if avail else None,
                "location": branch,
            }
            reasoning = self._reasoning(query, level, item, interests_hit, courses_hit)
            items.append({
                "resource_id": item["resource_id"],
                "title": item["title"],
                "score": round(score, 3),
                "catalog_facts": facts,
                "relevance_reasoning": reasoning,
                "reason": f"{reasoning} Catalog facts: {self._facts_text(facts)}.",
                "available_copies": available,
            })
            if len(items) >= limit:
                break

        return {
            "profile_used": {"courses": profile.courses, "interests": profile.interests},
            "items": items,
            "total": len(items),
        }

    async def _availability(self, user, resource_id):
        try:
            return await self.adapter.get_availability(user, resource_id)
        except ToolError as e:
            if e.code == ToolError.NOT_FOUND:
                return None
            raise

    @staticmethod
    def _reasoning(query, level, item, interests_hit, courses_hit) -> str:
        parts = []
        if query.strip():
            parts.append(f"Semantically relevant to \"{query.strip()}\"")
        if interests_hit:
            parts.append("matches your interest in " + " and ".join(interests_hit))
        if courses_hit:
            parts.append("related to your course " + courses_hit[0])
        if level:
            parts.append(f"{level} level as requested")
        if not parts:
            parts.append("Closest match to your profile")
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."

    @staticmethod
    def _facts_text(f: dict) -> str:
        avail = ("availability not verified" if f["available_copies"] is None
                 else f"{f['available_copies']} available" + (f" at {f['location']}" if f["location"] else "")
                 if f["available_copies"] else f"none available now (waitlist {f['waitlist_count']})")
        return f"{f['level']} {f['type'].replace('_', ' ')} by {', '.join(f['authors'][:2])}; {avail}"
