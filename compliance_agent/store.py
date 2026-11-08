"""SQLite store. One file on disk; the audit table is append-only (update and delete are refused by triggers).

Original source text (evidence) and our interpretation of it (obligations) live in separate tables.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS business_profiles (
    profile_id   TEXT NOT NULL,
    version      INTEGER NOT NULL,
    project_id   TEXT NOT NULL,
    business_id  TEXT NOT NULL,
    display_name TEXT NOT NULL,
    facts_json   TEXT NOT NULL,
    synthetic    INTEGER NOT NULL CHECK (synthetic = 1),
    created_at   TEXT NOT NULL,
    PRIMARY KEY (profile_id, version)
);

-- Evidence: the source text exactly as captured, never edited after insert.
CREATE TABLE IF NOT EXISTS source_versions (
    version_id        TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    issuing_authority TEXT NOT NULL,
    authority_type    TEXT NOT NULL,          -- primary | secondary
    jurisdiction      TEXT NOT NULL,          -- AE (federal) | AE-DU | AE-SH ...
    document_title    TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    locator           TEXT NOT NULL,          -- article/page/section, or UNKNOWN
    publication_date  TEXT,                   -- NULL when not known; never invented
    effective_date    TEXT,
    retrieved_at      TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    normalized_hash   TEXT NOT NULL,
    text              TEXT NOT NULL,
    status            TEXT NOT NULL,          -- candidate | approved | rejected | superseded
    superseded_by     TEXT,
    change_class      TEXT,                   -- first_version | cosmetic | substantive
    flags_json        TEXT NOT NULL DEFAULT '[]',
    fixture           INTEGER NOT NULL,
    UNIQUE (source_id, content_hash)
);

-- Interpretation: what we think a source version requires, with conditions over profile facts.
CREATE TABLE IF NOT EXISTS obligations (
    obligation_id     TEXT PRIMARY KEY,       -- stable id + source version
    obligation_key    TEXT NOT NULL,          -- same key across versions and across conflicting sources
    version_id        TEXT NOT NULL REFERENCES source_versions(version_id),
    title             TEXT NOT NULL,
    requirement       TEXT NOT NULL,          -- required | not_required
    conditions_json   TEXT NOT NULL,
    action_json       TEXT NOT NULL,
    interpretation_status TEXT NOT NULL       -- fixture_reviewed | unreviewed
);

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id   TEXT PRIMARY KEY,
    profile_id      TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    obligation_key  TEXT NOT NULL,
    result          TEXT NOT NULL,            -- applicable | not_applicable | needs_clarification | conflict
    rationale       TEXT NOT NULL,
    missing_json    TEXT NOT NULL,
    citations_json  TEXT NOT NULL,
    current         INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id         TEXT PRIMARY KEY,
    dedupe_key      TEXT NOT NULL UNIQUE,
    kind            TEXT NOT NULL,            -- obligation_action | clarification | conflict | source_update
    project_id      TEXT NOT NULL,
    business_id     TEXT,
    profile_id      TEXT,
    obligation_key  TEXT,
    source_version_id TEXT,
    assessment_id   TEXT,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL,
    why             TEXT NOT NULL,
    owner           TEXT NOT NULL,
    reviewer        TEXT NOT NULL,
    due_basis       TEXT NOT NULL,
    due_date        TEXT,
    evidence_required_json TEXT NOT NULL,
    evidence_json   TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL REFERENCES cases(case_id),
    decision    TEXT NOT NULL,                -- approve | reject
    reviewer    TEXT NOT NULL,
    role        TEXT NOT NULL,
    context     TEXT NOT NULL,
    outcome     TEXT NOT NULL,                -- accepted | refused
    decided_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key  TEXT NOT NULL UNIQUE,
    case_id     TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    event       TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS source_text_frozen BEFORE UPDATE OF text, content_hash ON source_versions
BEGIN SELECT RAISE(ABORT, 'source evidence is immutable'); END;
"""


SCHEMA_V2 = """
-- Knowledge base: original documents on disk, referenced here; extracted passages; full-text index.
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,         -- source_id + sha256 prefix
    source_id       TEXT NOT NULL,
    version_id      TEXT,                     -- source_versions row created from this capture
    origin_label    TEXT NOT NULL,            -- REAL_OFFICIAL_SOURCE | SYNTHETIC_FIXTURE
    url             TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    bytes           INTEGER NOT NULL,
    mime            TEXT NOT NULL,
    raw_path        TEXT NOT NULL,            -- relative to the project data directory
    extraction_status TEXT NOT NULL,          -- ok | partial | failed
    extractor       TEXT NOT NULL,
    pages           INTEGER,
    empty_pages_json TEXT NOT NULL DEFAULT '[]',
    extraction_note TEXT NOT NULL DEFAULT '',
    UNIQUE (source_id, sha256)
);

CREATE TABLE IF NOT EXISTS passages (
    passage_id  TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id),
    version_id  TEXT,
    seq         INTEGER NOT NULL,
    locator     TEXT NOT NULL,                -- e.g. "Article (13), p. 14" or "Paragraph 3"
    page_start  INTEGER,
    page_end    INTEGER,
    text        TEXT NOT NULL,
    label       TEXT NOT NULL                 -- UNVERIFIED_EXTRACTION | SYNTHETIC_FIXTURE
);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(passage_id UNINDEXED, locator, text, tokenize = 'porter unicode61');

CREATE TABLE IF NOT EXISTS collection_attempts (
    attempt_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    url         TEXT NOT NULL,
    at          TEXT NOT NULL,
    outcome     TEXT NOT NULL,                -- new_version | identical | cosmetic | failed | refused
    detail      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id      TEXT PRIMARY KEY,
    at          TEXT NOT NULL,
    suite       TEXT NOT NULL,
    passed      INTEGER NOT NULL,
    failed      INTEGER NOT NULL,
    metrics_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_results (
    run_id      TEXT NOT NULL REFERENCES evaluation_runs(run_id),
    scenario_id TEXT NOT NULL,
    category    TEXT NOT NULL,
    expected    TEXT NOT NULL,
    actual      TEXT NOT NULL,
    passed      INTEGER NOT NULL,
    note        TEXT NOT NULL,
    PRIMARY KEY (run_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS reviewer_signoffs (
    signoff_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type   TEXT NOT NULL,                -- obligation | reference_answer | source
    item_id     TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    qualification TEXT NOT NULL,
    decision    TEXT NOT NULL,                -- agree | disagree | needs_source
    note        TEXT NOT NULL,
    at          TEXT NOT NULL
);
"""

# Columns added after v1. Applied idempotently so databases made by earlier builds keep working.
COLUMN_MIGRATIONS = [
    ("source_versions", "origin_label", "TEXT NOT NULL DEFAULT 'SYNTHETIC_FIXTURE'"),
    ("source_versions", "doc_id", "TEXT"),
    ("obligations", "support_quote", "TEXT"),
    ("obligations", "support_status", "TEXT NOT NULL DEFAULT 'not_checked'"),   # supported | unsupported | not_checked
    ("obligations", "support_passage_id", "TEXT"),
]


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # The local web server handles requests on worker threads; web.App serialises access with a lock.
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.executescript(SCHEMA_V2)
        for table, col, decl in COLUMN_MIGRATIONS:
            cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        self.db.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '2') "
                        "ON CONFLICT(key) DO UPDATE SET value = '2'")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # small helpers -------------------------------------------------------
    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def audit(self, at: str, actor: str, event: str, entity: str, entity_id: str, payload: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_events (at, actor, event, entity, entity_id, payload_json) VALUES (?,?,?,?,?,?)",
            (at, actor, event, entity, entity_id, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)))

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        r = self.one("SELECT value FROM meta WHERE key = ?", (key,))
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, value))
