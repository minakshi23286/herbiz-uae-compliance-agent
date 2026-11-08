"""Workstream C (16 Oct 2026, founder-approved P5): the kb and backup commands must not write to the authoritative
database. Every test runs on a disposable copy or a temporary folder and checks the authoritative file's md5 is unchanged."""
from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_agent import backup, dbsafety, kb  # noqa: E402

AUTH = dbsafety.AUTHORITATIVE
md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()


def quiet(fn, *args):
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        code = fn(*args)
    return code, out.getvalue() + err.getvalue()


@unittest.skipUnless(AUTH.exists(), "authoritative database not present")
class KbAndBackupNeverWriteAuthoritative(unittest.TestCase):
    def setUp(self):
        self.before = md5(AUTH)
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.ws = self.d / "workspace.sqlite3"
        self.patch = mock.patch.object(dbsafety, "WORKSPACE", self.ws)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()
        self.assertEqual(md5(AUTH), self.before, "the authoritative database changed")

    def test_86_every_kb_command_refuses_the_authoritative_path(self):
        for cmd in ("collect", "rebuild", "setup", "status", "search", "interpret"):
            with self.subTest(cmd=cmd):
                code, out = quiet(kb.main, [cmd, "--db", str(AUTH)])
                self.assertEqual(code, 2)
                self.assertIn("Refused", out)

    def test_87_kb_default_is_the_test_workspace_copy(self):
        code, out = quiet(kb.main, ["status"])
        self.assertEqual(code, 0)
        self.assertIn(str(self.ws), out)
        a = sqlite3.connect(f"file:{AUTH}?mode=ro", uri=True); b = sqlite3.connect(self.ws)
        q = "SELECT COUNT(*) FROM passages"
        self.assertEqual(a.execute(q).fetchone(), b.execute(q).fetchone())
        a.close(); b.close()

    def test_88_kb_collect_needs_explicit_network_approval_and_never_fetches_without_it(self):
        # KnowledgeBase binds http_fetch as a default argument, so patching kb.http_fetch would not stop a real fetch:
        # block the socket-level call instead (found 16 Oct 2026 while documenting the scratch-folder incident).
        with mock.patch.object(kb.urllib.request, "urlopen", side_effect=AssertionError("network used")) as net:
            code, out = quiet(kb.main, ["collect", "--db", str(self.d / "c.sqlite3")])
        net.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("--allow-network", out)
        self.assertFalse((self.d / "c.sqlite3").exists())

    def test_89_links_to_the_authoritative_file_are_recognised(self):
        sym = self.d / "sym.sqlite3"; sym.symlink_to(AUTH)
        self.assertTrue(dbsafety.is_authoritative(sym))
        hard = self.d / "hard.sqlite3"
        try:
            os.link(AUTH, hard)
        except OSError:
            hard = None   # another filesystem: hard links impossible, nothing to check
        if hard:
            self.assertTrue(dbsafety.is_authoritative(hard))
            hard.unlink()
        copy = dbsafety.copy_readonly(AUTH, self.d / "copy.sqlite3")
        self.assertFalse(dbsafety.is_authoritative(copy))
        code, out = quiet(kb.main, ["status", "--db", str(sym)])
        self.assertEqual(code, 2)

    def test_90_restore_refuses_the_authoritative_target_even_with_yes(self):
        b = backup.backup(AUTH, self.d)                    # backup reads the authoritative file only
        code, out = quiet(backup.main, ["restore", str(b), "--db", str(AUTH), "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("Refused", out)
        with self.assertRaises(dbsafety.AuthoritativeDatabaseError):
            backup.restore(b, AUTH, yes=True)

    def test_91_restore_needs_an_explicit_target(self):
        b = backup.backup(AUTH, self.d)
        code, out = quiet(backup.main, ["restore", str(b), "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("explicit --db", out)

    def test_92_restore_into_a_test_copy_works_and_keeps_the_previous_file(self):
        b = backup.backup(AUTH, self.d)
        target = dbsafety.copy_readonly(AUTH, self.d / "target.sqlite3")
        kept = backup.restore(b, target, yes=True)
        self.assertTrue(kept.exists())
        self.assertEqual(backup.verify(target)["counts"], backup.verify(b)["counts"])

    def test_93_backup_never_writes_over_an_earlier_backup(self):
        with mock.patch.object(backup, "stamp", return_value="fixed"):
            backup.backup(AUTH, self.d)
            with self.assertRaises(SystemExit):
                backup.backup(AUTH, self.d)


if __name__ == "__main__":
    unittest.main()
