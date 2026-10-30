"""search_catalog tool: natural-language queries on top of the backend's
literal-substring /resources filter."""
from app.tools.catalog_search import keywords, search_catalog


def test_keywords_drop_stopwords_and_stem():
    assert set(keywords("Find beginner-friendly books on machine learning")) == {"beginner-friendly", "machine"}
    kws = keywords("papers on Python programming")
    assert "paper" in kws and "python" in kws and "on" not in kws


async def test_natural_language_query_finds_titles(adapter):
    res = await search_catalog(adapter, None, "beginner books on machine learning")
    assert "res-006" in [r.resource_id for r in res["items"]]


async def test_title_matches_rank_first(adapter):
    res = await search_catalog(adapter, None, "python programming")
    assert "python" in res["items"][0].title.lower()


async def test_single_common_keyword_is_not_enough(adapter):
    # "engineering" appears in real titles, but the other keywords match nothing
    res = await search_catalog(adapter, None, "The Lost Manuscripts of Atlantis Engineering")
    assert res["items"] == [] and res["total"] == 0


async def test_exact_title_phrase(adapter):
    res = await search_catalog(adapter, None, "Artificial Intelligence: A Modern Approach")
    assert res["items"][0].resource_id == "res-004"


async def test_filters_passed_to_backend(adapter):
    res = await search_catalog(adapter, None, "learning", type="paper")
    assert all(r.type == "paper" for r in res["items"])


async def test_only_contract_calls_are_made(adapter):
    calls = []
    original = adapter.search_resources

    async def spy(*a, **k):
        calls.append(k)
        return await original(*a, **k)
    adapter.search_resources = spy
    await search_catalog(adapter, None, "deep learning neural networks")
    assert calls and all(1 <= c["limit"] <= 100 for c in calls)
    assert len(calls) <= 5  # phrase + at most 4 keywords
