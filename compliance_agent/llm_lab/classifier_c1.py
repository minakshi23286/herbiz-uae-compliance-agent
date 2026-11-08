"""Option C1 (Workstream B): an optional stage-1 classifier using Claude Haiku 5.5 through the existing `anthropic` SDK.

It only NAMES topics from a closed list (the v7 curated topics) or an out-of-scope class. It never sees legal passages and
never answers. Provision mapping, retrieval, G1/G3 validity rules and certification stay deterministic (pipeline_c1.py).

The client is injected: tests and dry runs use FakeC1Client (no network, no spend). A real client is created only by the
paid-run harness, after the founder approves the exact run.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

from . import pipeline_v7 as P7

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 1024
EFFORT = "low"
OOS_CLASSES = ["none", "non_uae_vat", "corporate_tax", "other_regime", "not_tax"]
MAX_TOPICS = 4


@lru_cache(maxsize=1)
def topic_catalogue() -> list[tuple[str, str]]:
    """(topic, description) for every curated v7 topic; the description is the titles of its required articles (data
    built from the corpus), so the list follows the law's own wording."""
    T = P7.tables()
    out = []
    for name in sorted(T["curated"]):
        parts = []
        for ref in T["curated"][name]["required"]:
            src, art = ref.split("|", 1)
            short = {"FTA-VAT-DL8": "Decree-Law", "FTA-VAT-ER": "Executive Regulation", "FTA-VAT-REG-PAGE": "FTA registration page"}[src]
            title = T["articles"].get(ref, {}).get("title", "") if art != "*" else "thresholds and how to register"
            parts.append(f"{short} Art. {art}: {title}" if art != "*" else f"{short}: {title}")
        out.append((name, "; ".join(parts)))
    return out


def system_prompt() -> str:
    lines = "\n".join(f"- {n}: {d}" for n, d in topic_catalogue())
    return (
        "You classify questions from small-business owners about UAE VAT (Federal Decree-Law No. 8 of 2017 and its Executive "
        "Regulation). You do not answer the question. Choose up to 4 topics from the list below that a correct answer must "
        "rest on, most important first. If the question is not about UAE VAT, set in_scope to false and choose the class: "
        "non_uae_vat (VAT or sales tax of another country), corporate_tax (UAE or other corporate or income tax, even if the "
        "FTA is mentioned), other_regime (licences, visas, municipality, customs, labour or other laws), not_tax (anything else). "
        "Set confidence to low if the wording is unclear, the facts fit several topics, or no listed topic fits well.\n\n"
        f"Topics:\n{lines}")


def schema() -> dict:
    names = [n for n, _ in topic_catalogue()]
    return {"type": "object", "additionalProperties": False,
            "required": ["in_scope", "out_of_scope_class", "topics", "confidence"],
            "properties": {"in_scope": {"type": "boolean"},
                           "out_of_scope_class": {"type": "string", "enum": OOS_CLASSES},
                           "topics": {"type": "array", "items": {"type": "string", "enum": names}},
                           "confidence": {"type": "string", "enum": ["high", "low"]}}}


def request(question: str) -> dict:
    """The exact request body sent to the API (also used to document and estimate the data sent)."""
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system_prompt(),
            "messages": [{"role": "user", "content": f"Owner's question:\n<question>\n{question}\n</question>"}],
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": schema()}}}


def _text(resp) -> str:
    return next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")


def classify(question: str, client) -> dict:
    """Returns {ok, in_scope, oos_class, topics, confidence, error, latency_ms, usage, stop_reason}. Any failure (exception,
    refusal, truncation, invalid JSON, unknown topic) gives ok=False; the pipeline then never certifies."""
    t0 = time.monotonic()
    out = {"ok": False, "in_scope": None, "oos_class": None, "topics": [], "confidence": None, "error": None,
           "latency_ms": None, "usage": None, "stop_reason": None, "model_returned": None}
    try:
        resp = client.messages.create(**request(question))
    except Exception as e:   # network, rate limit, server error, timeout: recorded, never certified
        out.update(error=f"{type(e).__name__}: {e}", latency_ms=int((time.monotonic() - t0) * 1000))
        return out
    out["latency_ms"] = int((time.monotonic() - t0) * 1000)
    out["stop_reason"] = getattr(resp, "stop_reason", None)
    out["model_returned"] = getattr(resp, "model", None)
    u = getattr(resp, "usage", None)
    out["usage"] = {"input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None)} if u else None
    if out["stop_reason"] != "end_turn":
        out["error"] = f"stop_reason {out['stop_reason']}"
        return out
    try:
        d = json.loads(_text(resp))
    except (json.JSONDecodeError, TypeError) as e:
        out["error"] = f"invalid JSON: {e}"
        return out
    names = {n for n, _ in topic_catalogue()}
    topics = d.get("topics") or []
    if (not isinstance(d.get("in_scope"), bool) or d.get("out_of_scope_class") not in OOS_CLASSES
            or d.get("confidence") not in ("high", "low") or any(t not in names for t in topics)):
        out["error"] = "response outside the schema"
        return out
    if d["in_scope"] and d["out_of_scope_class"] != "none" or (not d["in_scope"] and d["out_of_scope_class"] == "none"):
        out["error"] = "in_scope and out_of_scope_class contradict"
        return out
    out.update(ok=True, in_scope=d["in_scope"], oos_class=d["out_of_scope_class"], topics=list(dict.fromkeys(topics))[:MAX_TOPICS],
               confidence=d["confidence"])
    return out


class FakeC1Client:
    """Offline mock of the Messages API for C1 (no network, no spend). `respond(question) -> dict | Exception | str` gives
    the classifier output; a str is returned as raw text (to test invalid JSON); stop_reason can be forced."""

    def __init__(self, respond, stop_reason: str = "end_turn"):
        self.respond, self.stop_reason, self.calls, self.requests = respond, stop_reason, 0, []
        self.messages = self

    def create(self, **kw):
        from types import SimpleNamespace
        self.calls += 1
        self.requests.append(kw)
        q = kw["messages"][0]["content"].split("<question>\n", 1)[1].rsplit("\n</question>", 1)[0]
        r = self.respond(q)
        if isinstance(r, Exception):
            raise r
        text = r if isinstance(r, str) else json.dumps(r)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self.stop_reason, model=MODEL,
                               usage=SimpleNamespace(input_tokens=len(kw["system"]) // 4, output_tokens=60))


def oracle_from_v7(question: str) -> dict:
    """Mock response that copies the deterministic v7 classification (for exercising the agreement path offline).
    It says nothing about C1's real quality."""
    c = P7.classify(question)
    if c["out_of_scope"]:
        return {"in_scope": False, "out_of_scope_class": "other_regime", "topics": [], "confidence": "high"}
    names = {n for n, _ in topic_catalogue()}
    return {"in_scope": True, "out_of_scope_class": "none", "topics": [t for t in c["intents"] if t in names][:MAX_TOPICS],
            "confidence": "low" if c["ambiguous"] else "high"}
