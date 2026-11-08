import json, sys, copy
from pathlib import Path
from collections import Counter
I = Path(sys.argv[1]); B = I / "B"; sys.path.insert(0, str(B))
from compliance_agent.llm_lab import classifier_c1p as K, pipeline_c1p as PP, source_validity_c as SV
from compliance_agent.llm_lab.retrieve import connect_ro
C = I / "CL_compliance_agent_app_ws_c"
db = B / "data" / "CL_ws_b_exact_copy.sqlite3"
qs = json.loads((B / "fixtures" / "CL_llm_eval_unseen_v8.json").read_text())["questions"]
rec = json.loads((B / "docs" / "CL_evidence" / "ws_b" / "CL_v8_proxy_classifier_outputs.json").read_text())
rec = rec.get("outputs", rec)
base = json.loads((C / "knowledge_base" / "CL_source_validity.json").read_text())
def world(name, mutate):
    v = copy.deepcopy(base); mutate(v)
    p = I / f"export_{name}.json"; p.write_text(json.dumps(v))
    sv = SV.load(db, c_root=C, export=p, today="2026-10-17")
    con = connect_ro(db)
    rows = []
    for q in qs:
        r = PP.retrieve(con, q["text"], K.parse(rec[q["id"]]) if q["id"] in rec else None, sv)
        rows.append({"id": q["id"], "retrieval": r.get("retrieval_status"), "verified": r.get("retrieval_verified"),
                     "source_approved": r.get("source_approved"), "certifiable": r.get("answer_certifiable"),
                     "issue_kinds": r.get("validity_issue_kinds") or (r.get("validity_label") or {}).get("validity_issue_kinds"),
                     "blockers": sorted({b["reason"] for b in (r.get("source_label") or {}).get("blockers", [])}), "provs": sorted({b.get("provision","") for b in (r.get("source_label") or {}).get("blockers", [])})[:6], "note": (r.get("user_note") or r.get("certification_note") or "")[:140]})
    out = {"world": name, "available": sv.available, "error": sv.error, "certifiable": sum(bool(x["certifiable"]) for x in rows),
           "verified": sum(bool(x["verified"]) for x in rows), "rows": rows}
    print(name, "available", sv.available, "| verified", out["verified"], "| certifiable", out["certifiable"], sv.error or "")
    return out
def approve_all(v):
    for x in v["versions"]: x["approved"] = True
def approve_all_and_change_er7(v):
    approve_all(v)
    v["issues"].append({"id": "monitor:changed_substantive_in_scope:2026-10-18:SYNTHETIC", "kind": "source_changed", "version_id": "FTA-VAT-ER@v3",
                        "provisions": ["FTA-VAT-ER|7"], "message": "SYNTHETIC unreviewed change to ER Art. 7 (integration test)"})
def current_text(v):
    approve_all(v)
    for x in v["versions"]: x["outdated"] = False
    v["issues"] = [i for i in v["issues"] if i["kind"] not in ("outdated", "future_text")]
def current_text_plus_change(v):
    current_text(v)
    prov = sys.argv[2] if len(sys.argv) > 2 else "FTA-VAT-DL8|13"
    v["issues"].append({"id": "monitor:changed_substantive_in_scope:SYNTHETIC", "kind": "source_changed", "version_id": None,
                        "provisions": [prov], "message": "SYNTHETIC unreviewed change (integration test)"})
res = [world("as_is", lambda v: None), world("all_approved", approve_all), world("all_approved_plus_unreviewed_change_ER7", approve_all_and_change_er7), world("approved_and_current_text", current_text), world("approved_current_plus_unreviewed_change", current_text_plus_change)]
(I / "whatif_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
a = {x["id"]: x for x in res[1]["rows"]}; c = {x["id"]: x for x in res[2]["rows"]}
print("certifiable when all approved:", [k for k, x in a.items() if x["certifiable"]])
print("...of those, blocked by the unreviewed ER Art. 7 change:", [k for k, x in a.items() if x["certifiable"] and not c[k]["certifiable"]])
print("why not certifiable (verified answers, all approved):", Counter(tuple(x["blockers"]) for x in a.values() if x["verified"] and not x["certifiable"]))

d = {x["id"]: x for x in res[3]["rows"]}; e = {x["id"]: x for x in res[4]["rows"]}
print("certifiable with approved + current text:", [k for k, x in d.items() if x["certifiable"]])
print("still blocked there (why):", {k: x["blockers"] for k, x in d.items() if x["verified"] and not x["certifiable"]})
print("blocked again by the unreviewed change:", [k for k, x in d.items() if x["certifiable"] and not e[k]["certifiable"]], {k: e[k]["blockers"] for k, x in d.items() if x["certifiable"] and not e[k]["certifiable"]})
print("out-of-scope certified in any world:", sum(1 for w in res for x in w["rows"] if x["certifiable"] and x["retrieval"] == "out_of_scope"))
