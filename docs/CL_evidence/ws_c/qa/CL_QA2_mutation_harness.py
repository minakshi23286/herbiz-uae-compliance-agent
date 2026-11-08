import shutil, subprocess, sys, os
from pathlib import Path
S = Path(__file__).parent; BASE = S / "base2"
T = "tests/test_ws_c_amendment_lifecycle.py"
MUT = {
 "M1_monitor_skips_listing_proposals": ("compliance_agent/rag_c/monitor.py",
    "    for p in prop[\"proposals\"]:\n        proposals.append(p)", "    for p in []:\n        proposals.append(p)"),
 "M2_review_source_no_supersede": ("compliance_agent/engine.py",
    "                if old:\n                    self.s.db.execute(\"UPDATE source_versions SET status='superseded'", "                if False:\n                    self.s.db.execute(\"UPDATE source_versions SET status='superseded'"),
 "M3_answer_label_ignores_approval": ("compliance_agent/rag_c/interface.py",
    "        if not ver[\"approved\"]:", "        if False:"),
 "M4_amended_article_identical_textually": (T,
    "Threshold shall be AED 400,000 (SYNTHETIC).\\n\" \\\n          \"2. Further", "Threshold shall be AED 375,000 (SYNTHETIC).\\n\" \\\n          \"2. Further"),
 "M5_monitor_flags_all_inscope_articles": ("compliance_agent/rag_c/monitor.py",
    "            alert(kind, it, f\"substantive change in {what}\" + (\" (in scope)\" if in_scope else \"\"), touched)",
    "            touched = sorted(set(touched) | {f\"{src}|{a}\" for a in (it.get('in_scope_articles') or [])})\n            alert(kind, it, f\"substantive change in {what}\" + (\" (in scope)\" if in_scope else \"\"), touched)"),
 "M6_validity_drops_outdated_issue": ("compliance_agent/rag_c/validity.py",
    "        for kind, arts in sorted(by_kind.items()):", "        for kind, arts in []:"),
 "M7_compare_everything_substantive_except_none": ("compliance_agent/kb.py",
    "            elif S.normalize(a[k]) == S.normalize(b[k]):\n                continue", "            elif S.normalize(a[k]) == S.normalize(b[k]):\n                rows.append({'unit': k, 'change': 'substantive', 'old': '', 'new': ''}); continue"),
 "M8_test_v1_left_approved_in_register": (T,
    "            if v[\"version_id\"] == \"SYN-ER@v1\":\n                v[\"kb_status\"] = \"superseded\"", "            if False:\n                v[\"kb_status\"] = \"superseded\""),
 "M9_test_no_db_review_only_register": (T,
    "        self.assertEqual(e.review_source(\"SYN-ER@v2\", \"approve\", *REVIEWER)[\"status\"], \"approved\")\n        e.s.close()\n        self.assertEqual((self.status(\"SYN-ER@v1\"), self.status(\"SYN-ER@v2\")), (\"superseded\", \"approved\"))",
    "        e.s.close()"),
 "M11_stage4_no_claims_registered": (T,
    "        r[\"claims\"].append({\"claim_id\": \"SYN-CL-THRESHOLD-V2\"", "        r[\"claims\"].append if False else None\n        dict({\"claim_id\": \"SYN-CL-THRESHOLD-V2\""),
 "M10_amendment_footnote_absent": (T,
    "\\n\\n1 Article amended as per Cabinet Decision No. 999 of 2027.\\n\"", "\\n\""),
}
which = sys.argv[1:] or list(MUT)
for name in which:
    f, old, new = MUT[name]
    d = S / "mut" / name
    import time; d = S / "mut2" / f"{name}_{int(time.time())}"
    shutil.copytree(BASE, d, ignore=shutil.ignore_patterns("__pycache__"))
    p = d / f; src = p.read_text()
    assert src.count(old) == 1, (name, src.count(old))
    p.write_text(src.replace(old, new))
    r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_ws_c_amendment_lifecycle"], cwd=d, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    tail = [l for l in r.stderr.splitlines() if "Error" in l or "assert" in l.lower() or l.startswith("  File") and "lifecycle" in l]
    print(f"{name}: {'CAUGHT (test fails)' if r.returncode else 'NOT CAUGHT (test passes)'}")
    for l in tail[-4:]: print("    ", l.strip()[:220])
