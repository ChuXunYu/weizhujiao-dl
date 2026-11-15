"""汇总输出：人话摘要与 JSON 结构。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from weizhujiao_dl.models import Courseware, Outcome, Reason, Status, Summary
from weizhujiao_dl.report import dump_json, summary_lines


def make_summary() -> Summary:
    summary = Summary(out_dir="D:\\课件", total_found=3, duration_s=12.34)
    summary.add(Outcome(Courseware(1, "K1 a.pdf 已读 a.pdf", "a.pdf"), Status.OK,
                        path="D:\\课件\\a.pdf", size=2048, attempts=1))
    summary.add(Outcome(Courseware(2, "K2 b.pdf", "b.pdf"), Status.SKIPPED,
                        Reason.ALREADY_DOWNLOADED, detail="2.0 KB"))
    summary.add(Outcome(Courseware(3, "K3 c.pdf", "c.pdf"), Status.FAILED,
                        Reason.DENIED, detail="无签名直链 → HTTP 403", attempts=3))
    return summary


class TestSummaryLines(unittest.TestCase):
    def test_counts_line(self):
        lines = "\n".join(summary_lines(make_summary()))
        self.assertIn("课件总数: 3 | 成功 1 | 跳过 1 | 失败 1", lines)
        self.assertIn("本次下载: 2.0 KB", lines)
        self.assertIn("耗时: 12.3s", lines)
        self.assertIn("保存目录: D:\\课件", lines)

    def test_failure_breakdown(self):
        lines = "\n".join(summary_lines(make_summary()))
        self.assertIn("失败分类:", lines)
        self.assertIn("http-403", lines)

    def test_dry_run_section(self):
        summary = Summary(out_dir="x", total_found=1)
        summary.add(Outcome(Courseware(1, "K1 a.pdf", "a.pdf"), Status.DRY, detail="a.pdf"))
        lines = "\n".join(summary_lines(summary))
        self.assertIn("dry-run 识别到的文件名", lines)
        self.assertIn("· a.pdf", lines)

    def test_no_failure_section_when_clean(self):
        summary = Summary(out_dir="x", total_found=1)
        summary.add(Outcome(Courseware(1, "a.pdf", "a.pdf"), Status.OK, size=1))
        self.assertNotIn("失败分类", "\n".join(summary_lines(summary)))


class TestJson(unittest.TestCase):
    def test_to_dict_shape(self):
        payload = make_summary().to_dict()
        self.assertEqual(payload["counts"]["ok"], 1)
        self.assertEqual(payload["counts"]["failed"], 1)
        self.assertEqual(payload["failures"], {Reason.DENIED.value: 1})
        self.assertEqual(payload["downloaded_bytes"], 2048)
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items"][2]["reason"], "http-403")

    def test_dump_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "report.json"
            dump_json(make_summary(), path)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["total_found"], 3)
        self.assertEqual(data["items"][0]["filename"], "a.pdf")


if __name__ == "__main__":
    unittest.main()
