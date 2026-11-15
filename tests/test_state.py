"""断点状态：记录、原子保存、文件大小校验、force 覆盖。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from weizhujiao_dl.state import STATE_VERSION, StateStore


class TestStateStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / ".wzd-state.json"
        self.target = self.dir / "a.pdf"
        self.target.write_bytes(b"12345")

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_and_reload(self):
        store = StateStore(self.path)
        store.record("a.pdf", 5, "https://h/a.pdf")
        store.save()

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], STATE_VERSION)
        self.assertEqual(payload["files"]["a.pdf"]["size"], 5)

        again = StateStore(self.path).load()
        self.assertTrue(again.is_done("a.pdf", self.target))

    def test_save_is_atomic_no_tmp_left(self):
        store = StateStore(self.path)
        store.record("a.pdf", 5)
        store.save()
        self.assertFalse(self.path.with_suffix(".json.tmp").exists())
        self.assertTrue(self.path.is_file())

    def test_is_done_false_for_unknown(self):
        self.assertFalse(StateStore(self.path).load().is_done("b.pdf", self.target))

    def test_is_done_false_when_size_mismatch(self):
        store = StateStore(self.path)
        store.record("a.pdf", 999)
        self.assertFalse(store.is_done("a.pdf", self.target))

    def test_is_done_false_when_file_gone(self):
        store = StateStore(self.path)
        store.record("a.pdf", 5)
        self.target.unlink()
        self.assertFalse(store.is_done("a.pdf", self.target))

    def test_force_ignores_state(self):
        store = StateStore(self.path)
        store.record("a.pdf", 5)
        self.assertFalse(store.is_done("a.pdf", self.target, force=True))

    def test_forget(self):
        store = StateStore(self.path)
        store.record("a.pdf", 5)
        store.forget("a.pdf")
        self.assertFalse(store.is_done("a.pdf", self.target))

    def test_load_tolerates_broken_json(self):
        self.path.write_text("{ not json", encoding="utf-8")
        store = StateStore(self.path).load()
        self.assertEqual(store.data, {})

    def test_save_skipped_when_clean(self):
        store = StateStore(self.path)
        store.save()
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
