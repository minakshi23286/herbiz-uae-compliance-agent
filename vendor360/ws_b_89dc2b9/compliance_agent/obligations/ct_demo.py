"""Two-persona corporate-tax DEMONSTRATION layer (founder decision D-064, T-040 #5). No rules, no decisions.

For WS-C's fictional persona "Amal" (variants A and B) only, each corporate-tax item gets a clearly labelled demo block:
the profile questions with the persona's answers, the document checklist, and possible workflow steps. The engine
state stays `blocked_pending_legal_validation`. Eligibility, relief, applicability outcomes and due dates are WITHHELD
(D-062: fail closed for every unreviewed legal rule). Source citations and uncertainty come from WS-C's sources360
contract 0.1, read from a pinned commit in a separate process (C's working tree is never used).
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from . import engine as E, profile as PR
from .validity import C_REPO

SOURCES360_COMMIT = "aa50dd4"   # ws-c-source-intelligence, sources360 contract 0.2 (short wording, citation_chip)
DEMO_LABEL = "Demo scenario — fictional business."
DEMO_PROFILES = ("SYN-AMAL-A", "SYN-AMAL-B")   # WS-C persona variants; nothing else gets a CT demo block
CT_TO_C = {"C360-07": "CT-REG-JURIDICAL", "C360-08": "CT-REG-NATURAL", "C360-10": "CT-RETURN", "C360-11": "CT-SBR",
           "C360-14": "ACC-RECORDS"}
WITHHELD = ["whether this applies to the business", "eligibility or relief outcome", "due dates", "filing instructions"]
WITHHELD_WHY = "Not shown: a qualified reviewer has not yet checked the corporate-tax rules."
STEPS = ["Answer the profile questions above.",
         "Gather the documents in the checklist.",
         "Ask an FTA-registered tax agent whether and when this item applies to the business.",
         "Only after a professional confirms it: the owner acts in EmaraTax. HerBiz does not file or pay anything."]

_LABEL_SCRIPT = r"""
import json, sys
from compliance_agent.rag_c import sources360 as S
ids, as_of = json.loads(sys.argv[1]), sys.argv[2]
d = S.load()
print(json.dumps({i: S.obligation_label(d, i, as_of, profile_synthetic=True) for i in ids}))
"""


def load_c_labels(as_of: str, commit: str = SOURCES360_COMMIT, c_repo: str | Path = C_REPO) -> dict:
    """{'available', 'origin', 'error', 'labels': {C id: label}}. Fails closed: no labels, nothing invented."""
    tmp = Path(tempfile.mkdtemp(prefix="ws_b_c_s360_"))
    try:
        tar = subprocess.run(["git", "-C", str(c_repo), "archive", commit, "compliance_agent", "knowledge_base"],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(tmp, filter="data")
        out = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.');" + _LABEL_SCRIPT,
                              json.dumps(sorted(set(CT_TO_C.values()))), as_of],
                             cwd=tmp, capture_output=True, check=True, text=True, timeout=60).stdout
        labels = json.loads(out)
        if any(l.get("release_approved") is not False for l in labels.values()):
            raise ValueError("a WS-C label is not marked release_approved: false")
        return {"available": True, "origin": f"{c_repo}@{commit}", "error": None, "labels": labels}
    except Exception as e:
        return {"available": False, "origin": f"{c_repo}@{commit}", "error": f"{type(e).__name__}: {e}"[:300], "labels": {}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def demo_block(ob: dict, result: dict, profile: dict, facts: dict, c: dict) -> dict:
    lab = c["labels"].get(CT_TO_C.get(ob["id"], ""), None)
    return {
        "demo_label": DEMO_LABEL, "kind": "simulated_example", "validated_guidance": False, "release_approved": False,
        "persona": profile["persona"], "engine_state": result["state"],
        "profile_walkthrough": [{"fact": f, "question": PR.question(f), "demo_answer": facts.get(f, "not given (would be asked)")}
                                for f in ob.get("facts_needed", [])],
        "documents": result["documents"],
        "possible_workflow_steps": STEPS,
        "withheld": WITHHELD, "withheld_why": WITHHELD_WHY,
        "professional_review": ob.get("professional_review", []),
        "source_label": ({k: lab[k] for k in ("obligation_id", "user_wording", "uncertainty", "citations", "open_gaps", "reviewer_needed",
                                                "release_approved", "contract") if k in lab}
                         if lab and lab.get("shown") else {"available": False, "user_wording": "Source details unavailable; nothing is shown in their place."}),
    }


def assess_demo(profile: dict, sv, as_of, c_labels: dict) -> dict:
    """Owner-view (fail-closed) report plus a labelled CT demo block for the two WS-C persona variants only."""
    if profile.get("profile_id") not in DEMO_PROFILES or profile.get("synthetic") is not True:
        raise ValueError("the corporate-tax demo is limited to WS-C's fictional persona variants " + ", ".join(DEMO_PROFILES))
    rep = E.assess(profile, sv, as_of, E.DEFAULT_POLICY)
    facts = PR.validate(profile)["facts"]
    cat = {ob["id"]: ob for ob in E.load_catalogues()}
    for r in rep["obligations"]:
        if r["domain"] == "corporate_tax":
            assert r["state"] == "blocked_pending_legal_validation"   # D-064: never relaxed by the demo layer
            r["demo_scenario"] = demo_block(cat[r["id"]], r, profile, facts, c_labels)
    rep["demo_scenario_label"] = DEMO_LABEL
    return rep


def demo_wording_violations(rep: dict) -> list[str]:
    texts = [DEMO_LABEL, WITHHELD_WHY, *STEPS]
    for r in rep["obligations"]:
        d = r.get("demo_scenario")
        if d:
            texts += [d["source_label"].get("user_wording", ""), *(w["question"] for w in d["profile_walkthrough"])]
    return E.wording_violations(rep) + [f"{p!r} in: {t}" for t in texts for p in E.FORBIDDEN if p in t.lower()]
