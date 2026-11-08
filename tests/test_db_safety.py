"""P0 database safety (founder instruction, 16 Oct 2026): demo and evaluation commands must not modify the
authoritative database. Every test compares the authoritative file's md5 before and after."""
from __future__ import annotations

import hashlib
import io
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import dbsafety  # noqa: E402

AUTH = dbsafety.AUTHORITATIVE
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()


@unittest.skipUnless(AUTH.exists(), "authoritative database not present")
class AuthoritativeUnchanged(unittest.TestCase):
    def setUp(self):
        self.before = md5(AUTH)
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "workspace.sqlite3"
        self.patch = mock.patch.object(dbsafety, "WORKSPACE", self.ws)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()
        self.assertEqual(md5(AUTH), self.before, "the authoritative database changed")

    def test_80_default_evaluation_run_uses_workspace_and_leaves_authoritative_unchanged(self):
        from compliance_agent import evaluation
        with redirect_stdout(io.StringIO()) as out:
            code = evaluation.main([])
        self.assertEqual(code, 0)
        self.assertIn(str(self.ws), out.getvalue())
        con = sqlite3.connect(self.ws)
        self.assertGreater(con.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0], 0)
        con.close()

    def test_81_explicit_authoritative_path_is_refused_without_override(self):
        from compliance_agent import evaluation
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(evaluation.main(["--db", str(AUTH)]), 2)
        self.assertIn("Refused", out.getvalue())
        with self.assertRaises(dbsafety.AuthoritativeDatabaseError):
            evaluation.run_all(str(AUTH))

    def test_82_web_app_refuses_authoritative_database(self):
        from compliance_agent import web
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(web.main(["--db", str(AUTH), "--port", "0"]), 2)
        self.assertIn("Refused", out.getvalue())

    def test_83_workspace_is_a_readonly_copy_and_never_the_authoritative_file(self):
        p = dbsafety.ensure_workspace()
        self.assertEqual(p, self.ws)
        self.assertFalse(dbsafety.is_authoritative(p))
        a = sqlite3.connect(f"file:{AUTH}?mode=ro", uri=True); b = sqlite3.connect(p)
        q = "SELECT COUNT(*) FROM audit_events"
        self.assertEqual(a.execute(q).fetchone(), b.execute(q).fetchone())   # audit history carried over, not rewritten
        a.close(); b.close()
        with self.assertRaises(dbsafety.AuthoritativeDatabaseError):
            dbsafety.ensure_workspace(fresh=True, dest=AUTH)


if __name__ == "__main__":
    unittest.main()
