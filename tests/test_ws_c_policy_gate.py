"""Personal-data intake gate (D-088), offline. Tests 197-212: permitted business questions, personal-data submissions,
bypass attempts, error handling, ablation (the KB drives the decision) and the no-raw-text rule. Synthetic data only."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.rag_c import policy_gate as G  # noqa: E402


def _iban(bban19: str) -> str:
    """Build a check-digit-valid synthetic AE IBAN (23 characters: AE + 2 check digits + 3 bank + 16 account; not a real account)."""
    for cd in range(100):
        cand = f"AE{cd:02d}{bban19}"
        if G._iban_ok(cand):
            return cand
    raise AssertionError


IBAN = _iban("033" + "1234567890123456")              # 3 + 16 = 19 digits, synthetic
POSITIVES = {                                           # synthetic values only
    "emirates_id": ["My Emirates ID is 784-1990-1234567-1", "ID 784 1990 1234567 1 for the VAT form", "784199012345671",
                    "Emirates ID ٧٨٤١٩٩٠١٢٣٤٥٦٧١", "７８４１９９０１２３４５６７１", "7 8 4 1 9 9 0 1 2 3 4 5 6 7 1",
                    "784​1990​1234567​1", "784-1990-\n1234567-1"],
    "iban_ae": [f"Pay into {IBAN}", " ".join(IBAN[i:i + 4] for i in range(0, len(IBAN), 4)), IBAN.lower()],
    "uae_phone": ["Call her on +971 50 123 4567", "0501234567", "00971501234567", "+971-4-123-4567", "050 123 4567", "971501234567",
                  "(+971) 50-123-4567"],
    "email": ["Send it to fatima.example@mail.test", "client: amal_test@example.org"],
    "passport": ["passport no. N1234567", "Passport number: AB123456"],
}
HARD_NEGATIVES = [
    "My TRN is 100123456700003. Do I file quarterly?", "TRN 100-1234-5678-9003 on the invoice", "Is AED 375,000 the threshold?",
    "Sales of AED 1,000,000 in 2026", "Invoice INV-2026-000123 dated 31/12/2025", "Licence number 1234567",
    "Return for the period 01/01/2026 to 31/03/2026", "Article 13 and Article 19 of the Decree-Law", "Cabinet Decision No. 153 of 2025",
    "I sold 784 cakes this month", "Ministerial Decision No. 131 of 2026 extends SBR to 2029", "15 digit reference 123456789012345",
    "Penalty of AED 10,000 for late registration", "Tax period ending 2026-12-31", "Invoice total 5,250.00 AED incl. 5% VAT",
    "Customs code 0402.10", "Is 5% VAT due on AED 50,000?",
    "Invoice dated 05/01/2026 14:30, do I charge VAT?", "On 05.01.2026 12 cakes sold",
]


def _kb_copy(mutate=None) -> Path:
    kb = json.loads(G.KB_PATH.read_text(encoding="utf-8"))
    if mutate:
        mutate(kb)
    p = Path(tempfile.mkdtemp()) / "kb.json"
    p.write_text(json.dumps(kb), encoding="utf-8")
    return p


def _clean_questions() -> list[str]:
    qs = []
    for name in ("CL_llm_eval_questions.json", "CL_llm_eval_unseen_v1.json", "CL_llm_eval_unseen_v2.json", "CL_llm_eval_unseen_v3.json"):
        for q in json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))["questions"]:
            qs.append(q.get("text") or q.get("question"))
    from compliance_agent import ask
    qs += [what for _, _, what in ask.DEMO_EXAMPLES]
    return qs


class PolicyGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = G.load()

    def test_197_kb_loads_with_required_controls_and_resolvable_clauses(self):
        self.assertTrue({"CTRL-PD-MINIMISE", "CTRL-NO-RAW-LOG", "CTRL-FAIL-CLOSED"} <= set(self.kb["controls"]))
        for c in self.kb["controls"].values():
            for cl in c["clause_ids"]:
                self.assertIn(cl, self.kb["clauses"])
        for cl in self.kb["clauses"].values():                      # summaries, never official text
            self.assertTrue(cl["summary"].startswith(("HerBiz summary, not official text", "HerBiz internal rule")))
        self.assertEqual(len(self.kb["sha256"]), 64)

    def test_198_permitted_business_questions_are_never_blocked(self):
        qs = _clean_questions()
        self.assertGreaterEqual(len(qs), 120)
        # one existing adversarial fixture question contains a (synthetic) Emirates ID: it must be blocked, not allowed
        with_pd = [q for q in qs if "784-1990-1234567-1" in q]
        self.assertEqual(len(with_pd), 1)
        self.assertEqual(G.policy_gate(with_pd[0], self.kb)["action"], "block")
        blocked = [q for q in qs if q not in with_pd and G.policy_gate(q, self.kb)["action"] == "block"]
        self.assertEqual(blocked, [])

    def test_199_hard_negatives_are_allowed(self):
        self.assertGreaterEqual(len(HARD_NEGATIVES), 15)
        for q in HARD_NEGATIVES:
            self.assertEqual(G.policy_gate(q, self.kb)["action"], "allow", q)

    def test_200_personal_data_is_blocked_with_kb_clauses(self):
        for det, items in POSITIVES.items():
            for q in items:
                d = G.policy_gate(q, self.kb)
                self.assertEqual(d["action"], "block", (det, q))
                self.assertFalse(d["process"])
                self.assertIn(det, d["detector_ids"], q)
                self.assertIn("PDPL-ART5", d["clause_ids"])
                self.assertIn("CTRL-PD-MINIMISE", d["control_ids"])

    def test_201_bypass_attempts_are_caught(self):
        for q in ("784​1990​1234567​1", "٧٨٤١٩٩٠١٢٣٤٥٦٧١", "７８４１９９０１２３４５６７１", "7 8 4 1 9 9 0 1 2 3 4 5 6 7 1",
                  "784.1990.1234567.1", "784/1990/1234567/1", "784_1990_1234567_1", "(784) 1990-1234567-1", IBAN.lower(),
                  "+971­50­1234567"):
            self.assertEqual(G.policy_gate(q, self.kb)["action"], "block", repr(q))

    def test_202_invalid_iban_check_digits_are_not_flagged(self):
        bad = IBAN[:2] + f"{(int(IBAN[2:4]) + 1) % 100:02d}" + IBAN[4:]
        self.assertEqual(G.policy_gate(f"ref {bad}", self.kb)["action"], "allow")

    def test_203_no_raw_text_or_matched_value_in_any_output(self):
        for items in POSITIVES.values():
            for q in items:
                d = G.policy_gate(q, self.kb)
                blob = json.dumps(d, ensure_ascii=False)
                self.assertNotIn(q, blob)
                for frag in ("1234567", "4567", "fatima", "amal_test", IBAN[-8:]):
                    if frag.lower() in q.lower():
                        self.assertNotIn(frag, blob.lower() if frag.islower() else blob)
                self.assertEqual(set(d["log_record"]), {"action", "control_ids", "detector_ids", "clause_ids", "kb_version", "kb_sha256"})

    def test_204_sensitive_words_warn_but_never_block(self):
        d = G.policy_gate("Is VAT zero-rated on medical services for my clinic?", self.kb)
        self.assertEqual((d["action"], d["process"]), ("warn", True))
        self.assertIn("CTRL-SENSITIVE-WARN", d["control_ids"])

    def test_205_missing_or_corrupt_kb_fails_closed(self):
        missing = G.policy_gate("Is AED 375,000 the threshold?", kb_path=Path(tempfile.mkdtemp()) / "nope.json")
        self.assertEqual((missing["action"], missing["control_ids"]), ("block", ["CTRL-FAIL-CLOSED"]))
        p = Path(tempfile.mkdtemp()) / "bad.json"; p.write_text("{not json", encoding="utf-8")
        self.assertEqual(G.policy_gate("hello", kb_path=p)["action"], "block")

    def test_206_kb_without_a_required_control_fails_closed(self):
        p = _kb_copy(lambda kb: kb.update(controls=[c for c in kb["controls"] if c["control_id"] != "CTRL-PD-MINIMISE"]))
        with self.assertRaises(G.KBError):
            G.load(p)
        self.assertEqual(G.policy_gate("Is AED 375,000 the threshold?", kb_path=p)["action"], "block")

    def test_207_unknown_detector_or_clause_fails_closed(self):
        for mut in (lambda kb: kb["controls"][0]["detector_ids"].append("nope"), lambda kb: kb["controls"][0]["clause_ids"].append("NOPE")):
            p = _kb_copy(mut)
            self.assertEqual(G.policy_gate("hello", kb_path=p)["action"], "block")

    def test_208_non_string_or_oversized_input_fails_closed(self):
        for bad in (None, 12345, b"bytes", "x" * (G.MAX_CHARS + 1)):
            d = G.policy_gate(bad, self.kb)
            self.assertEqual((d["action"], d["control_ids"]), ("block", ["CTRL-FAIL-CLOSED"]))

    def test_209_detector_crash_fails_closed(self):
        orig = G.DETECTORS["email"]
        G.DETECTORS["email"] = lambda t: 1 / 0
        try:
            self.assertEqual(G.policy_gate("hello", self.kb)["action"], "block")
        finally:
            G.DETECTORS["email"] = orig

    def test_210_ablation_the_kb_drives_the_decision(self):
        """Remove the Emirates ID detector from the KB control: the same input flips from block to allow, while other
        detectors still block. This shows the decision comes from the policy KB, not from hard-coded logic."""
        q = "My Emirates ID is 784-1990-1234567-1"
        self.assertEqual(G.policy_gate(q, self.kb)["action"], "block")
        def drop(kb):
            next(c for c in kb["controls"] if c["control_id"] == "CTRL-PD-MINIMISE")["detector_ids"].remove("emirates_id")
        ablated = G.load(_kb_copy(drop))
        self.assertEqual(G.policy_gate(q, ablated)["action"], "allow")
        self.assertEqual(G.policy_gate("mail fatima.example@mail.test", ablated)["action"], "block")

    def test_211_owner_message_comes_from_the_kb_and_makes_no_legal_claim(self):
        d = G.policy_gate("0501234567", self.kb)
        self.assertEqual(d["owner_message"], self.kb["controls"]["CTRL-PD-MINIMISE"]["owner_message"])
        self.assertIn("not a legal assessment", d["owner_message"])
        for word in ("comply", "compliant", "required by law", "the law requires"):
            self.assertNotIn(word, d["owner_message"].lower())

    def test_213_unicode_dashes_and_other_script_digits_are_caught(self):
        for q in ("784\u20131990\u20131234567\u20131", "784\u20141990\u20141234567\u20141", "784\u22121990\u22121234567\u22121",
                  "+971\u201350\u2013123\u20134567", "\u096d\u096e\u096a\u0967\u096f\u096f\u0966\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u0967"):
            self.assertEqual(G.policy_gate(q, self.kb)["action"], "block", repr(q))

    def test_214_malformed_kb_shapes_fail_closed(self):
        for content in ("[]", '{"_meta": {}, "clauses": [], "controls": ["x"]}', '{"clauses": [], "controls": []}', "null"):
            p = Path(tempfile.mkdtemp()) / "kb.json"; p.write_text(content, encoding="utf-8")
            with self.assertRaises(G.KBError):
                G.load(p)
            self.assertEqual(G.policy_gate("hello", kb_path=p)["action"], "block")
        for bad_kb in ({}, {"controls": {"X": {}}}, {"controls": {"CTRL-PD-MINIMISE": {"detector_ids": ["email"]}}}):
            self.assertEqual(G.policy_gate("mail a@b.co", kb=bad_kb)["action"], "block")

    def test_215_block_or_warn_control_needs_an_owner_message(self):
        def empty(kb):
            next(c for c in kb["controls"] if c["control_id"] == "CTRL-SENSITIVE-WARN")["owner_message"] = ""
        with self.assertRaises(G.KBError):
            G.load(_kb_copy(empty))

    def test_216_changing_a_control_action_in_the_kb_changes_the_decision(self):
        def to_warn(kb):
            next(c for c in kb["controls"] if c["control_id"] == "CTRL-PD-MINIMISE")["action"] = "warn"
        self.assertEqual(G.policy_gate("0501234567", G.load(_kb_copy(to_warn)))["action"], "warn")

    def test_212_loaded_kb_is_a_copy(self):
        kb = G.load()
        kb["controls"]["CTRL-PD-MINIMISE"]["detector_ids"].clear()
        self.assertIn("emirates_id", G.load()["controls"]["CTRL-PD-MINIMISE"]["detector_ids"])


if __name__ == "__main__":
    unittest.main()
