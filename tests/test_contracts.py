"""Task 2 A-0: canonical contract schemas and golden fixtures (doc 16 r2). Tests t2c_01-14 (numbered apart from the WS A/B/C series, which already use 135-216). Synthetic only; no network.

Runs on the standard library (contracts/validate.py). Where `jsonschema` is installed, every verdict is cross-checked
against it, so the small validator can never be more lenient than the reference implementation."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "contracts"
FX = C / "fixtures"
sys.path.insert(0, str(C)); sys.path.insert(0, str(FX)); sys.path.insert(0, str(ROOT))

import validate as V  # noqa: E402
import build_schemas as BS  # noqa: E402
import build_fixtures as BF  # noqa: E402

try:
    import jsonschema  # optional cross-check (not needed by the public export)
except ImportError:
    jsonschema = None

INDEX = json.loads((C / "CONTRACTS_INDEX.json").read_text(encoding="utf-8"))["contracts"]
SCHEMAS = {name.split("/")[0].split(".", 1)[1]: json.loads((C / v["file"]).read_text(encoding="utf-8")) for name, v in INDEX.items()}
FIXTURES = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FX.glob("*.json"))}


def check(contract: str, payload) -> bool:
    """True if valid. Asserts that the stdlib validator and jsonschema (if present) agree."""
    ok = not V.errors(SCHEMAS[contract], payload)
    if jsonschema is not None:
        ref = jsonschema.Draft202012Validator(SCHEMAS[contract]).is_valid(payload)
        assert ok == ref, f"validator disagreement on {contract}: stdlib={ok} jsonschema={ref}"
    return ok


class Contracts(unittest.TestCase):
    def test_t2c_01_schemas_and_fixtures_are_exactly_what_the_builders_produce(self):
        for name, data in BS.build().items():
            self.assertEqual((C / name).read_bytes(), data, name)
        for name, obj in BF.build().items():
            self.assertEqual((FX / name).read_bytes(), BF.render(obj), name)
        self.assertEqual(set(FIXTURES), set(BF.build()))

    def test_t2c_02_index_lists_the_six_contracts_with_their_sha256(self):
        self.assertEqual(set(INDEX), {"herbiz.retrieval_result/1.0", "herbiz.decision_explanation/1.0", "herbiz.source_validity/1.2",
                                      "herbiz.audit_record/1.0", "herbiz.scenario/1.0", "herbiz.capability_declaration/1.0"})
        for name, v in INDEX.items():
            self.assertEqual(hashlib.sha256((C / v["file"]).read_bytes()).hexdigest(), v["sha256"], name)
            self.assertEqual(SCHEMAS[name.split("/")[0].split(".", 1)[1]]["properties"]["contract"]["const"], name)
        self.assertEqual({v["semantics_owner"] for k, v in INDEX.items() if "retrieval" in k or "decision" in k}, {"WS B"})
        self.assertEqual(INDEX["herbiz.source_validity/1.2"]["semantics_owner"], "WS C")

    def test_t2c_03_schemas_use_only_supported_keywords_and_are_valid_2020_12(self):
        def walk(s):
            if isinstance(s, dict):
                for k, v in s.items():
                    if k in ("properties",):
                        for sub in v.values():
                            yield from walk(sub)
                        continue
                    yield k
                    if k in ("items", "additionalProperties", "if", "then") and isinstance(v, dict):
                        yield from walk(v)
                    if k in ("allOf", "oneOf"):
                        for sub in v:
                            yield from walk(sub)
        for name, s in SCHEMAS.items():
            self.assertLessEqual(set(walk(s)), V.SUPPORTED | V.ANNOTATIONS, name)
            if jsonschema is not None:
                jsonschema.Draft202012Validator.check_schema(s)

    def test_t2c_04_every_golden_fixture_has_the_expected_verdict(self):
        self.assertGreaterEqual(len([f for f in FIXTURES if ".valid" in f]), 6)
        for c in SCHEMAS:
            self.assertTrue(any(f.startswith(c + ".valid") for f in FIXTURES), c)
            self.assertTrue(any(f.startswith(c + ".invalid") for f in FIXTURES), c)
        for f, x in FIXTURES.items():
            c = f.split(".")[0]
            self.assertEqual(check(c, x), ".valid" in f, f)

    def test_t2c_05_T2_D2_question_text_only_when_the_gate_allows(self):
        base = FIXTURES["audit_record.valid_allow.json"]
        self.assertTrue(check("audit_record", base))
        for action in ("warn", "block"):
            x = copy.deepcopy(base); x["request"]["gate"]["action"] = action
            self.assertFalse(check("audit_record", x), action)
            x["request"]["query_text"] = None
            if action == "warn":
                self.assertTrue(check("audit_record", x), "warn without text is fine")
        x = copy.deepcopy(base); x["request"]["gate"] = None
        self.assertFalse(check("audit_record", x), "text without any gate decision")
        x = copy.deepcopy(base); x["synthetic"] = False
        self.assertFalse(check("audit_record", x), "Task 2 records are synthetic only")

    def test_t2c_06_T2_D3_confidence_is_categorical(self):
        for f, path in (("decision_explanation.valid.json", ("confidence",)), ("audit_record.valid_allow.json", ("confidence",))):
            for bad in (0.5, 1, "high"):
                x = copy.deepcopy(FIXTURES[f]); x["confidence"]["numeric"] = bad
                self.assertFalse(check(f.split(".")[0], x), (f, bad))
            x = copy.deepcopy(FIXTURES[f]); x["confidence"]["level"] = "very high"
            self.assertFalse(check(f.split(".")[0], x))

    def test_t2c_07_no_approval_anywhere(self):
        for f in ("decision_explanation.valid.json", "audit_record.valid_allow.json"):
            x = copy.deepcopy(FIXTURES[f]); x["review"]["release_approved"] = True
            self.assertFalse(check(f.split(".")[0], x))
        x = copy.deepcopy(FIXTURES["source_validity.valid_conflict.json"]); x["release_approved"] = True
        self.assertFalse(check("source_validity", x))
        x = copy.deepcopy(FIXTURES["source_validity.valid_conflict.json"]); x["conflicts"][0]["precedence_known"] = True
        self.assertFalse(check("source_validity", x), "HerBiz explains conflicts; it never resolves them")
        x = copy.deepcopy(FIXTURES["source_validity.valid_conflict.json"]); x["conflicts"] = []
        self.assertFalse(check("source_validity", x), "status conflict needs a conflict record")

    def test_t2c_08_audit_records_never_carry_passage_text_and_blocked_answers_never_carry_retrieval(self):
        x = copy.deepcopy(FIXTURES["audit_record.valid_allow.json"]); x["retrieval"]["items"][0]["text"] = "passage"
        self.assertFalse(check("audit_record", x))
        self.assertTrue(check("retrieval_result", FIXTURES["retrieval_result.valid.json"]))      # internal payload may
        x = copy.deepcopy(FIXTURES["audit_record.valid_blocked.json"]); x["retrieval"] = copy.deepcopy(FIXTURES["audit_record.valid_allow.json"]["retrieval"])
        self.assertFalse(check("audit_record", x))
        x = copy.deepcopy(FIXTURES["audit_record.valid_allow.json"]); x["answer"]["execution_mode"] = "live_inference"
        self.assertFalse(check("audit_record", x), "no live inference in Task 2")
        x = copy.deepcopy(FIXTURES["audit_record.valid_allow.json"]); x["integrity"]["record_sha256"] = "abc"
        self.assertFalse(check("audit_record", x))
        x = copy.deepcopy(FIXTURES["audit_record.valid_allow.json"]); x["at"] = "2026-10-17T10:00:00Z"
        self.assertFalse(check("audit_record", x), "timestamps are Asia/Dubai (+04:00)")

    def test_t2c_09_scenarios_release_events_one_at_a_time(self):
        for sid in ("SC-1", "SC-2", "SC-3"):
            s = FIXTURES[f"scenario.valid_{sid}.json"]
            self.assertEqual(s["scenario_id"], sid)
            ns = [st["n"] for st in s["steps"]]
            self.assertEqual(ns, list(range(1, len(ns) + 1)))
            self.assertEqual([st["released_after"] for st in s["steps"]], [None] + ns[:-1])
        self.assertIn("conflict", FIXTURES["scenario.valid_SC-2.json"]["steps"][2]["expected"]["flags"])
        self.assertIn("deadline", FIXTURES["scenario.valid_SC-2.json"]["steps"][2]["expected"]["must_not"])
        self.assertIn("stale_source", FIXTURES["scenario.valid_SC-3.json"]["steps"][2]["expected"]["flags"])

    def test_t2c_10_capability_declaration_classes(self):
        d = FIXTURES["capability_declaration.valid.json"]
        self.assertEqual({c["class"] for c in d["capabilities"]},
                         {"deterministic", "recorded_model", "proxy_outputs", "live_inference", "tool_use", "simulated", "planned"})
        self.assertFalse(any(c["active"] for c in d["capabilities"] if c["class"] in ("live_inference", "planned")))
        x = copy.deepcopy(d); x["capabilities"][0]["class"] = ["deterministic", "simulated"]
        self.assertFalse(check("capability_declaration", x), "exactly one class per capability")

    def test_t2c_11_fixtures_are_synthetic_and_hold_no_personal_data_or_official_text(self):
        from compliance_agent.rag_c import policy_gate as PG
        def strings(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    yield k; yield from strings(v)
            elif isinstance(x, list):
                for v in x:
                    yield from strings(v)
            elif isinstance(x, str):
                yield x
        for f, x in FIXTURES.items():
            if "invalid_query_text" in f:
                continue
            for s in strings(x):
                self.assertNotEqual(PG.policy_gate(s)["action"], "block", (f, s[:40]))
                self.assertLess(len(s), 300, (f, "long string: official text is never a fixture"))
            for it in (x.get("items") or []):
                if "text" in it:
                    self.assertTrue(it["text"].startswith("SYNTHETIC FIXTURE"), f)

    def test_t2c_12_owner_facing_fixture_wording(self):
        forbidden = ("approved", "verified", "certified", "compliant", "endorsed", "guarantee")
        d = FIXTURES["decision_explanation.valid.json"]
        for field in ("reason", "state_chip", "label"):
            low = (d[field] or "").lower()
            self.assertFalse(any(w in low for w in forbidden), field)
            self.assertFalse(any(f" {w} " in f" {low} " for w in ("we", "our", "us")), field)

    def test_t2c_13_R_C1_current_official_url_status_and_embedded_validity(self):
        ok = FIXTURES["source_validity.valid_outdated.json"]
        self.assertEqual(ok["current_official_url_status"]["content_check"], "pending_founder_verification")
        x = copy.deepcopy(ok); x["current_official_url_status"] = None
        self.assertFalse(check("source_validity", x), "a link without its status")
        x = copy.deepcopy(FIXTURES["source_validity.valid_conflict.json"])
        x["current_official_url_status"] = copy.deepcopy(ok["current_official_url_status"])
        self.assertFalse(check("source_validity", x), "a status without a link")
        x = copy.deepcopy(ok); del x["current_official_url_status"]
        self.assertFalse(check("source_validity", x), "the field is required (nullable)")
        x = copy.deepcopy(ok); x["amendments"][0]["evidence_level"] = "listing_only"
        self.assertFalse(check("source_validity", x), "N-C1: WS C's six evidence levels only")
        # N-C2: the validity block embedded in audit records is the 1.2 schema itself (copied, so it must not drift)
        core = {k: v for k, v in SCHEMAS["source_validity"].items() if k not in V.ANNOTATIONS}
        embedded = SCHEMAS["audit_record"]["properties"]["sources"]["items"]["properties"]["validity"]["oneOf"][1]
        self.assertEqual(embedded, core)
        self.assertIn("pending_unverified_link", FIXTURES["scenario.valid_SC-3.json"]["steps"][2]["expected"]["flags"])

    def test_t2c_14_R_B1_engine_values_and_R_B2_named_obligation(self):
        d = FIXTURES["decision_explanation.valid.json"]
        self.assertIn(d["rule_status"], ("draft_unreviewed", "reviewed", "no_reviewed_rule", "blocked_source_conflict", "synthetic_test"))
        self.assertIn(d["label"], ("TEST RULE — not law", "Draft — not reviewed"))
        for sid in ("SC-1", "SC-2", "SC-3"):
            for st in FIXTURES[f"scenario.valid_{sid}.json"]["steps"]:
                if st["expected"]["state"] is not None:
                    self.assertIn("obligation_id", st["input"], (sid, st["n"]))
        self.assertTrue(all(st["expected"]["state"] is None for st in FIXTURES["scenario.valid_SC-2.json"]["steps"]))
        from compliance_agent.obligations import profile as PR          # WS B's own validator (read-only use)
        step3 = FIXTURES["scenario.valid_SC-1.json"]["steps"][2]["input"]
        fields = {k: v for k, v in step3.items() if k != "obligation_id"}
        self.assertEqual(PR.validate({"profile_id": "SYN-SC1", "synthetic": True, "fields": fields}).get("clarify"), [])


if __name__ == "__main__":
    unittest.main()
