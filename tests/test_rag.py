import os
from datetime import datetime, timezone

import pytest

from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.auth.context import UserContext
from app.llm.fake_llm import ScriptedLLM, call, final
from app.rag.embedder import HashingEmbedder, build_embedder
from app.rag.ingest import dedup_key, split_text
from app.rag.retriever import Retriever
from app.schemas.library import Resource
from tests.conftest import AUTH, FIXTURES

INDEXER = UserContext("svc-ai-indexer", "AI Indexer", "librarian", token="")


def make_retriever(adapter, embedder=None, min_score=0.1):
    return Retriever(embedder or HashingEmbedder(), adapter, INDEXER, min_score=min_score)


# ---------------------------------------------------------------- ingestion

def test_dedup_key_matches_reimported_record():
    assert dedup_key("Python  Crash Course ", ["Eric Matthes"]) == dedup_key("Python Crash Course", ["Eric Matthes"])
    assert dedup_key("Python Crash Course", ["Eric Matthes"]) != dedup_key("Fluent Python", ["Luciano Ramalho"])


def test_split_text_keeps_sections_and_bounds_size():
    text = "# Title\n\n## Approach\n" + ("Sentence about retrieval. " * 80) + "\n## Findings\nShort."
    chunks = split_text(text, size=300, overlap=50)
    assert all(len(t) <= 300 for _, t in chunks)
    assert {s for s, _ in chunks} == {"Approach", "Findings"}


async def test_index_build_dedups_and_ingests_documents(adapter):
    r = make_retriever(adapter)
    stats = await r.refresh()
    assert stats["seen"] == 26 and stats["duplicates"] == 1 and stats["documents"] == 8
    assert r.duplicates == {"res-026": "res-001"}
    assert "res-026" not in r.store.resource_ids()


async def test_every_chunk_has_required_fields(adapter):
    r = make_retriever(adapter)
    await r.refresh()
    for chunk in r.store._chunks.values():
        assert chunk.chunk_id and chunk.resource_id and chunk.title and chunk.text
        assert chunk.source_type in ("catalog", "document")
        assert chunk.access_level in ("public", "university", "restricted")
        assert "type" in chunk.metadata


# ---------------------------------------------------------------- retrieval

async def test_research_search_returns_papers_with_passages(adapter, student):
    r = make_retriever(adapter)
    res = await r.search(student, "retrieval-augmented generation dense retriever", limit=5)
    ids = [i["resource_id"] for i in res["items"]]
    assert "res-013" in ids
    rag_paper = next(i for i in res["items"] if i["resource_id"] == "res-013")
    assert rag_paper["passages"] and rag_paper["passages"][0]["chunk_id"].startswith("res-013#c")


async def test_type_and_level_filters(adapter, student):
    r = make_retriever(adapter)
    res = await r.search(student, "retrieval", type="paper")
    assert res["items"] and all(i["type"] == "paper" for i in res["items"])


async def test_restricted_content_hidden_from_students(adapter, student, faculty):
    r = make_retriever(adapter)
    q = "hybrid sparse dense retrieval re-ranking library catalog nDCG"
    student_hit = next(i for i in (await r.search(student, q))["items"] if i["resource_id"] == "res-019")
    assert student_hit["passages"] == []           # metadata visible, embargoed text not
    faculty_hit = next(i for i in (await r.search(faculty, q))["items"] if i["resource_id"] == "res-019")
    assert faculty_hit["passages"]                  # entitled role sees the text


async def test_university_content_hidden_from_anonymous(adapter):
    r = make_retriever(adapter)
    res = await r.search(None, "Self-RAG reflection tokens critique adaptive retrieval")
    hit = next(i for i in res["items"] if i["resource_id"] == "res-016")
    assert hit["passages"] == []


async def test_deleted_resource_dropped_at_query_time(adapter, student):
    r = make_retriever(adapter)
    await r.refresh()
    del adapter.resources["res-013"]  # removed from the catalog after indexing
    res = await r.search(student, "retrieval-augmented generation")
    assert "res-013" not in [i["resource_id"] for i in res["items"]]


async def test_titles_come_from_live_catalog(adapter, student):
    r = make_retriever(adapter)
    await r.refresh()
    adapter.resources["res-013"] = adapter.resources["res-013"].model_copy(update={"title": "RAG (Revised Title)"})
    res = await r.search(student, "retrieval-augmented generation")
    assert next(i for i in res["items"] if i["resource_id"] == "res-013")["title"] == "RAG (Revised Title)"


async def test_incremental_refresh_makes_new_resource_searchable(adapter, student):
    r = make_retriever(adapter)
    await r.refresh()
    before = len(r.store)
    adapter.resources["res-100"] = Resource(
        resource_id="res-100", title="Graph Neural Networks Primer", authors=["New Author"], type="book",
        description="Introductory guide to graph neural networks and message passing.",
        topics=["graph neural networks", "deep learning"], level="beginner", access_level="public",
        updated_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
    )
    stats = await r.refresh()
    assert stats["seen"] == 1 and stats["indexed"] == 1    # only the changed record was fetched
    assert len(r.store) == before + 1
    res = await r.search(student, "graph neural networks message passing")
    assert res["items"][0]["resource_id"] == "res-100"


async def test_backend_outage_during_search_raises_tool_error(student):
    from app.adapters.errors import ToolError

    adapter = MockLibraryToolAdapter(FIXTURES)
    r = make_retriever(adapter)
    await r.refresh()
    adapter.failures["get_resource"] = "timeout"
    with pytest.raises(ToolError):
        await r.search(student, "retrieval")


# ---------------------------------------------------------------- via chat

def test_semantic_search_tool_through_chat_has_chunk_citations(make_app):
    llm = ScriptedLLM([
        call("semantic_search", query="retrieval-augmented generation", type="paper"),
        final("RAG combines a retriever with a generator [Lewis et al.].", "research",
              [{"resource_id": "res-013", "reason": "Original RAG paper"}]),
    ])
    client, _ = make_app(llm)
    d = client.post("/api/v1/chat/messages", json={"message": "Find papers related to RAG"},
                    headers=AUTH["student"]).json()["data"]
    assert d["outcome"] == "answered"
    types = {(c["source_type"], c["resource_id"]) for c in d["citations"]}
    assert ("catalog", "res-013") in types and ("document", "res-013") in types
    assert all(c["resource_id"] == "res-013" for c in d["citations"])  # only cited resource's sources
    # passages reached the model wrapped as untrusted
    tool_msg = next(m for m in llm.requests[-1]["messages"] if m["role"] == "tool")
    assert tool_msg["content"]["data"]["items"][0]["passages"][0]["text"].startswith("<<UNTRUSTED_CONTENT>>")


def test_duplicate_records_collapse_in_chat_results(make_app):
    llm = ScriptedLLM([call("search_catalog", query="python crash course"), final("Found it.", "search")])
    client, _ = make_app(llm)
    d = client.post("/api/v1/chat/messages", json={"message": "python crash course"}).json()["data"]
    titles = [r["title"].strip() for r in d["resources"]]
    assert titles.count("Python Crash Course") == 1


def test_index_refresh_endpoint_librarian_only(make_app):
    client, _ = make_app(ScriptedLLM([]))
    assert client.post("/api/v1/index/refresh", headers=AUTH["student"]).status_code == 403
    resp = client.post("/api/v1/index/refresh", headers=AUTH["librarian"])
    assert resp.status_code == 200 and resp.json()["data"]["indexed"] == 25


# ---------------------------------------------------------------- real model (opt-in)

@pytest.mark.skipif(os.getenv("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1 to run with the real embedding model")
async def test_real_model_semantic_quality(adapter, student):
    r = make_retriever(adapter, build_embedder("sentence-transformers/all-MiniLM-L6-v2"), min_score=0.3)
    res = await r.search(student, "how do language models look up external documents before answering?")
    assert res["items"][0]["resource_id"] in {"res-013", "res-016", "res-012"}
    res = await r.search(student, "zzqx flibbertigibbet wombat sonata")
    assert res["items"] == []
