"""Task 2 B-A: WS-B's read-only copy of WS-A's canonical schemas (t2-integration @ b4eb7bb) is byte-identical,
and WS-B's payloads are embedded unchanged in herbiz.audit_record/1.0. No schema is edited here."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "contracts" / "ws_a_canonical_b4eb7bb"
EXPECTED = {
    "retrieval_result_1.0.schema.json": "f878a0af5cab43095ed5ef1b587db2f36ea9fa3cd3ea9cf062cf14d32202f3a5",
    "decision_explanation_1.0.schema.json": "388e98545b88d19b6b3719cc94099efd07318fdedf4154158755694f013e1f7f",
    "audit_record_1.0.schema.json": "cc2aebeae9ff0ad54670c2d75e50cd68a6be3eab342c15a8c514d5100989e061",
    "scenario_1.0.schema.json": "4f445bea14520ae415bafd6f5c574010202c39db4c736698c3f5db7d8e502883",
    "capability_declaration_1.0.schema.json": "5bde1f9ed4814a253c2081c1c59094cca7429c53c103ee96bc5c5b1c72b0a50f",
    "CONTRACTS_INDEX.json": "237dfe2333044d6299992e1881a255d36a4ece88ec603e8622ff72dc2410b24f",
}


def load(name):
    return json.loads((COPY / name).read_text(encoding="utf-8"))


def bare(schema):
    s = copy.deepcopy(schema)
    for k in ("$id", "$schema", "title"):
        s.pop(k, None)
    return s


class ContractCopy(unittest.TestCase):
    def test_t2_ba_01_byte_identical_sha256(self):
        self.assertEqual(sorted(p.name for p in COPY.glob("*.json")), sorted(EXPECTED))
        for name, sha in EXPECTED.items():
            self.assertEqual(hashlib.sha256((COPY / name).read_bytes()).hexdigest(), sha, name)

    def test_t2_ba_02_retrieval_embedded_unchanged_except_text(self):
        rr = bare(load("retrieval_result_1.0.schema.json"))
        rr["properties"]["items"]["items"]["properties"].pop("text")      # audit records never carry official text
        emb = copy.deepcopy(load("audit_record_1.0.schema.json")["properties"]["retrieval"])
        self.assertEqual(emb["type"], ["object", "null"])                  # null for blocked answers (T2-D2)
        emb["type"] = "object"
        self.assertEqual(emb, rr)

    def test_t2_ba_03_decision_embedded_unchanged(self):
        self.assertEqual(load("audit_record_1.0.schema.json")["properties"]["decisions"]["items"],
                         bare(load("decision_explanation_1.0.schema.json")))

    def test_t2_ba_04_ws_b_never_live_and_confidence_never_numeric(self):
        de = load("decision_explanation_1.0.schema.json")["properties"]
        self.assertEqual(de["confidence"]["properties"]["numeric"], {"const": None})
        self.assertEqual(de["review"]["properties"]["release_approved"], {"const": False})
        self.assertNotIn("live_model", de["execution_mode"]["enum"])


if __name__ == "__main__":
    unittest.main()
