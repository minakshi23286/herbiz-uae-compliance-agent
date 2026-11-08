"""Request ledger and budget enforcement for the LLM experiment.

Every request is written as `reserved` BEFORE it is sent, with its worst-case cost; the row is completed after.
A request is refused if spent + open reservations + its own reservation would exceed the authorisation.
Unfinished reservations (e.g. a reply lost in transit) stay counted at their worst case.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    at             TEXT NOT NULL,
    phase          TEXT NOT NULL,
    question_id    TEXT NOT NULL,
    model_alias    TEXT NOT NULL,
    model_requested TEXT NOT NULL,
    model_returned TEXT,
    status         TEXT NOT NULL,      -- reserved | ok | refusal | error | refused_budget
    reserved_usd   REAL NOT NULL,
    input_tokens   INTEGER, output_tokens INTEGER, cache_write_tokens INTEGER, cache_read_tokens INTEGER,
    cost_usd       REAL,
    latency_ms     INTEGER,
    stop_reason    TEXT,
    request_id     TEXT,
    error          TEXT,
    retrieved_json TEXT,
    response_text  TEXT,
    parsed_json    TEXT,
    checks_json    TEXT,
    grade_json     TEXT
);
CREATE TABLE IF NOT EXISTS llm_runs (
    run_id TEXT PRIMARY KEY, at TEXT NOT NULL, phase TEXT NOT NULL, models TEXT NOT NULL,
    authorized_usd REAL NOT NULL, outcome TEXT, stop_reason TEXT, main_db_md5_before TEXT, main_db_md5_after TEXT
);
"""


class BudgetExceeded(Exception):
    pass


def price(usage: dict, p: dict) -> float:
    """USD cost from usage fields (prices per million tokens)."""
    return round((usage.get("input_tokens") or 0) * p["input"] / 1e6
                 + (usage.get("output_tokens") or 0) * p["output"] / 1e6
                 + (usage.get("cache_write_tokens") or 0) * p["cache_write"] / 1e6
                 + (usage.get("cache_read_tokens") or 0) * p["cache_read"] / 1e6, 6)


def worst_case(input_tokens: int, max_tokens: int, p: dict) -> float:
    """Reservation: counted input (+10% and 500 tokens margin) at input price + every possible output token."""
    return round((input_tokens * 1.10 + 500) * p["input"] / 1e6 + max_tokens * p["output"] / 1e6, 6)


class Ledger:
    def __init__(self, path: str | Path, authorized_usd: float, hard_ceiling_usd: float):
        if hard_ceiling_usd > 60:
            raise ValueError("hard ceiling above the approved $60 is refused")
        self.limit = min(float(authorized_usd), float(hard_ceiling_usd))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    @staticmethod
    def now() -> str:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=4))).replace(microsecond=0).isoformat()

    def committed_usd(self) -> float:
        """Money treated as gone: finished calls at actual cost + unfinished reservations at worst case."""
        r = self.db.execute("SELECT COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_usd "
                            "WHEN status IN ('ok','refusal','error') THEN COALESCE(cost_usd, 0) ELSE 0 END), 0) FROM llm_calls").fetchone()[0]
        return round(float(r), 6)

    def reserve(self, run_id: str, phase: str, qid: str, alias: str, model_id: str, amount: float) -> int:
        if self.committed_usd() + amount > self.limit:
            self.db.execute("INSERT INTO llm_calls (run_id, at, phase, question_id, model_alias, model_requested, status, reserved_usd)"
                            " VALUES (?,?,?,?,?,?, 'refused_budget', ?)", (run_id, self.now(), phase, qid, alias, model_id, amount))
            self.db.commit()
            raise BudgetExceeded(f"would exceed the ${self.limit:.2f} authorisation "
                                 f"(committed ${self.committed_usd():.4f} + reservation ${amount:.4f})")
        cur = self.db.execute("INSERT INTO llm_calls (run_id, at, phase, question_id, model_alias, model_requested, status, reserved_usd)"
                              " VALUES (?,?,?,?,?,?, 'reserved', ?)", (run_id, self.now(), phase, qid, alias, model_id, amount))
        self.db.commit()
        return cur.lastrowid

    def complete(self, call_id: int, **fields) -> None:
        for k in ("retrieved_json", "parsed_json", "checks_json", "grade_json"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k], ensure_ascii=False)
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE llm_calls SET {cols} WHERE call_id = ?", (*fields.values(), call_id))
        self.db.commit()
