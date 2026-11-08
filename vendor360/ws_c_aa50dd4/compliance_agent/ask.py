"""Owner "Ask a question" panel — DEMO MODE: recorded answers only, no live AI, no network, no spend.

Answers are replayed from the experiment ledger (data/CL_llm_experiment.sqlite3, read-only): the latest successful Sonnet
answer for each development question whose text matches the owner's question exactly (case and spacing ignored).
Anything else gets the most relevant official passages (offline retrieval) and an honest "no recorded answer".

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
    def __init__(self, main_db: Path, ledger_db: Path | None = None):
        self.main_db = Path(main_db)
        self.ledger_db = Path(ledger_db) if ledger_db else ROOT / "data" / "CL_llm_experiment.sqlite3"
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
            return {}
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
        r = self.recorded[qid]
        parsed = json.loads(r["parsed_json"])
        seen = json.loads(r["retrieved_json"] or "[]")
        checks = json.loads(r["checks_json"] or "{}")
        cites = parsed.get("citations", [])
        full = self._passages(sorted({c["passage_id"] for c in cites}))
        sources = []
        for c in cites:
            p = full.get(c["passage_id"], {})
            sources.append({"passage_id": c["passage_id"], "quote": c.get("quote", ""),
                            "where": provision_name(p.get("source_id", ""), _art(p.get("locator", ""))) if p else c["passage_id"],
                            "locator": p.get("locator", ""), "url": p.get("url", ""), "text": p.get("text", "")})
        status = parsed.get("answer_status", "")
        g = guard(question, seen, status)
        if not checks.get("supported", False):
            g = {**g, "level": "incomplete", "message": "A quote or number in this answer could not be found in the cited text, so treat it as unreliable."}
        return {
            "mode": "recorded", "question": question, "question_id": qid,
            "status": status, "status_plain": STATUS_PLAIN.get(status, status),
            "answer": parsed.get("answer", ""), "missing_facts": parsed.get("missing_facts", []),
            "sources": sources, "guard": g,
            "professional": status != "answered" or g["level"] != "complete_for_map",
            "provenance": {"recorded_at": r["at"], "model": r["model_returned"], "run_id": r["run_id"],
                           "note": "Recorded answer from an earlier test run, replayed here. No AI was called just now."},
        }

    def _no_recording(self, question: str) -> dict:
        passages = []
        if question and self.main_db.exists():
            from .llm_lab.retrieve import connect_ro, search
            con = connect_ro(self.main_db)
            try:
                passages = [{"passage_id": p["passage_id"], "where": provision_name(p["source_id"], _art(p["locator"])),
                             "locator": p["locator"], "url": p.get("url", ""), "text": p["text"]} for p in search(con, question)[:5]]
            except sqlite3.Error:
                passages = []
            con.close()
        qw = _words(question)
        near = sorted(((len(qw & _words(self.questions[q])) / max(1, len(qw | _words(self.questions[q]))), q)
                       for q in self.recorded if q in self.questions), reverse=True)[:3]
        outside = "" if intents(question)[0] else ("Your question may be outside VAT registration, which is the only topic these texts cover. ")
        return {
            "mode": "no_recording", "question": question, "status": "no_recording",
            "status_plain": "No recorded answer for this question",
            "answer": outside + "In this demo I only replay answers recorded in earlier test runs, and none matches your question exactly. "
                      "Below are the official passages that look most relevant. They are not an answer.",
            "passages": passages, "guard": {"level": "unchecked", "missing": [], "message": "Not an answer: nothing has been checked."},
            "suggestions": [{"id": q, "text": self.questions[q]} for s, q in near if s > 0.15],
            "professional": True,
        }
