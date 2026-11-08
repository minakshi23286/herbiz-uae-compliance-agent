"""Amendment and supersession map, built from the source register (read-only).

For every captured version: which registered instruments it includes (from its own stated amendment chain), which
in-force instruments it is missing (so the version is outdated for the articles they touch), and how it relates to the
other versions of the same source (current / archived / superseded). Nothing here changes a status; it only reports."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .register import REGISTER


def _norm_instrument(title: str) -> str:
    """'Cabinet Decision No. (100) of 2024' -> 'cabinet decision 100 2024'. The type is kept exactly (cabinet / ministerial /
    FTA decision, decree-law), so 'Ministerial Decision No. 100 of 2024' never matches Cabinet Decision 100/2024 (QA C05)."""
    m = INSTRUMENT_RX.search(title)
    if m:
        return f"{_norm_type(m.group(1))} {int(m.group(2))} {m.group(3)}"
    return " ".join(title.lower().split())


def amendment_map(register_path: Path = REGISTER, as_of: str | None = None, db=None) -> dict:
    """With db, every instrument's affected articles are completed from the footnotes of the captured versions that
    include it (observed_in_file), which replaces snippet-based lists (QA C02/C08)."""
    reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    as_of = as_of or dt.date.today().isoformat()
    instruments = reg.get("instruments", [])
    effects = reg.get("instrument_effects", [])
    fn_articles: dict[str, set] = {}
    if db is not None:
        for s in reg.get("sources", []):
            for v in s.get("versions", []):
                for ins, arts in instrument_articles_from_footnotes(db, v["version_id"]).items():
                    fn_articles.setdefault(ins, set()).update(a for a in arts if a != "Front matter")
    by_source: dict[str, list[dict]] = {}
    for ins in instruments:
        by_source.setdefault(ins["amends_source"], []).append(ins)
    out_versions = []
    for s in reg.get("sources", []):
        sid = s["source_id"]
        # in force by `as_of`; an unknown effective date counts as possibly in force (QA C06), flagged below
        relevant = [i for i in by_source.get(sid, []) if i.get("status") == "in force"
                    and (i.get("effective") is None or i["effective"] <= as_of)]
        for v in s.get("versions", []):
            stated = {_norm_instrument(a["instrument"]) for a in v.get("amendments_as_stated", [])}
            included = [i["instrument_id"] for i in relevant if _norm_instrument(i["title"]) in stated]
            missing = [i for i in relevant if _norm_instrument(i["title"]) not in stated]
            affected, unknown_scope = [], []
            for i in missing:
                from_fn = sorted(fn_articles.get(_norm_instrument(i["title"]), set()))
                arts = sorted(set(i.get("articles_affected") or []) | set(from_fn))
                arts += [e["article"] for e in effects if e["instrument_id"] == i["instrument_id"] and e["article"] not in arts]
                for a in arts:
                    affected.append({"article": a, "instrument_id": i["instrument_id"], "effective": i.get("effective"),
                                     "effect": next((e["effect"] for e in effects if e["instrument_id"] == i["instrument_id"]
                                                     and e["article"] == a), "amends"),
                                     "evidence": "footnotes of a newer captured version" if a in from_fn else "register",
                                     "complete_list": bool(i.get("articles_list_complete")) or bool(from_fn)})
                if not arts or not (i.get("articles_list_complete") or from_fn):
                    unknown_scope.append(i["instrument_id"])
            currency = (v.get("currency_observations") or [{}])[-1].get("currency", "")
            out_versions.append({
                "source_id": sid, "version_id": v["version_id"], "kb_status": v.get("kb_status"),
                "latest_effective_as_stated": v.get("latest_effective_as_stated"),
                "includes": included, "missing_in_force_instruments": [i["instrument_id"] for i in missing],
                "missing_with_unknown_effective_date": [i["instrument_id"] for i in missing if i.get("effective") is None],
                "outdated": bool(missing), "affected_articles": affected,
                "missing_instruments_with_unknown_scope": unknown_scope,
                "fta_currency": "current" if currency.upper().startswith("CURRENT") else
                                ("archived" if "archived" in currency.lower() or "OUTDATED" in currency else
                                 ("unknown" if not currency else "other")),
            })
    for sid in {v["source_id"] for v in out_versions}:
        vs = [v for v in out_versions if v["source_id"] == sid]
        dated = [v for v in vs if v["latest_effective_as_stated"]]
        newest = max(dated, key=lambda v: (v["latest_effective_as_stated"], v["version_id"])) if dated else None
        for v in vs:
            v["newest_by_effective_date"] = bool(newest and v["version_id"] == newest["version_id"])
            v["superseded_by_effective_date"] = newest["version_id"] if newest and v is not newest else None
    return {"as_of": as_of, "register_version": reg.get("register_version"), "instruments": len(instruments),
            "footnote_evidence_used": db is not None, "versions": out_versions}


# ------------------------------------------------------------------ amendment evidence from the documents' own footnotes
FOOTNOTE_LINE = re.compile(r"^\s*(\d{1,3})\s+((?:Article|Clause|Paragraph|Item|Definition|Title|Chapter|This)\b.*?"
                           r"(amended|added|repealed|replaced|inserted|cancelled)\b.*)$", re.I | re.M)
INSTRUMENT_RX = re.compile(r"(Cabinet Decision|Federal Decree-Law|Decree-Law|Ministerial Decision|FTA Decision)\s+No\.?\s*\(?(\d+)\)?\s+of\s+(\d{4})", re.I)
FUTURE_RX = re.compile(r"come into effect from (the first tax year commencing after \d{1,2} \w+ \d{4}|\d{1,2} \w+ \d{4})", re.I)


def _norm_type(kind: str) -> str:
    k = kind.lower()
    return "decree-law" if "decree" in k else ("ministerial decision" if "minister" in k else ("fta decision" if "fta" in k else "cabinet decision"))


NOT_MARKER_BEFORE = {"article", "articles", "clause", "clauses", "no", "no.", "of", "paragraph", "item", "chapter", "title",
                     "aed", "and", "to", "or", "within", "than", "least", "decision", "law", "page"}


def _has_marker(body: str, n: int) -> bool:
    """A footnote marker is glued to a word or punctuation ('follows:39', 'Deregistration10'), or ends a line after a
    word ('Tax Deregistration 10'). A number after 'Article', 'Clause', 'No.', 'of', 'within' ... is a reference."""
    for m in re.finditer(rf"(?<!\d){n}(?!\d)", body):
        before = body[:m.start()]
        if not before or before[-1] in "(\n":
            continue
        if before[-1].isalpha() or before[-1] in "):;.,":
            word = re.findall(r"[A-Za-z.]+$", before)
            if word and word[0].lower().rstrip(".") in {"no"}:
                continue
            return True
        if before[-1] == " " and re.search(r"Article\s*\(?\d+\)?(?:\s*\(\w+\))?\s+$", before.splitlines()[-1] if before.splitlines() else "") \
                and re.match(r"[ \t]*(\n|$)", body[m.end():]) and re.match(r"\s*Article", before.splitlines()[-1]):
            return True                                     # title-less heading 'Article 1 1' (marker after the number)
        if before[-1] == " ":
            prev = re.findall(r"([A-Za-z.]+)\s$", before)
            line_end = re.match(r"[ \t]*(\n|$)", body[m.end():])
            if prev and line_end and prev[0].lower() not in NOT_MARKER_BEFORE and prev[0].lower().rstrip(".") not in NOT_MARKER_BEFORE:
                return True
    return False


def footnote_index(db, version_id: str) -> dict:
    """Map every footnote ('38 Clause amended as per Cabinet Decision No. 149 of 2026 ...') to the article that carries
    its marker. Markers run 1..N through the document, so each is assigned to the first article (reading order) whose
    body - footnote lines removed - shows the marker glued after a word or punctuation. Evidence level: observed_in_file."""
    from .inventory import article_key, connect_ro
    con = connect_ro(db)
    try:
        rows = con.execute("SELECT locator, text FROM passages WHERE version_id = ? ORDER BY seq", (version_id,)).fetchall()
    finally:
        con.close()
    notes, bodies = {}, []
    for r in rows:
        for m in FOOTNOTE_LINE.finditer(r["text"]):
            n = int(m.group(1))
            ins = [f"{_norm_type(t)} {int(no)} {yr}" for t, no, yr in INSTRUMENT_RX.findall(m.group(2))]
            fut = FUTURE_RX.search(" ".join(r["text"][m.start():m.start() + 400].split()))   # footnotes run over lines
            k0 = article_key(r["locator"])
            notes.setdefault(n, {"marker": n, "text": " ".join(m.group(2).split())[:240], "action": m.group(3).lower(),
                                 "instruments": ins, "future_effect": fut.group(1) if fut else None,
                                 "line_in": (f"{k0[0]}{' (' + k0[1] + ')' if k0[1] else ''}" if k0 else r["locator"].split(",")[0])})
        k = article_key(r["locator"])
        key = (f"{k[0]}{' (' + k[1] + ')' if k[1] else ''}" if k else r["locator"].split(",")[0])
        bodies.append((key, FOOTNOTE_LINE.sub(" ", r["text"])))
    by_article: dict[str, list[dict]] = {}
    unassigned, i = [], 0
    for n in sorted(notes):
        j = i
        while j < len(bodies) and not _has_marker(bodies[j][1], n):
            j += 1
        if j == len(bodies):
            unassigned.append(n)
            continue
        i = j
        by_article.setdefault(bodies[j][0], []).append(notes[n])
    return {"version_id": version_id, "footnotes": len(notes), "assigned": len(notes) - len(unassigned),
            "unassigned_markers": unassigned, "articles": by_article}


def instrument_articles_from_footnotes(db, version_id: str) -> dict[str, list[str]]:
    """{normalised instrument: [articles it amended/added per this version's footnotes]}."""
    out: dict[str, set] = {}
    for art, fns in footnote_index(db, version_id)["articles"].items():
        for f in fns:
            for ins in f["instruments"]:
                out.setdefault(ins, set()).add(art)
    return {k: sorted(v, key=lambda a: (int(re.match(r"\d+", a).group()) if re.match(r"\d+", a) else 9999, a)) for k, v in out.items()}
