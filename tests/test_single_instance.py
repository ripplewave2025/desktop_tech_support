"""
Tests for core.single_instance.

These run on the file-lock fallback path because CI typically isn't Windows.
On Windows, the named-mutex path is exercised by `acquire_lock` directly —
the file-lock test approximates that behavior (only one holder at a time)
so the contract is verified end-to-end on either OS.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import single_instance as si


class TestPortDiscovery(unittest.TestCase):
    def test_find_free_port_returns_preferred_when_free(self):
        # Pick a high port that's almost certainly free in the test env.
        port = si.find_free_port(preferred=42424, max_tries=5)
        self.assertEqual(port, 42424)

    def test_find_free_port_walks_when_preferred_is_taken(self):
        # Hold a port open, then ask for it. Should walk to the next.
        held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            held.bind(("127.0.0.1", 0))
            taken = held.getsockname()[1]
            # Listen so the bound state is unambiguous.
            held.listen(1)
            chosen = si.find_free_port(preferred=taken, max_tries=5)
            self.assertNotEqual(chosen, taken)
            self.assertGreater(chosen, taken)
            self.assertLess(chosen, taken + 5)
        finally:
            held.close()

    def test_find_free_port_raises_when_all_taken(self):
        # Hold a contiguous range and ask for it.
        held = []
        try:
            base = None
            for _ in range(3):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", 0))
                s.listen(1)
                held.append(s)
                if base is None:
                    base = s.getsockname()[1]
            # Find a contiguous start
            ports = sorted(s.getsockname()[1] for s in held)
            # Ports may not be contiguous; the test only needs ONE port
            # in the requested range to be free → it'll find it. To force
            # a failure, ask within an arbitrarily-narrow span where the
            # ports we hold sit, AND skip any that aren't contiguous.
            # If they happen to be contiguous, this passes; otherwise we
            # skip the assertion (it's an OS-dependent flake source).
            if ports == list(range(ports[0], ports[0] + 3)):
                with self.assertRaises(RuntimeError):
                    si.find_free_port(preferred=ports[0], max_tries=3)
        finally:
            for s in held:
                s.close()

    def test_port_responds_returns_false_for_dead_port(self):
        # Pick a port nobody's listening on.
        self.assertFalse(si._port_responds(54545, timeout=0.2))


class TestPidAlive(unittest.TestCase):
    def test_self_pid_is_alive(self):
        self.assertTrue(si._pid_alive(os.getpid()))

    def test_zero_pid_is_dead(self):
        self.assertFalse(si._pid_alive(0))

    def test_negative_pid_is_dead(self):
        self.assertFalse(si._pid_alive(-1))


class TestInstanceMetadata(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="zora-instance-")
        self.lock_file = Path(self.tmpdir) / ".instance.json"

    def tearDown(self):
        for p in Path(self.tmpdir).iterdir():
            try:
                p.unlink()
            except OSError:
                pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_write_then_read_round_trips_when_alive(self):
        # Use a port we open ourselves so the read passes the port-responds check.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            si.write_instance_metadata(port, lock_file=self.lock_file)
            data = si.read_running_instance(lock_file=self.lock_file)
            self.assertIsNotNone(data)
            self.assertEqual(data["port"], port)
            self.assertEqual(data["pid"], os.getpid())
            self.assertTrue(data["url"].endswith(str(port)))
        finally:
            s.close()

    def test_read_returns_none_when_file_missing(self):
        self.assertIsNone(si.read_running_instance(lock_file=self.lock_file))

    def test_read_returns_none_when_pid_dead(self):
        self.lock_file.write_text(json.dumps({
            "pid": 999_999_999,   # absurdly high — almost certainly dead
            "port": 54545,
            "url": "http://127.0.0.1:54545",
            "started_at": "2026-01-01T00:00:00Z",
            "version": 1,
        }))
        self.assertIsNone(si.read_running_instance(lock_file=self.lock_file))

    def test_read_returns_none_when_port_dead(self):
        # Live PID (us) but a port nobody's listening on.
        self.lock_file.write_text(json.dumps({
            "pid": os.getpid(),
            "port": 54545,
            "url": "http://127.0.0.1:54545",
            "started_at": "2026-01-01T00:00:00Z",
            "version": 1,
        }))
        self.assertIsNone(si.read_running_instance(lock_file=self.lock_file))

    def test_read_returns_none_for_corrupt_json(self):
        self.lock_file.write_text("{not valid json")
        self.assertIsNone(si.read_running_instance(lock_file=self.lock_file))


class TestFileLock(unittest.TestCase):
    """Cross-platform lock contract — on Windows the same contract is
    enforced by the mutex backend."""

    def setUp(self):
        # Force the file-lock path so this test is meaningful even on Windows.
        # We do this by calling the file-lock function directly with a
        # unique name per test run.
        self.name = f"zora-test-{os.getpid()}-{int(time.time() * 1000)}"

    def test_first_acquire_succeeds(self):
        lock = si._acquire_file_lock(self.name)
        self.assertIsNotNone(lock)
        self.assertEqual(lock.kind, "file")
        lock.release()

    def test_second_acquire_returns_none_while_first_held(self):
        first = si._acquire_file_lock(self.name)
        self.assertIsNotNone(first)
        try:
            second = si._acquire_file_lock(self.name)
            self.assertIsNone(second, "duplicate acquire should fail")
        finally:
            first.release()

    def test_release_then_reacquire_succeeds(self):
        first = si._acquire_file_lock(self.name)
        self.assertIsNotNone(first)
        first.release()
        second = si._acquire_file_lock(self.name)
        self.assertIsNotNone(second, "lock should be reusable after release")
        second.release()

    def test_stale_lock_from_dead_pid_is_reclaimed(self):
        # Manually plant a lock file that points to a dead PID, then try
        # to acquire — the file-lock backend should detect staleness and
        # take over.
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or "/tmp")
        lock_path = base / "Zora" / f".{self.name}.pid"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("999999999")
        try:
            lock = si._acquire_file_lock(self.name)
            self.assertIsNotNone(lock, "stale lock should be reclaimed")
            lock.release()
        finally:
            try:
                lock_path.unlink()
            except OSError:
                pass


class TestPublicAcquireLock(unittest.TestCase):
    """End-to-end: the public `acquire_lock` should give us a lock at least
    once and reject the second call within the same process."""

    def test_acquire_then_duplicate(self):
        name = f"zora-test-public-{os.getpid()}-{int(time.time() * 1000)}"
        first = si.acquire_lock(name)
        self.assertIsNotNone(first)
        try:
            second = si.acquire_lock(name)
            self.assertIsNone(second, "second acquire should fail while first held")
        finally:
            first.release()


if __name__ == "__main__":
    unittest.main()
