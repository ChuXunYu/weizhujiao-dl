"""下载器：原子写、状态码分流、错误页识别、失败不留半截文件。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weizhujiao_dl.downloader import fetch, human_size
from weizhujiao_dl.errors import HttpStatusError, NetworkError

from .fakes import FakeResponse, FakeSession

URL = "https://app.teachermate.com.cn/x/abc-123-a.pdf"


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.target = self.dir / "a.pdf"

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_writes_file_and_no_part_left(self):
        session = FakeSession({URL: FakeResponse(chunks=[b"abc", b"def"])})
        result = fetch(session, URL, self.target, headers={"Referer": "r"}, timeout=5)
        self.assertEqual(result.size, 6)
        self.assertEqual(result.path.read_bytes(), b"abcdef")
        self.assertFalse(self.target.with_name("a.pdf.part").exists())

    def test_dir_created(self):
        target = self.dir / "deep" / "nested" / "b.pdf"
        fetch(FakeSession(), URL, target)
        self.assertTrue(target.is_file())

    def test_http_error_raises_with_status(self):
        session = FakeSession({URL: FakeResponse(status=403)})
        with self.assertRaises(HttpStatusError) as ctx:
            fetch(session, URL, self.target)
        self.assertEqual(ctx.exception.status, 403)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.target.with_name("a.pdf.part").exists())

    def test_html_body_rejected(self):
        session = FakeSession({URL: FakeResponse(content_type="text/html; charset=utf-8")})
        with self.assertRaises(NetworkError):
            fetch(session, URL, self.target)
        self.assertFalse(self.target.exists())

    def test_html_allowed_for_html_target(self):
        target = self.dir / "page.html"
        session = FakeSession({URL: FakeResponse(content_type="text/html")})
        fetch(session, URL, target)
        self.assertTrue(target.is_file())

    def test_empty_body_rejected(self):
        session = FakeSession({URL: FakeResponse(chunks=[])})
        with self.assertRaises(NetworkError):
            fetch(session, URL, self.target)
        self.assertFalse(self.target.exists())

    def test_transport_error_becomes_network_error(self):
        session = FakeSession({URL: TimeoutError("timed out")})
        with self.assertRaises(NetworkError):
            fetch(session, URL, self.target)

    def test_partial_file_cleaned_on_second_chunk_failure(self):
        class Boom:
            status_code = 200
            headers = {"Content-Type": "application/pdf"}

            def iter_content(self, chunk_size=8192):
                yield b"half"
                raise RuntimeError("连接被重置")

            def close(self):
                pass

        with self.assertRaises(RuntimeError):
            fetch(FakeSession({URL: Boom()}), URL, self.target)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.target.with_name("a.pdf.part").exists())

    def test_passes_headers_and_timeout(self):
        session = FakeSession()
        fetch(session, URL, self.target, headers={"Referer": "r", "User-Agent": "ua"}, timeout=7)
        self.assertEqual(session.calls[0][1]["headers"], {"Referer": "r", "User-Agent": "ua"})
        self.assertEqual(session.calls[0][1]["timeout"], 7)
        self.assertTrue(session.calls[0][1]["stream"])


class TestHumanSize(unittest.TestCase):
    def test_units(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(999), "999 B")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(human_size(3 * 1024 ** 3), "3.0 GB")


if __name__ == "__main__":
    unittest.main()
