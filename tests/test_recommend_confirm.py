import pytest

from app.llm.fake_llm import ScriptedLLM, call, final
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.recommend.recommender import Recommender
from tests.conftest import AUTH
from tests.test_rag import INDEXER


@pytest.fixture
def recommender(adapter):
    return Recommender(adapter, Retriever(HashingEmbedder(), adapter, INDEXER, min_score=0.1))


# ---------------------------------------------------------------- recommendations

async def test_beginner_data_science_recommendations(recommender, adapter, student):
    res = await recommender.recommend(student, "data science", level="beginner", limit=5)
    items = res["items"]
    assert items, "expected recommendations"
    assert all(i["catalog_facts"]["level"] == "beginner" for i in items)
    assert "res-008" in [i["resource_id"] for i in items]
    assert res["profile_used"]["interests"] == ["data science", "machine learning"]


async def test_items_already_on_loan_are_excluded(recommender, student):
    res = await recommender.recommend(student, "python data analysis pandas", limit=10)
    assert not {"res-001", "res-005", "res-007"} & {i["resource_id"] for i in res["items"]}


async def test_facts_are_verified_and_separate_from_reasoning(recommender, adapter, student):
    res = await recommender.recommend(student, "data science", level="beginner")
    ds = next(i for i in res["items"] if i["resource_id"] == "res-008")
    assert ds["available_copies"] == adapter.availability["res-008"].available_copies
    assert ds["catalog_facts"]["location"] == "Central Library"
    assert "data science" in ds["relevance_reasoning"]          # profile interest explained
    assert "Catalog facts:" in ds["reason"] and "2 available" in ds["reason"]


async def test_available_only_filters_unavailable(recommender, student2):
    res = await recommender.recommend(student2, "generative ai deep learning", available_only=True)
    assert res["items"] and all(i["available_copies"] > 0 for i in res["items"])


async def test_empty_query_uses_profile(recommender, faculty):
    res = await recommender.recommend(faculty, "")
    assert res["items"]
    assert any("interest" in i["relevance_reasoning"] for i in res["items"])


def test_recommendation_through_chat(make_app):
    llm = ScriptedLLM([
        call("generate_recommendations", query="data science", level="beginner"),
        final("Here are beginner data science picks.", "recommendation"),
    ])
    client, _ = make_app(llm)
    d = client.post("/api/v1/chat/messages", json={"message": "Suggest beginner resources for data science"},
                    headers=AUTH["student"]).json()["data"]
    assert d["outcome"] == "answered" and d["intent"] == "recommendation"
    r = next(x for x in d["resources"] if x["resource_id"] == "res-008")
    assert r["available_copies"] == 2                     # verified number reaches the response
    assert "Catalog facts:" in r["reason"]                # engine reason, not model text
    assert all(c["source_type"] in ("catalog", "document") for c in d["citations"])


def test_recommendations_require_login(make_app):
    llm = ScriptedLLM([call("generate_recommendations", query="ai"), final("x", "recommendation")])
    client, _ = make_app(llm)
    d = client.post("/api/v1/chat/messages", json={"message": "recommend ai books"}).json()["data"]
    assert d["outcome"] == "refused"


# ---------------------------------------------------------------- confirmation

def propose(client, tool, headers=AUTH["student"], **args):
    """Drive a chat turn that proposes one action; returns the action_id."""
    client.app.state.services.orchestrator.llm = ScriptedLLM([call(tool, **args), final("Please confirm.", "general")])
    d = client.post("/api/v1/chat/messages", json={"message": "do it"}, headers=headers).json()["data"]
    assert d["outcome"] == "needs_confirmation", d
    return d["proposed_action"]["action_id"]


def confirm(client, action_id, headers=AUTH["student"], **extra):
    return client.post("/api/v1/chat/actions/confirm", json={"action_id": action_id, **extra}, headers=headers)


def test_reservation_request_then_confirm(make_app):
    client, services = make_app(ScriptedLLM([]))
    action_id = propose(client, "create_reservation", resource_id="res-006")
    assert services.adapter.availability["res-006"].available_copies == 2  # untouched before confirm

    body = confirm(client, action_id).json()
    assert body["status"] == "success" and body["trace_id"]
    d = body["data"]
    assert d["transaction_status"] == "succeeded" and d["action_type"] == "reservation"
    assert d["reservation_id"].startswith("rsv-")
    assert "Machine Learning for Absolute Beginners" in d["message"]
    assert services.adapter.availability["res-006"].available_copies == 1

    # Double click: same result, no second reservation
    again = confirm(client, action_id).json()["data"]
    assert again["reservation_id"] == d["reservation_id"]
    assert services.adapter.availability["res-006"].available_copies == 1


def test_waitlist_reservation_message(make_app):
    client, _ = make_app(ScriptedLLM([]))
    d = confirm(client, propose(client, "create_reservation", resource_id="res-023")).json()["data"]
    assert d["transaction_status"] == "succeeded" and "waitlist" in d["message"] and "position 3" in d["message"]


def test_renewal_request_then_confirm(make_app):
    client, services = make_app(ScriptedLLM([]))
    old_due = services.adapter.loans["loan-5001"]["loan"].due_at
    d = confirm(client, propose(client, "renew_loan", loan_id="loan-5001")).json()["data"]
    assert d["transaction_status"] == "succeeded" and d["loan_id"] == "loan-5001"
    assert (services.adapter.loans["loan-5001"]["loan"].due_at - old_due).days == 14
    assert "New due date" in d["message"]


def test_confirm_requires_owner(make_app):
    client, _ = make_app(ScriptedLLM([]))
    action_id = propose(client, "create_reservation", resource_id="res-006")
    assert confirm(client, action_id, headers=AUTH["student2"]).status_code == 404
    assert confirm(client, action_id, headers={}).status_code == 401


def test_unknown_and_expired_actions(make_app):
    client, services = make_app(ScriptedLLM([]))
    assert confirm(client, "act-doesnotexist").status_code == 404
    action_id = propose(client, "create_reservation", resource_id="res-006")
    services.actions.clock = lambda: 10**12  # far future -> expired
    resp = confirm(client, action_id)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "action_not_found"


def test_client_cannot_change_arguments(make_app):
    client, services = make_app(ScriptedLLM([]))
    action_id = propose(client, "create_reservation", resource_id="res-006")
    d = confirm(client, action_id, resource_id="res-004", tool="renew_loan").json()["data"]
    assert d["details"]["resource_id"] == "res-006"   # stored args used, extras ignored


def test_business_failure_at_confirm_time(make_app):
    client, services = make_app(ScriptedLLM([]))
    action_id = propose(client, "renew_loan", loan_id="loan-5003")
    services.adapter.availability["res-001"].waitlist_count = 1  # someone joined the waitlist meanwhile
    d = confirm(client, action_id).json()["data"]
    assert d["transaction_status"] == "failed" and d["details"]["error_code"] == "not_renewable"
    assert confirm(client, action_id).status_code == 404  # failed action is discarded


def test_outage_at_confirm_time_is_retryable(make_app):
    client, services = make_app(ScriptedLLM([]))
    action_id = propose(client, "create_reservation", resource_id="res-006")
    services.adapter.failures["create_reservation"] = "timeout"
    d = confirm(client, action_id).json()["data"]
    assert d["transaction_status"] == "failed" and "Nothing was changed" in d["message"]
    services.adapter.failures.clear()
    d = confirm(client, action_id).json()["data"]
    assert d["transaction_status"] == "succeeded"
    assert services.adapter.availability["res-006"].available_copies == 1
