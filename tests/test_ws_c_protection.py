"""Reversible database protection (design: docs/rag/CL_HERBIZ_DB_PROTECTION_DESIGN.md). Copies only."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent.dbsafety import AuthoritativeDatabaseError, copy_readonly  # noqa: E402
from compliance_agent.rag_c import protection as P  # noqa: E402

REF = ROOT / "data" / "CL_c_readonly_copy.sqlite3"


def write(db, sql):
    c = sqlite3.connect(db)
    try:
        c.execute(sql)
        c.commit()
        return True
    except sqlite3.DatabaseError:
        return False
    finally:
        c.close()


@unittest.skipUnless(REF.exists(), "reference copy missing")
class Protection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = copy_readonly(REF, Path(self.tmp.name) / "copy.sqlite3")

    def tearDown(self):
        subprocess.run(["chflags", "-R", "nouchg", self.tmp.name], check=False)
        self.tmp.cleanup()

    def test_151_triggers_block_evidence_tampering_and_roll_back_exactly(self):
        before = {r[0] for r in sqlite3.connect(self.db).execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(len(P.apply_triggers(self.db)), len(P.TRIGGER_NAMES))
        self.assertFalse(write(self.db, "INSERT OR REPLACE INTO audit_events SELECT event_id,at,'forged',event,entity,entity_id,payload_json "
                                        "FROM audit_events WHERE event_id=(SELECT min(event_id) FROM audit_events)"))
        self.assertFalse(write(self.db, "UPDATE passages SET text='x' WHERE rowid=1"))
        self.assertFalse(write(self.db, "DELETE FROM documents WHERE rowid=1"))
        self.assertTrue(write(self.db, "UPDATE source_versions SET status=status WHERE rowid=1"))   # status changes stay possible
        self.assertFalse(write(self.db, "INSERT OR REPLACE INTO documents SELECT * FROM documents WHERE rowid=1"))
        self.assertFalse(write(self.db, "UPDATE OR REPLACE passages SET passage_id=(SELECT passage_id FROM passages WHERE rowid=1) WHERE rowid=2"))
        self.assertFalse(write(self.db, "UPDATE OR REPLACE source_versions SET version_id=(SELECT version_id FROM source_versions WHERE rowid=1) WHERE rowid=2"))
        self.assertEqual(len(P.remove_triggers(self.db)), len(P.TRIGGER_NAMES))
        after = {r[0] for r in sqlite3.connect(self.db).execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(after, before)

    def test_152_protected_files_are_never_hardened_or_unhardened_by_code(self):
        for p in (ROOT / "data" / "CL_compliance.sqlite3", ROOT.parent / "CL_compliance_agent_app" / "data" / "CL_compliance.sqlite3"):
            with self.assertRaises(AuthoritativeDatabaseError):
                P.apply_triggers(p)
            with self.assertRaises(AuthoritativeDatabaseError):
                P.remove_triggers(p)

    def test_153_status_is_read_only_and_reports_os_protection(self):
        md5 = hashlib.md5(Path(self.db).read_bytes()).hexdigest()
        os.chmod(self.db, 0o444)
        s = P.status(self.db)
        self.assertEqual((s["mode"], s["owner_writable"], s["journal_mode"], s["side_files"]), ("0o444", False, "delete", []))
        self.assertFalse(write(self.db, "INSERT INTO meta(key,value) VALUES('p','x')"))
        os.chmod(self.db, 0o644)
        if subprocess.run(["chflags", "uchg", str(self.db)]).returncode == 0:
            self.assertTrue(P.status(self.db)["user_immutable"])
            with self.assertRaises(PermissionError):
                os.remove(self.db)
            subprocess.run(["chflags", "nouchg", str(self.db)], check=True)
        self.assertEqual(hashlib.md5(Path(self.db).read_bytes()).hexdigest(), md5)


    def test_163_application_writes_still_work_under_all_triggers_and_typos_create_nothing(self):
        import json
        from compliance_agent import kb as K
        from compliance_agent.clock import FixedClock
        from compliance_agent.engine import Engine
        from compliance_agent.store import Store
        P.apply_triggers(self.db)
        e = Engine(Store(self.db), FixedClock("2026-10-17T10:00:00"))
        k = K.KnowledgeBase(e, ROOT / "data", fetch=lambda u: (_ for _ in ()).throw(K.CollectError("offline")),
                            lock_path=ROOT / "knowledge_base" / "CL_collected_lock.json")
        if (ROOT / "data" / "raw").exists():
            out = k.rebuild(json.loads((ROOT / "knowledge_base" / "CL_source_manifest.json").read_text(encoding="utf-8")))
            self.assertEqual({o["outcome"] for o in out}, {"identical"})
        k.add_interpretations(json.loads((ROOT / "knowledge_base" / "CL_draft_interpretations.json").read_text(encoding="utf-8"))["interpretations"])
        self.assertEqual(e.review_source("FTA-VAT-REG-PAGE@v1", "approve", "Test Reviewer", "qualified reviewer (TEST)", "copy only")["status"], "approved")
        e.s.close()
        with self.assertRaises(FileNotFoundError):
            P.apply_triggers(Path(self.tmp.name) / "typo.sqlite3")
        self.assertFalse((Path(self.tmp.name) / "typo.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
