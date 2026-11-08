"""Task 2 A-7: build the synthetic, redistribution-safe VAT-warning test fixture (founder approval 18 Oct, D-098; proposal
docs/360/export/CL_HERBIZ360_SYNTHETIC_VAT_WARNING_PROPOSAL.md).

    python3 experiments/ws_a/CL_build_synthetic_vat_fixture.py [--check]

Writes tests/fixtures/CL_synthetic_vat_answers.json in the record shape Asker accepts through `recorded_file`. It holds NO
legal text: a fixed synthetic answer label, no quotes, no citations, no passages; only source ids and article locators
(metadata), chosen so each case exercises one branch of the warning logic. It is never placed where the demo loads
recorded answers, so the demo can never show it as a recorded model answer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "CL_synthetic_vat_answers.json"
LABEL = "SYNTHETIC TEST ANSWER — written for a test, not a model output and not a statement of the law."


def loc(src: str, art) -> dict:
    return {"passage_id": f"SYNTHETIC-{src}-{art}", "source_id": src, "locator": f"Article {art}", "source_status": "synthetic",
            "added_by": "synthetic_fixture"}


CASES = {   # qid: (answer_status, passages seen, quote check passed, what the case exercises)
    "Q35": ("answered", [loc("FTA-VAT-DL8", 17)], True, "primary provisions DL8 Art 21, ER Art 14 and ER Art 8 absent -> incomplete, named"),
    "U22": ("declined", [], True, "declined -> not_applicable; tax-agent box"),
    "U10": ("answered", [loc("FTA-VAT-DL8", 13), loc("FTA-VAT-ER", 7), loc("FTA-VAT-DL8", 17), loc("FTA-VAT-ER", 8)], False,
            "quote check failed -> incomplete (unreliable-quote message)"),
    "Q13": ("answered", [loc("FTA-VAT-DL8", 13), loc("FTA-VAT-ER", 7)], True,
            "all primary provisions present -> complete_for_map, still not checked by a qualified tax professional (control)"),
}


# rc3 item 1 (founder/CTO 19 Oct): cited articles whose source status must withhold a recorded answer. Metadata only: the
# "passage" carries a source id and an article locator, never text; the quote is a fixed synthetic label.
CITING = {   # qid: (answer_status, (source_id, article), what the case exercises)
    "SYN-79BIS": ("answered", ("FTA-VAT-DL8", "79 (bis)"), "article record superseded -> answer withheld (as V24)"),
    "SYN-ART48": ("answered", ("FTA-VAT-DL8", "48"), "article record outdated (amended) -> answer withheld"),
    "SYN-ER14": ("answered", ("FTA-VAT-ER", "14"), "article record conflict -> answer withheld and escalated"),
    "SYN-ART13": ("answered", ("FTA-VAT-DL8", "13"), "only the whole-source record; article not listed as amended -> shown with a note"),
}
QUOTE = "SYNTHETIC QUOTE — not official text"


def build() -> dict:
    answers = {}
    for n, (qid, (status, seen, ok, why)) in enumerate(CASES.items(), 1):
        answers[qid] = {"call_id": -n, "run_id": "SYNTHETIC-FIXTURE", "at": "2026-10-18T00:00:00+04:00", "question_id": qid,
                        "model_returned": "none (synthetic fixture)", "retrieved_json": json.dumps(seen),
                        "parsed_json": json.dumps({"answer_status": status, "answer": LABEL, "citations": [], "missing_facts": []}),
                        "checks_json": json.dumps({"supported": ok}), "passages": {}, "case": why}
    for n, (qid, (status, (src, art), why)) in enumerate(CITING.items(), len(CASES) + 1):
        pid = f"{src}:SYNTHETIC-{art}".replace(" ", "")        # same "SOURCE:id" form as real passage ids
        answers[qid] = {"call_id": -n, "run_id": "SYNTHETIC-FIXTURE", "at": "2026-10-18T00:00:00+04:00", "question_id": qid,
                        "model_returned": "none (synthetic fixture)", "retrieved_json": json.dumps([loc(src, art)]),
                        "parsed_json": json.dumps({"answer_status": status, "answer": LABEL, "missing_facts": [],
                                                   "citations": [{"passage_id": pid, "quote": QUOTE}]}),
                        "checks_json": json.dumps({"supported": True}), "case": why,
                        "passages": {pid: {"passage_id": pid, "source_id": src, "locator": f"Article {art}", "url": "", "text": ""}}}
    return {"_meta": {"title": "Synthetic VAT-warning test fixture (A-7; D-098)", "synthetic": True,
                      "contains": "question ids, a fixed synthetic answer label, source ids and article locators only",
                      "excludes": "official legal text, official quotes, model outputs, personal data (rc3 cases carry a fixed synthetic quote label)",
                      "use": "tests and the --synthetic-answers scenario option only; never loaded by the demo"},
            "answers": answers}


def render() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    if ap.parse_args(argv).check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == render()
        print("OK" if ok else "fixture out of date")
        return 0 if ok else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
