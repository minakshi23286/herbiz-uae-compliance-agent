"""Run the LLM smoke test (or an offline dry run with a fake client).

    .venv-llm/bin/python -m compliance_agent.llm_lab.run --model sonnet --set smoke
    .venv-llm/bin/python -m compliance_agent.llm_lab.run --model opus --set opus_subset
    python3 -m compliance_agent.llm_lab.run --model sonnet --set smoke --fake      (no network, no spend)

Stops on: budget (authorisation in experiments/llm/CL_llm_experiment.json), repeated failures, billing errors,
unknown model, too many unsupported answers, or any change to the main database file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

from . import answer as A
from .budget import BudgetExceeded, Ledger, price, worst_case
from .retrieve import connect_ro, file_md5, search

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "experiments" / "llm" / "CL_llm_experiment.json"
QUESTIONS = ROOT / "fixtures" / "CL_llm_eval_questions.json"


class Stop(Exception):
    pass


def real_client(cfg: dict):
    import anthropic  # only available inside .venv-llm
    return anthropic.Anthropic(max_retries=0, timeout=float(cfg["timeout_seconds"]))


def _text(resp) -> str:
    return next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")


UNSEEN = ROOT / "fixtures" / "CL_llm_eval_unseen_v1.json"
UNSEEN_V2 = ROOT / "fixtures" / "CL_llm_eval_unseen_v2.json"
UNSEEN_V3 = ROOT / "fixtures" / "CL_llm_eval_unseen_v3.json"


def run(model_alias: str, set_name: str, client=None, cfg: dict | None = None, root: Path = ROOT,
        log=print, questions_file: Path | None = None) -> dict:
    cfg = cfg or json.loads(CONFIG.read_text(encoding="utf-8"))
    qfile = questions_file or (UNSEEN_V3 if set_name.startswith("unseen_v3") else UNSEEN_V2 if set_name.startswith("unseen_v2") else UNSEEN if set_name.startswith("unseen") else QUESTIONS)
    qs = json.loads(Path(qfile).read_text(encoding="utf-8"))
    if qfile in (UNSEEN, UNSEEN_V2, UNSEEN_V3):
        from .freeze import verify
        verify(qfile)   # refuses to run if the frozen unseen set was changed
    qmap = {q["id"]: q for q in qs["questions"]}
    ids = qs.get(set_name) or cfg["paid_subsets"][set_name]   # subsets of frozen sets live in the config, not the frozen file
    m = cfg["models"][model_alias]
    main_db = root / cfg["main_db"]
    md5_before = file_md5(main_db)
    ledger = Ledger(root / cfg["experiment_db"], cfg["authorized_usd"], cfg["hard_ceiling_usd"])
    run_id = f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}-{model_alias}"
    ledger.db.execute("INSERT INTO llm_runs (run_id, at, phase, models, authorized_usd, main_db_md5_before) VALUES (?,?,?,?,?,?)",
                      (run_id, ledger.now(), set_name, m["id"], ledger.limit, md5_before))
    ledger.db.commit()
    con = connect_ro(main_db)
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set in this terminal (the key itself is never printed).")
        client = real_client(cfg)
    fails, results, stop_reason = 0, [], None
    log(f"{run_id}: {len(ids)} questions on {m['id']}; authorisation ${ledger.limit:.2f}; committed so far ${ledger.committed_usd():.4f}")
    try:
        for qid in ids:
            q = qmap[qid]
            passages = search(con, q["text"], cfg["top_k_passages"])
            retrieved = [{"passage_id": p["passage_id"], "source_id": p["source_id"], "locator": p["locator"],
                          "source_status": p["source_status"], "added_by": p.get("added_by", "bm25")} for p in passages]
            messages = [{"role": "user", "content": A.user_message(q["text"], passages)}]
            try:
                n_in = client.messages.count_tokens(model=m["id"], system=A.SYSTEM, messages=messages).input_tokens
                count_note = "counted"
            except Exception as ex:  # unknown model -> stop before any spend; otherwise estimate conservatively
                if type(ex).__name__ == "NotFoundError":
                    raise Stop(f"model {m['id']} not available to this key (token count returned not found)")
                if getattr(ex, "status_code", None) in (400, 401, 403):
                    detail = str(getattr(ex, "message", "") or ex)[:500]
                    raise Stop(f"token count rejected ({type(ex).__name__} {getattr(ex, 'status_code', '')}): {detail}")
                n_in = int((len(A.SYSTEM) + len(messages[0]["content"])) / 2.5)
                count_note = f"estimated ({type(ex).__name__})"
            reserve = worst_case(n_in, cfg["max_tokens"], m)
            try:
                call_id = ledger.reserve(run_id, set_name, qid, model_alias, m["id"], reserve)
            except BudgetExceeded as ex:
                raise Stop(f"budget: {ex}")
            t0 = time.monotonic()
            try:
                resp = client.messages.create(
                    model=m["id"], max_tokens=cfg["max_tokens"], system=A.SYSTEM, messages=messages,
                    output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": A.SCHEMA}})
            except Exception as ex:
                latency = int((time.monotonic() - t0) * 1000)
                code = getattr(ex, "status_code", None)
                # an error response is normally not billed; keep it at 0 but record it. A lost reply stays 'reserved'.
                detail = str(getattr(ex, "message", "") or ex)[:500]  # API error text; never contains the key
                ledger.complete(call_id, status="error", cost_usd=0.0, latency_ms=latency,
                                error=f"{type(ex).__name__} {code}: {detail}")
                fails += 1
                log(f"  {qid}: ERROR {type(ex).__name__} {code}: {detail}")
                if code == 400 or type(ex).__name__ == "BadRequestError":
                    raise Stop(f"request rejected as malformed (400) — fix the request before retrying: {detail}")
                if code == 402:
                    raise Stop("billing error (402): credit or spend limit reached")
                if type(ex).__name__ == "NotFoundError":
                    raise Stop(f"model {m['id']} not found")
                if fails >= cfg["stop_rules"]["consecutive_failures"]:
                    raise Stop(f"{fails} failed requests in a row")
                continue
            latency = int((time.monotonic() - t0) * 1000)
            returned = getattr(resp, "model", "") or ""
            u = resp.usage
            usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                     "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                     "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
            cost = price(usage, m)
            status, text, parsed, checks, grade = "ok", _text(resp), None, None, None
            if resp.stop_reason == "refusal":
                status = "refusal"
                fails += 1
            else:
                try:
                    parsed = A.parse_text(text)
                    checks = A.check(parsed, passages, q["text"])
                    grade = A.grade(q, parsed, checks)
                    grade["readability"] = A.readability(parsed.get("answer", ""))
                    grade["expected_source_retrieved"] = A.retrieved_expected(q, retrieved)
                    from .retrieval_metrics import per_question
                    grade["retrieval"] = per_question(q, retrieved)
                    grade["category"] = q["category"]
                    grade["_has_must_include"] = bool(q.get("must_include"))
                    fails = 0
                except (ValueError, KeyError) as ex:
                    checks = {"supported": False, "parse_error": f"{type(ex).__name__}: {ex}"[:300]}
                    grade = {"pass": False, "parse_error": True}
                    fails += 1
            ledger.complete(call_id, status=status, model_returned=getattr(resp, "model", None), cost_usd=cost,
                            latency_ms=latency, stop_reason=resp.stop_reason, request_id=getattr(resp, "_request_id", None),
                            retrieved_json=retrieved, response_text=text, parsed_json=parsed or {}, checks_json=checks or {},
                            grade_json=grade or {}, error=None if count_note == "counted" else count_note, **usage)
            if not returned.startswith(m["id"]):
                raise Stop(f"response came from {returned!r}, not the requested {m['id']}")
            row = {"q": qid, "model": getattr(resp, "model", None), "status": parsed and parsed.get("answer_status"),
                   "pass": bool(grade and grade.get("pass")), "supported": bool(checks and checks.get("supported")),
                   "cost": cost, "latency_ms": latency, "in": usage["input_tokens"], "out": usage["output_tokens"],
                   "stop_reason": resp.stop_reason}
            results.append(row)
            log(f"  {qid}: {row['status'] or status:12} pass={row['pass']!s:5} cited-ok={row['supported']!s:5} "
                f"${cost:.4f} {latency/1000:.1f}s in={usage['input_tokens']} out={usage['output_tokens']} stop={resp.stop_reason}")
            committed = ledger.committed_usd()
            if committed >= cfg["warn_at_fraction"] * ledger.limit:
                log(f"  WARNING: ${committed:.4f} committed = {committed / ledger.limit:.0%} of the ${ledger.limit:.2f} authorisation")
            if fails >= cfg["stop_rules"]["consecutive_failures"]:
                raise Stop(f"{fails} failed answers in a row")
            n = cfg["stop_rules"]["unsupported_check_after_n"]
            answered = [r for r in results if r["status"]]
            if len(answered) >= n:
                rate = sum(not r["supported"] for r in answered) / len(answered)
                if rate > cfg["stop_rules"]["max_unsupported_rate"]:
                    raise Stop(f"unsupported-answer rate {rate:.0%} above {cfg['stop_rules']['max_unsupported_rate']:.0%}")
            if file_md5(main_db) != md5_before:
                raise Stop("main database changed during the run")
    except Stop as ex:
        stop_reason = str(ex)
        log(f"STOPPED: {stop_reason}")
    finally:
        con.close()
    md5_after = file_md5(main_db)
    if md5_after != md5_before:
        stop_reason = (stop_reason or "") + " | MAIN DATABASE CHANGED"
    total = round(sum(r["cost"] for r in results), 6)
    ledger.db.execute("UPDATE llm_runs SET outcome=?, stop_reason=?, main_db_md5_after=? WHERE run_id=?",
                      ("stopped" if stop_reason else "completed", stop_reason, md5_after, run_id))
    ledger.db.commit()
    summary = {"run_id": run_id, "model": m["id"], "questions": len(ids), "answered": len(results),
               "passed": sum(r["pass"] for r in results), "citations_supported": sum(r["supported"] for r in results),
               "cost_usd": total, "committed_all_runs_usd": ledger.committed_usd(), "authorisation_usd": ledger.limit,
               "stop_reason": stop_reason, "main_db_unchanged": md5_after == md5_before,
               "latency_ms": sorted(r["latency_ms"] for r in results)}
    log(json.dumps(summary, indent=1))
    ledger.db.close()
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["sonnet", "opus"], required=True)
    ap.add_argument("--set", choices=["smoke", "opus_subset", "evaluation_v2", "opus_difficult", "unseen_all", "unseen_opus", "unseen_v2_all", "unseen_v3_all", "unseen_v3_paid"], required=True)
    ap.add_argument("--repeat", type=int, default=1, help="run the set N times (consistency check)")
    ap.add_argument("--fake", action="store_true", help="offline fake client: no network, no spend")
    a = ap.parse_args(argv)
    client, cfg = None, None
    if a.fake:  # offline: fake client AND a throwaway ledger, so fake costs never enter the real one
        import tempfile
        from .fake import FakeClient
        client = FakeClient()
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg["experiment_db"] = str(Path(tempfile.mkdtemp()) / "fake_ledger.sqlite3")
    for i in range(max(1, a.repeat)):
        s = run(a.model, a.set, client=client, cfg=cfg)
        if s["stop_reason"]:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
