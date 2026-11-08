"""Owner "Ask a question" panel — DEMO MODE: recorded answers only, no live AI, no network, no spend.

Answers are replayed from the experiment ledger (data/CL_llm_experiment.sqlite3, read-only): the latest successful Sonnet
answer for each development question whose text matches the owner's question exactly (case and spacing ignored).
Anything else gets the most relevant official passages (offline retrieval) and an honest "no recorded answer".

Without the ledger (the history-free submission export), answers come from RECORDED_FILE when it is present: the same
ledger rows and cited passages, exported by experiments/ws_a/CL_export_recorded_answers.py. No file -> no recorded answers.

Every answer passes an incompleteness guard: the topic's primary provisions (llm_lab.concepts.INTENT_PROVISIONS) must
have been among the passages the model saw. Nothing is ever labelled verified; no qualified tax reviewer has checked it.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .llm_lab.concepts import INTENT_PROVISIONS, intents

ROOT = Path(__file__).resolve().parents[1]
RECORDED_FILE = ROOT / "fixtures" / "mvp360" / "CL_recorded_vat_answers.json"
QUESTION_FILES = ["fixtures/CL_llm_eval_questions.json", "fixtures/CL_llm_eval_unseen_v1.json", "fixtures/CL_llm_eval_unseen_v2.json"]

STATUS_PLAIN = {
    "answered": "Answer from the official texts",
    "needs_facts": "I need a few facts first",
    "not_covered": "Not covered by the texts I have",
    "declined": "I can't help with that",
}

# Hackathon demo flow (Workstream A): controlled scenarios with recorded answers. Fictional people.
DEMO_EXAMPLES = [
    ("Q13", "Fatima, bridal henna", "Crossed the limit — from when?"),
    ("U10", "Aisha, home baker", "An amount with no period"),
    ("Q35", "Layla, cupcakes", "Cancel a voluntary registration"),
    ("U14", "Mariam, henna + a flat", "Does rent count?"),
    ("U18", "Huda, home food", "A licensing question"),
    ("U22", "Noura, beauty", "Split sales with my sister"),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def _words(s: str) -> set[str]:
    return {w for w in _norm(s).split() if len(w) > 2}


def _art(locator: str) -> str | None:
    m = re.match(r"Article (\d+(?: \(bis\))?)", locator or "")
    return m.group(1) if m else None


SOURCE_PLAIN = {"FTA-VAT-DL8": "VAT Decree-Law No. 8 of 2017", "FTA-VAT-ER": "VAT Executive Regulation",
                "FTA-VAT-REG-PAGE": "FTA web page 'Registration for VAT'"}


def provision_name(src: str, art) -> str:
    return SOURCE_PLAIN.get(src, src) + (f", Article {art}" if art is not None else "")


def guard(question: str, seen: list[dict], status: str) -> dict:
    """Incompleteness guard. level: complete_for_map | incomplete | unchecked | not_applicable."""
    if status in ("declined", "not_covered"):
        return {"level": "not_applicable", "intents": [], "missing": [],
                "message": "No legal answer was given, so there is nothing to check for completeness."}
    its, ambiguous = intents(question)
    if not its:
        return {"level": "unchecked", "intents": [], "missing": [],
                "message": "This topic is outside the map of provisions I can check, so this may be incomplete."}
    have = {(p["source_id"], _art(p["locator"])) for p in seen}
    have_page = any(p["source_id"] == "FTA-VAT-REG-PAGE" for p in seen)
    missing = []
    for it in its:
        for src, art in INTENT_PROVISIONS[it]["primary"]:
            ok = have_page if src == "FTA-VAT-REG-PAGE" else (src, str(art)) in have
            if not ok and provision_name(src, art) not in missing:
                missing.append(provision_name(src, art))
    if missing:
        return {"level": "incomplete", "intents": its, "ambiguous": ambiguous, "missing": missing,
                "message": "This may be incomplete: some provisions this topic normally needs were not in the texts used."}
    return {"level": "complete_for_map", "intents": its, "ambiguous": ambiguous, "missing": [],
            "message": "The main provisions for this topic were in the texts used. Still not checked by a qualified tax professional."}


class Asker:
    def __init__(self, main_db: Path, ledger_db: Path | None = None, recorded_file: Path | None = None):
        self.main_db = Path(main_db)
        self.ledger_db = Path(ledger_db) if ledger_db else ROOT / "data" / "CL_llm_experiment.sqlite3"
        self.recorded_file = Path(recorded_file) if recorded_file else RECORDED_FILE
        self.file_passages: dict = {}
        self.questions = {}
        for f in QUESTION_FILES:
            p = ROOT / f
            if p.exists():
                for q in json.loads(p.read_text(encoding="utf-8"))["questions"]:
                    self.questions[q["id"]] = q["text"]
        self.recorded = self._load_recorded()
        self.by_text = {_norm(self.questions[qid]): qid for qid in self.recorded if qid in self.questions}

    def _ro(self, p: Path) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _load_recorded(self) -> dict:
        if not self.ledger_db.exists():
            if not self.recorded_file.exists():
                return {}
            data = json.loads(self.recorded_file.read_text(encoding="utf-8"))
            out = {}
            for qid, r in data["answers"].items():
                out[qid] = {k: r[k] for k in ("call_id", "run_id", "at", "question_id", "model_returned",
                                              "retrieved_json", "parsed_json", "checks_json")}
                self.file_passages.update(r.get("passages", {}))
            return out
        con = self._ro(self.ledger_db)
        out = {}
        for r in con.execute("SELECT call_id, run_id, at, question_id, model_returned, retrieved_json, parsed_json, checks_json"
                             " FROM llm_calls WHERE status = 'ok' AND model_alias = 'sonnet' AND parsed_json IS NOT NULL"
                             " ORDER BY call_id"):
            out[r["question_id"]] = dict(r)   # latest successful answer wins
        con.close()
        return out

    def examples(self) -> list[dict]:
        return [{"id": qid, "persona": who, "label": what, "text": self.questions[qid]}
                for qid, who, what in DEMO_EXAMPLES if qid in self.recorded and qid in self.questions]

    def _passages(self, ids: list[str]) -> dict:
        if ids and not self.ledger_db.exists() and self.file_passages:
            return {i: self.file_passages[i] for i in ids if i in self.file_passages}
        if not ids or not self.main_db.exists():
            return {}
        con = self._ro(self.main_db)
        rows = con.execute(
            "SELECT p.passage_id, p.locator, p.text, d.source_id, d.url FROM passages p JOIN documents d ON d.doc_id = p.doc_id"
            f" WHERE p.passage_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        con.close()
        return {r["passage_id"]: dict(r) for r in rows}

    def ask(self, question: str = "", qid: str | None = None) -> dict:
        question = (question or "").strip()[:500]
        if qid and qid in self.recorded:
            question = self.questions.get(qid, question)
        else:
            qid = self.by_text.get(_norm(question))
        if qid and qid in self.recorded:
            return self._recorded(qid, question)
        return self._no_recording(question)

    def _recorded(self, qid: str, question: str) -> dict:
        from . import t2_retrieval as R
        r = self.recorded[qid]
        parsed = json.loads(r["parsed_json"])
        seen = json.loads(r["retrieved_json"] or "[]")
        checks = json.loads(r["checks_json"] or "{}")
        cites = parsed.get("citations", [])
        full = self._passages(sorted({c["passage_id"] for c in cites}))
        sources, worst = [], None
        for c in cites:
            p = full.get(c["passage_id"], {})
            src, art = p.get("source_id", "") or c["passage_id"].split(":")[0], _art(p.get("locator", ""))
            payload, kind = R.article_status(src, art)          # rc3 item 1: article-level source status (rule M4)
            eff = R.effective_status(payload, kind)
            if kind in ("article", "amended"):
                v = R.owner_validity(payload)
                if kind == "amended":
                    v = {**v, "status": "outdated", "plain": "Outdated: this article was amended since"}
            elif kind == "source" and not R.amended_articles(src):
                v = R.owner_validity(payload)                    # whole-source label only (no amendments listed); never a withhold
            elif kind == "source":
                v = {"status": "not_listed_as_amended", "current_official_url": None, "note": None, "conflicts": 0,
                     "plain": "This source has later amendments to other articles (" + ", ".join(R.amended_articles(src))
                              + "); this article is not listed as changed.", "review_status": payload.get("review_status")}
            else:
                v = R.owner_validity(None)
            if eff in R.SEVERITY and (worst is None or R.SEVERITY.index(eff) < R.SEVERITY.index(worst[0])):
                worst = (eff, provision_name(src, art), payload)
            sources.append({"passage_id": c["passage_id"], "quote": c.get("quote", ""),
                            "where": provision_name(p.get("source_id", ""), _art(p.get("locator", ""))) if p else c["passage_id"],
                            "locator": p.get("locator", ""), "url": p.get("url", ""), "text": p.get("text", ""), "validity": v})
        status = parsed.get("answer_status", "")
        g = guard(question, seen, status)
        if not checks.get("supported", False):
            g = {**g, "level": "incomplete", "message": "A quote or number in this answer could not be found in the cited text, so treat it as unreliable."}
        out = {
            "mode": "recorded", "question": question, "question_id": qid,
            "status": status, "status_plain": STATUS_PLAIN.get(status, status),
            "answer": parsed.get("answer", ""), "missing_facts": parsed.get("missing_facts", []),
            "sources": sources, "guard": g,
            "professional": status != "answered" or g["level"] != "complete_for_map",
            "provenance": {"recorded_at": r["at"], "model": r["model_returned"], "run_id": r["run_id"],
                           "note": "Recorded answer from an earlier test run, replayed here. No AI was called just now."},
        }
        if worst:                                                # withhold: no answer text, no quotes, no passage text
            st, where, payload = worst
            am = ((payload or {}).get("amendments") or [{}])[0]
            when = f" from {am['effective_date']}" if am.get("effective_date") else ""
            by = f" ({am['instrument']})" if am.get("instrument") else ""
            msg = (f"HerBiz has withheld this recorded answer: it relies on {where}, which was "
                   f"{'repealed or replaced' if st == 'superseded' else 'amended'}{when}{by}. Review required."
                   if st != "conflict" else
                   f"HerBiz has withheld this recorded answer: official texts disagree on {where}. Ask an FTA-registered tax agent.")
            for x in sources:
                x["quote"], x["text"] = "", ""
            out.update(status="withheld_source_status", status_plain="Answer withheld: the law it relies on has changed"
                       if st != "conflict" else "Answer withheld: official texts disagree",
                       answer=msg, missing_facts=[], professional=True,
                       guard={"level": "not_applicable", "intents": [], "missing": [],
                              "message": "The answer is withheld, so there is nothing to check for completeness."})
        return out

    def _no_recording(self, question: str) -> dict:
        """Task 2 A-4: WS B v8 retrieval (interim candidate, D-102) with WS C validity 1.2. Passages are never an answer.
        Fail closed: no database, drifted frozen code or a retrieval error -> no passages, "retrieval unavailable"."""
        from . import t2_retrieval as R
        qw = _words(question)
        near = sorted(((len(qw & _words(self.questions[q])) / max(1, len(qw | _words(self.questions[q]))), q)
                       for q in self.recorded if q in self.questions), reverse=True)[:3]
        out = {"mode": "no_recording", "question": question, "status": "no_recording",
               "status_plain": "No recorded answer for this question",
               "suggestions": [{"id": q, "text": self.questions[q]} for s, q in near if s > 0.15],
               "professional": True, "execution_mode": "deterministic", "interim_notice": R.INTERIM}
        try:
            if not question:
                raise R.Unavailable("no question")
            payload, items = R.retrieve(self.main_db, question)
        except R.Unavailable:
            out.update(status="retrieval_unavailable", status_plain="Search of the official texts is unavailable",
                       answer="HerBiz could not search the official texts just now, so no passages are shown and this is not an answer. "
                              "Please ask an FTA-registered tax agent.",
                       passages=[], guard={"level": "unchecked", "missing": [], "message": "Not an answer: nothing has been checked."},
                       _retrieval=None)
            return out
        scope = payload["scope"]
        comp = payload["completeness"]
        missing = [provision_name(m["source_id"], m["article"]) for m in comp["missing_required"]]
        passages = []
        if scope["in_scope"]:
            for i in items[:R.SHOWN]:
                v = R.validity(i["source_id"], i["article"])
                passages.append({"passage_id": i["passage_id"], "where": provision_name(i["source_id"], i["article"]),
                                 "locator": i["locator"], "url": i["url"], "text": i.get("text", ""),
                                 "validity": R.owner_validity(v)})
            answer = ("In this demo I only replay answers recorded in earlier test runs, and none matches your question exactly. "
                      "Below are the official passages that look most relevant. They are not an answer.")
        else:
            answer = ("HerBiz treated this question as outside UAE VAT, which is the only topic these texts cover, so no passages are shown and this is not an answer. "
                      "This check can be wrong: if your question is about UAE VAT, ask an FTA-registered tax agent.")
        msg = ("This may be incomplete: some provisions this topic normally needs were not found: " + "; ".join(missing) + "."
               if missing else "This may be incomplete: HerBiz cannot confirm that every provision this topic needs was found.")
        out.update(answer=answer, passages=passages, scope=scope["class"],
                   retrieved=len(items), shown=len(passages),
                   guard={"level": "incomplete" if comp["status"] == "incomplete" else "unchecked", "missing": missing,
                          "message": msg if scope["in_scope"] else "Not an answer: nothing has been checked."},
                   _retrieval=R.without_text(payload))
        return out
