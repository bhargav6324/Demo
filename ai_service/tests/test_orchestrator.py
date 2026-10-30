from app.llm.base import LLMError, LLMResponse
from app.llm.fake_llm import RuleBasedLLM, ScriptedLLM, call, final
from tests.conftest import AUTH


def chat(client, message, headers=None, conversation_id=None):
    resp = client.post("/api/v1/chat/messages", json={"message": message, "conversation_id": conversation_id},
                       headers=headers or {})
    return resp


# ---------------------------------------------------------------- grounding

def test_search_python_grounded_and_cited(make_app):
    llm = ScriptedLLM([
        call("search_catalog", query="python"),
        final("Here are Python books.", "search", [
            {"resource_id": "res-001", "reason": "Beginner Python intro"},
            {"resource_id": "res-999", "reason": "hallucinated"},  # never returned by a tool
        ]),
    ])
    client, _ = make_app(llm)
    body = chat(client, "Find books about Python").json()
    assert body["status"] == "success" and body["trace_id"]
    d = body["data"]
    assert d["outcome"] == "answered" and d["intent"] == "search"
    assert [r["resource_id"] for r in d["resources"]] == ["res-001"]   # res-999 dropped
    assert d["resources"][0]["title"] == "Python Crash Course"         # title from tool, not model
    assert d["resources"][0]["available_copies"] is None               # never checked -> not claimed
    assert d["citations"] == [{"resource_id": "res-001", "source_type": "catalog",
                               "source_id": "res-001", "title": "Python Crash Course"}]
    assert d["proposed_action"] is None and d["conversation_id"]


def test_availability_uses_tool_values(make_app):
    llm = ScriptedLLM([
        call("search_catalog", query="Artificial Intelligence: A Modern Approach", limit=1),
        call("get_availability", resource_id="res-004"),
        final("All 3 copies are on loan; 6 people are waiting.", "availability", [{"resource_id": "res-004"}]),
    ])
    client, _ = make_app(llm)
    d = chat(client, "Is Artificial Intelligence: A Modern Approach available?").json()["data"]
    assert d["outcome"] == "answered"
    assert d["resources"][0]["available_copies"] == 0


def test_model_without_tools_cannot_cite(make_app):
    llm = ScriptedLLM([final("Try 'Python Crash Course'.", "search", [{"resource_id": "res-001"}])])
    client, _ = make_app(llm)
    d = chat(client, "python books?").json()["data"]
    assert d["outcome"] == "not_found" and d["resources"] == [] and d["citations"] == []


def test_nonexistent_title_not_found(make_app):
    llm = ScriptedLLM([call("search_catalog", query="Quantum Basket Weaving for Dragons"),
                       final("Nothing found.", "search")])
    client, _ = make_app(llm)
    d = chat(client, "Find Quantum Basket Weaving for Dragons").json()["data"]
    assert d["outcome"] == "not_found" and d["resources"] == []


def test_fallback_resources_when_model_omits_them(make_app):
    llm = ScriptedLLM([call("search_catalog", query="python"), final("Some Python books.", "search")])
    client, _ = make_app(llm)
    d = chat(client, "python").json()["data"]
    assert d["outcome"] == "answered" and d["resources"][0]["resource_id"] == "res-001"


# ---------------------------------------------------------------- account & privacy

def test_my_loans(make_app):
    llm = ScriptedLLM([call("get_my_loans"), final("You have 3 loans.", "account")])
    client, services = make_app(llm)
    d = chat(client, "Show my current loans", AUTH["student"]).json()["data"]
    assert d["outcome"] == "answered" and d["intent"] == "account"


def test_loans_anonymous_refused(make_app):
    llm = ScriptedLLM([call("get_my_loans"), final("Please sign in.", "account")])
    client, _ = make_app(llm)
    d = chat(client, "Show my loans").json()["data"]
    assert d["outcome"] == "refused"


def test_other_users_history_refused(make_app):
    llm = ScriptedLLM([final("I can't share another person's borrowing history.", "account", abstain="privacy")])
    client, _ = make_app(llm)
    d = chat(client, "What has Meera borrowed?", AUTH["student"]).json()["data"]
    assert d["outcome"] == "refused" and d["resources"] == []


def test_student_analytics_refused_librarian_allowed(make_app):
    steps = lambda: [call("get_library_analytics"), final("Top waitlists...", "analytics")]
    client, _ = make_app(ScriptedLLM(steps()))
    assert chat(client, "Which titles have the longest waitlists?", AUTH["student"]).json()["data"]["outcome"] == "refused"
    client, _ = make_app(ScriptedLLM(steps()))
    d = chat(client, "Which titles have the longest waitlists?", AUTH["librarian"]).json()["data"]
    assert d["outcome"] == "answered" and d["intent"] == "analytics"


# ---------------------------------------------------------------- actions

def test_reservation_proposed_not_executed(make_app):
    llm = ScriptedLLM([call("create_reservation", resource_id="res-006"),
                       final("I've prepared the reservation; please confirm.", "reservation", [{"resource_id": "res-006"}])])
    client, services = make_app(llm)
    before = services.adapter.availability["res-006"].available_copies
    d = chat(client, "Reserve Machine Learning for Absolute Beginners", AUTH["student"]).json()["data"]
    assert d["outcome"] == "needs_confirmation"
    pa = d["proposed_action"]
    assert pa["action_type"] == "reservation" and pa["resource_id"] == "res-006"
    assert pa["action_id"].startswith("act-") and "Central Library" in pa["description"]
    assert services.adapter.availability["res-006"].available_copies == before  # nothing changed
    assert services.actions.get(pa["action_id"]).owner == "u-1001"


def test_renewal_proposed(make_app):
    llm = ScriptedLLM([call("renew_loan", loan_id="loan-5001"), final("Confirm renewal?", "renewal")])
    client, _ = make_app(llm)
    d = chat(client, "Renew loan-5001", AUTH["student"]).json()["data"]
    assert d["outcome"] == "needs_confirmation"
    assert d["proposed_action"]["loan_id"] == "loan-5001"
    assert d["proposed_action"]["resource_id"] == "res-007"


def test_only_one_action_per_turn(make_app):
    llm = ScriptedLLM([[call("create_reservation", resource_id="res-006"),
                        call("create_reservation", resource_id="res-008")],
                       final("Confirm?", "reservation")])
    client, _ = make_app(llm)
    d = chat(client, "Reserve both", AUTH["student"]).json()["data"]
    assert d["proposed_action"]["resource_id"] == "res-006"
    tool_msgs = [m for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert tool_msgs[1]["content"]["error"]["code"] == "one_action_per_turn"


# ---------------------------------------------------------------- safety & robustness

def test_unknown_tool_and_bad_args_rejected(make_app):
    llm = ScriptedLLM([[call("drop_database"), call("get_availability", resource_id="http://evil")],
                       final("Sorry.", "general")])
    client, _ = make_app(llm)
    d = chat(client, "do something", AUTH["student"]).json()["data"]
    errs = [m["content"]["error"]["code"] for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert errs == ["unknown_tool", "invalid_argument"]
    assert d["resources"] == []


def test_tool_loop_is_bounded(make_app):
    llm = ScriptedLLM([call("search_catalog", query="python")] * 20)
    client, _ = make_app(llm, max_tool_calls=3)
    resp = chat(client, "loop forever")
    assert resp.status_code == 200
    assert len(llm.requests) == 4                          # 3 tool rounds + 1 final-only round
    assert llm.requests[-1]["tools"] == ["final_answer"]   # only final_answer offered at the limit
    assert resp.json()["data"]["assistant_message"]


def test_backend_outage_graceful(make_app):
    llm = ScriptedLLM([call("search_catalog", query="python"), final("Here are books", "search")])
    client, _ = make_app(llm, failures={"*": "timeout"})
    d = chat(client, "python books").json()["data"]
    assert d["outcome"] == "answered" and "temporarily unavailable" in d["assistant_message"]
    assert d["resources"] == []


def test_llm_failure_returns_503(make_app):
    class Broken(ScriptedLLM):
        async def generate(self, *a):
            raise LLMError("quota")
    client, _ = make_app(Broken([]))
    resp = chat(client, "hello")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "llm_unavailable"


def test_untrusted_content_wrapped_and_prompt_has_no_secrets(make_app):
    llm = ScriptedLLM([call("get_resource_content", resource_id="res-025"), final("Summary.", "research")])
    client, _ = make_app(llm)
    chat(client, "Summarize res-025", AUTH["student"])
    req = llm.requests[-1]
    tool_msg = next(m for m in req["messages"] if m["role"] == "tool")
    assert tool_msg["content"]["data"]["text"].startswith("<<UNTRUSTED_CONTENT>>")
    assert "mock-token-student" not in req["system"] and "u-1001" not in req["system"]
    assert "Aarav Sharma" in req["system"]


def test_invalid_token_401(make_app):
    client, _ = make_app(ScriptedLLM([]))
    resp = chat(client, "hi", {"Authorization": "Bearer forged"})
    assert resp.status_code == 401 and resp.json()["status"] == "error"


def test_conversation_memory_and_ownership(make_app):
    llm = ScriptedLLM([call("search_catalog", query="python"), final("Books", "search"),
                       final("Follow-up", "general")])
    client, _ = make_app(llm)
    cid = chat(client, "python", AUTH["student"]).json()["data"]["conversation_id"]
    # Another user cannot hijack the conversation
    resp = chat(client, "what did I ask?", AUTH["student2"], conversation_id=cid)
    assert resp.status_code == 404
    chat(client, "what did I ask?", AUTH["student"], conversation_id=cid)
    history = llm.requests[-1]["messages"]
    assert history[0] == {"role": "user", "content": "python"}
    assert "res-001" in history[1]["content"]  # verified resources carried into context


def test_plain_text_response_handled(make_app):
    llm = ScriptedLLM([lambda msgs: LLMResponse(text="Hello! How can I help?")])
    client, _ = make_app(llm)
    d = chat(client, "hi").json()["data"]
    assert d["outcome"] == "answered" and d["assistant_message"] == "Hello! How can I help?"


# ---------------------------------------------------------------- offline rule-based LLM

def test_rule_based_llm_end_to_end(make_app):
    client, _ = make_app(RuleBasedLLM())
    d = chat(client, "Find books on Python programming").json()["data"]
    assert d["outcome"] == "answered" and d["resources"][0]["resource_id"] == "res-001"

    d = chat(client, "Is Artificial Intelligence: A Modern Approach available?").json()["data"]
    assert d["resources"][0]["resource_id"] == "res-004" and d["resources"][0]["available_copies"] == 0

    d = chat(client, "Show me Meera's borrowing history", AUTH["student"]).json()["data"]
    assert d["outcome"] == "refused"

    d = chat(client, "Show library analytics", AUTH["student"]).json()["data"]
    assert d["outcome"] == "refused"

    d = chat(client, "Reserve res-006", AUTH["student"]).json()["data"]
    assert d["outcome"] == "needs_confirmation"

    d = chat(client, "Find papers related to retrieval-augmented generation", AUTH["student"]).json()["data"]
    assert d["intent"] == "research"
    assert any(c["source_type"] == "document" for c in d["citations"])
