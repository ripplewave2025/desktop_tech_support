"""
Tests for core.crash_reporter.

Covers:
  * Hook installation (idempotency)
  * Crash dump round-trip
  * Retention pruning
  * Path-traversal rejection
  * Support bundle ZIP integrity
  * Log tail handling (large file, missing file)
  * RotatingFileHandler attachment + deduplication
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import crash_reporter as cr


def _raise_and_capture():
    """Trigger an exception and return the (type, value, tb) triple."""
    try:
        raise ValueError("boom from test")
    except ValueError:
        return sys.exc_info()


class TestInstall(unittest.TestCase):
    def setUp(self):
        cr._reset_for_tests()
        self._original_excepthook = sys.excepthook

    def tearDown(self):
        cr._reset_for_tests()
        sys.excepthook = self._original_excepthook

    def test_install_is_idempotent(self):
        cr.install_crash_handlers(version="test")
        first_hook = sys.excepthook
        cr.install_crash_handlers(version="test")
        # Second install should be a no-op — same hook, no further wrapping.
        self.assertIs(sys.excepthook, first_hook)

    def test_install_replaces_excepthook(self):
        cr.install_crash_handlers(version="test")
        self.assertIsNot(sys.excepthook, self._original_excepthook)


class TestWriteAndPrune(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="zora-crash-"))

    def tearDown(self):
        for f in self.tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def test_write_crash_round_trip(self):
        exc_type, exc_value, tb = _raise_and_capture()
        path = cr.write_crash(exc_type, exc_value, tb,
                              version="9.9", crash_dir=self.tmpdir)
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "9.9")
        self.assertEqual(data["exception_type"], "ValueError")
        self.assertEqual(data["exception_message"], "boom from test")
        self.assertIn("Traceback", data["traceback"])
        self.assertIn("boom from test", data["traceback"])

    def test_prune_keeps_only_latest_n(self):
        # Write 5 crash dumps with deliberate mtime ordering.
        for i in range(5):
            exc_type, exc_value, tb = _raise_and_capture()
            p = cr.write_crash(exc_type, exc_value, tb,
                               version=f"v{i}", crash_dir=self.tmpdir)
            # Force distinct mtimes so the sort order is deterministic.
            os.utime(p, (time.time() - (5 - i), time.time() - (5 - i)))
        # Confirm we have 5 before pruning.
        self.assertEqual(len(list(self.tmpdir.glob("*.json"))), 5)
        cr._prune(self.tmpdir, retain=2)
        survivors = sorted(self.tmpdir.glob("*.json"))
        self.assertEqual(len(survivors), 2)

    def test_prune_with_zero_retain_is_noop(self):
        for _ in range(3):
            exc_type, exc_value, tb = _raise_and_capture()
            cr.write_crash(exc_type, exc_value, tb, crash_dir=self.tmpdir)
        cr._prune(self.tmpdir, retain=0)
        self.assertEqual(len(list(self.tmpdir.glob("*.json"))), 3)


class TestListAndRead(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="zora-crash-"))

    def tearDown(self):
        for f in self.tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def test_list_returns_summaries_newest_first(self):
        # Write two crashes and force distinct mtimes.
        et, ev, tb = _raise_and_capture()
        a = cr.write_crash(et, ev, tb, crash_dir=self.tmpdir)
        os.utime(a, (time.time() - 100, time.time() - 100))
        et, ev, tb = _raise_and_capture()
        b = cr.write_crash(et, ev, tb, crash_dir=self.tmpdir)
        os.utime(b, (time.time(), time.time()))

        summaries = cr.list_crashes(crash_dir=self.tmpdir)
        self.assertEqual(len(summaries), 2)
        # Newest (b) comes first.
        self.assertEqual(summaries[0]["filename"], b.name)

    def test_read_crash_returns_dict_for_valid_file(self):
        et, ev, tb = _raise_and_capture()
        path = cr.write_crash(et, ev, tb, crash_dir=self.tmpdir)
        data = cr.read_crash(path.name, crash_dir=self.tmpdir)
        self.assertIsNotNone(data)
        self.assertEqual(data["exception_type"], "ValueError")

    def test_read_crash_rejects_path_traversal(self):
        for bad in ("../passwd", "..\\..\\evil.json", "/etc/shadow",
                    "C:\\Windows\\system.json", "/abs.json", ""):
            self.assertIsNone(cr.read_crash(bad, crash_dir=self.tmpdir),
                              f"traversal not blocked: {bad!r}")

    def test_read_crash_rejects_non_json_extension(self):
        # Even if a filename is otherwise safe, only .json is accepted.
        (self.tmpdir / "innocent.txt").write_text("not a crash")
        self.assertIsNone(cr.read_crash("innocent.txt", crash_dir=self.tmpdir))

    def test_delete_crash_rejects_path_traversal(self):
        for bad in ("../passwd", "..\\evil.json"):
            self.assertFalse(cr.delete_crash(bad, crash_dir=self.tmpdir))

    def test_delete_crash_removes_existing(self):
        et, ev, tb = _raise_and_capture()
        path = cr.write_crash(et, ev, tb, crash_dir=self.tmpdir)
        self.assertTrue(cr.delete_crash(path.name, crash_dir=self.tmpdir))
        self.assertFalse(path.exists())


class TestSupportBundle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="zora-crash-"))
        self.log_path = self.tmpdir / "zora.log"
        self.log_path.write_text("first log line\nsecond log line\nfinal log line\n",
                                 encoding="utf-8")

    def tearDown(self):
        for f in self.tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def test_bundle_contains_crash_and_log_tail(self):
        et, ev, tb = _raise_and_capture()
        crash_path = cr.write_crash(et, ev, tb, crash_dir=self.tmpdir)
        bundle = cr.build_support_bundle(
            crash_path.name,
            crash_dir=self.tmpdir,
            log_path=self.log_path,
            output_dir=self.tmpdir,
        )
        self.assertIsNotNone(bundle)
        self.assertTrue(bundle.exists())
        with zipfile.ZipFile(str(bundle)) as zf:
            names = set(zf.namelist())
            self.assertIn(crash_path.name, names)
            self.assertIn("zora.log.tail.txt", names)
            log_tail = zf.read("zora.log.tail.txt").decode("utf-8")
            self.assertIn("final log line", log_tail)

    def test_bundle_returns_none_for_traversal_attempt(self):
        self.assertIsNone(cr.build_support_bundle("../etc/passwd",
                                                  crash_dir=self.tmpdir))

    def test_bundle_returns_none_for_missing_crash(self):
        self.assertIsNone(cr.build_support_bundle("does-not-exist.json",
                                                  crash_dir=self.tmpdir))


class TestTailLog(unittest.TestCase):
    def test_returns_friendly_message_when_log_missing(self):
        text = cr._tail_log(Path("/definitely/nonexistent/zora.log"), 10)
        self.assertIn("no log file", text.lower())

    def test_tails_only_last_n_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False, encoding="utf-8") as f:
            for i in range(1000):
                f.write(f"line {i}\n")
            path = Path(f.name)
        try:
            tail = cr._tail_log(path, 10)
            lines = tail.splitlines()
            self.assertEqual(len(lines), 10)
            self.assertEqual(lines[-1], "line 999")
            self.assertEqual(lines[0], "line 990")
        finally:
            path.unlink()


class TestLogRotation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="zora-log-"))
        # Snapshot root logger handlers so we can restore.
        self._original_handlers = list(logging.getLogger().handlers)

    def tearDown(self):
        # Detach any handlers we added.
        root = logging.getLogger()
        for h in list(root.handlers):
            if h not in self._original_handlers:
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass
        for f in self.tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            self.tmpdir.rmdir()
        except OSError:
            pass

    def test_attach_creates_handler_and_writes(self):
        log_path = self.tmpdir / "zora.log"
        handler = cr.attach_rotating_log(log_path=log_path,
                                         max_bytes=1024, backups=2)
        self.assertIsInstance(handler, logging.handlers.RotatingFileHandler)
        logging.getLogger().info("hello rotating")
        handler.flush()
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("hello rotating", text)

    def test_attach_is_idempotent_per_path(self):
        log_path = self.tmpdir / "zora.log"
        h1 = cr.attach_rotating_log(log_path=log_path)
        h2 = cr.attach_rotating_log(log_path=log_path)
        self.assertIs(h1, h2, "second attach to same path should reuse handler")


if __name__ == "__main__":
    unittest.main()
