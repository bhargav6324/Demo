"""Measured evaluation of the AI service (PDF success criterion "Evaluation").

Runs eval/cases.json through the real pipeline (in-process API, configured
LLM provider and embedder, mock adapter) and reports:
  outcome accuracy, search relevance (hit rate), citation accuracy,
  tool correctness, privacy/authorization, latency p50/p95.

Usage (from ai_service/):
  .venv/Scripts/python -m eval.run_eval                 # uses .env (LLM_PROVIDER, EMBEDDING_MODEL)
  LLM_PROVIDER=fake .venv/Scripts/python -m eval.run_eval
  .venv/Scripts/python -m eval.run_eval --delay 20      # pace requests for free-tier rate limits
"""
import argparse
import json
import logging
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import build_services

HERE = Path(__file__).resolve().parent
TOKENS = {"student": "mock-token-student", "student2": "mock-token-student2",
          "faculty": "mock-token-faculty", "librarian": "mock-token-librarian"}


class AuditCollector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.by_trace: dict[str, list[str]] = defaultdict(list)

    def emit(self, record):
        e = json.loads(record.getMessage())
        if e.get("event") == "tool_call":
            self.by_trace[e["trace_id"]].append(e["tool"])


def evaluate(case: dict, data: dict, tools: list[str], catalog: dict) -> dict:
    checks = {"outcome": data["outcome"] == case["expect_outcome"]}
    returned = [r["resource_id"] for r in data["resources"]]
    if "expect_any_resource" in case:
        checks["relevance"] = bool(set(returned[:5]) & set(case["expect_any_resource"]))
    if "expect_any_tool" in case:
        checks["tool"] = bool(set(tools) & set(case["expect_any_tool"]))
    if "expect_no_tool" in case:
        checks["privacy_no_tool"] = not (set(tools) & set(case["expect_no_tool"]))
    for rid, n in case.get("expect_available_copies", {}).items():
        r = next((x for x in data["resources"] if x["resource_id"] == rid), None)
        checks["availability_value"] = r is not None and r["available_copies"] == n
    # Citation accuracy: every citation/resource is a real catalog record with the real title
    cites_ok = all(c["resource_id"] in catalog for c in data["citations"]) and all(
        r["resource_id"] in catalog and r["title"] == catalog[r["resource_id"]].title for r in data["resources"])
    checks["citations"] = cites_ok
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to wait between cases")
    args = parser.parse_args()

    settings = Settings(tool_adapter="mock", rag_refresh_seconds=0)
    services = build_services(settings)
    if services.orchestrator is None:
        print(f"LLM not configured: {services.llm_error}. Set GEMINI_API_KEY or LLM_PROVIDER=fake.")
        return 2
    collector = AuditCollector()
    logging.getLogger("smartlibrary.audit").addHandler(collector)
    logging.getLogger("smartlibrary.audit").setLevel(logging.INFO)

    client = TestClient(create_app(services))
    catalog = services.adapter.resources
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

    services.retriever.store or __import__("asyncio").run(services.retriever.refresh())  # warm index

    rows, latencies = [], []
    for n, case in enumerate(cases):
        if n and args.delay:
            time.sleep(args.delay)
        headers = {"Authorization": f"Bearer {TOKENS[case['user']]}"} if case["user"] else {}
        t0 = time.perf_counter()
        resp = client.post("/api/v1/chat/messages", json={"message": case["message"]}, headers=headers)
        ms = (time.perf_counter() - t0) * 1000
        latencies.append(ms)
        if resp.status_code != 200:
            rows.append({"id": case["id"], "category": case["category"], "error": resp.json()["error"], "ms": ms,
                         "checks": {"outcome": False}})
            continue
        body = resp.json()
        tools = collector.by_trace.get(body["trace_id"], [])
        rows.append({"id": case["id"], "category": case["category"], "outcome": body["data"]["outcome"],
                     "tools": tools, "ms": round(ms), "checks": evaluate(case, body["data"], tools, catalog)})

    # ---- report
    def rate(metric):
        vals = [r["checks"][metric] for r in rows if metric in r["checks"]]
        return (sum(vals), len(vals))

    print(f"\nLLM={settings.llm_provider}/{settings.llm_model}  embedder={services.retriever.embedder.name}\n")
    print(f"{'case':24} {'outcome':20} {'ms':>6}  failed checks")
    for r in rows:
        failed = [k for k, v in r["checks"].items() if not v]
        print(f"{r['id']:24} {r.get('outcome', 'ERROR'):20} {r['ms']:>6.0f}  {', '.join(failed) or '-'}")

    summary = {}
    print("\nmetric                 score")
    for metric, label in [("outcome", "outcome accuracy"), ("relevance", "search relevance (hit@5)"),
                          ("citations", "citation accuracy"), ("tool", "tool correctness"),
                          ("availability_value", "availability correctness"),
                          ("privacy_no_tool", "privacy (no account tool)")]:
        ok, n = rate(metric)
        if n:
            summary[metric] = round(ok / n, 3)
            print(f"{label:28} {ok}/{n}  ({ok / n:.0%})")
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
    summary.update({"latency_p50_ms": round(p50), "latency_p95_ms": round(p95)})
    print(f"{'latency p50 / p95':28} {p50:.0f} ms / {p95:.0f} ms")

    report = {"llm": f"{settings.llm_provider}/{settings.llm_model}", "embedder": services.retriever.embedder.name,
              "summary": summary, "cases": rows}
    (HERE / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report: {HERE / 'report.json'}")
    return 0 if summary.get("outcome", 0) == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
