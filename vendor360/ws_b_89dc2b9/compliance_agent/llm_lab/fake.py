"""Offline fake client for tests and dry runs. Mimics the response fields the runner reads. Never touches the network."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace


class FakeClient:
    def __init__(self, behaviour: str = "grounded", model_override: str | None = None):
        self.behaviour = behaviour
        self.model_override = model_override
        self.calls = 0
        self.messages = self

    def count_tokens(self, model, system, messages):
        if self.behaviour == "unknown_model":
            err = type("NotFoundError", (Exception,), {})("not found")
            raise err
        return SimpleNamespace(input_tokens=int((len(system) + len(messages[0]["content"])) / 4))

    def create(self, model, max_tokens, system, messages, output_config):
        self.calls += 1
        if self.behaviour == "error":
            e = type("InternalServerError", (Exception,), {})("boom")
            e.status_code = 500
            raise e
        if self.behaviour == "badrequest":
            e = type("BadRequestError", (Exception,), {})("invalid schema")
            e.status_code = 400
            e.message = "output_config.format: example problem"
            raise e
        if self.behaviour == "billing":
            e = type("APIStatusError", (Exception,), {})("credit")
            e.status_code = 402
            raise e
        content = messages[0]["content"]
        first = re.search(r"\[([^\]]+#\d{4})\][^\n]*\n(.+)", content)
        if self.behaviour == "grounded" and first:
            pid, line = first.group(1), first.group(2)
            quote = " ".join(line.split()[:8])
            data = {"answer_status": "answered", "answer": "Fake grounded answer.", "citations": [{"passage_id": pid, "quote": quote}], "missing_facts": []}
        elif self.behaviour == "invented":
            data = {"answer_status": "answered", "answer": "The penalty is AED 99,999.", "citations": [{"passage_id": "NOPE#0001", "quote": "made up"}], "missing_facts": []}
        else:
            data = {"answer_status": "not_covered", "answer": "Not covered.", "citations": [], "missing_facts": []}
        usage = SimpleNamespace(input_tokens=int(len(content) / 4), output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(data))], usage=usage,
                               model=self.model_override or model, stop_reason="end_turn", _request_id="req_fake")
