"""汇总输出：默认人话表格，`--json` 给机器读。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .downloader import human_size
from .models import Status, Summary

_ICON = {
    Status.OK: "✔",
    Status.SKIPPED: "–",
    Status.FAILED: "✘",
    Status.DRY: "·",
}


def summary_lines(summary: Summary) -> list[str]:
    """把 Summary 变成要打印的行（纯文本，方便单测断言）。"""
    ok = summary.count(Status.OK)
    skipped = summary.count(Status.SKIPPED)
    failed = summary.count(Status.FAILED)
    dry = summary.count(Status.DRY)

    lines = ["", "==== 汇总 ===="]
    lines.append("课件总数: %d | 成功 %d | 跳过 %d | 失败 %d%s"
                 % (summary.total_found, ok, skipped, failed,
                    " | 只识别 %d" % dry if dry else ""))
    if ok:
        lines.append(f"本次下载: {human_size(summary.downloaded_bytes)}")
    if summary.duration_s:
        lines.append(f"耗时: {summary.duration_s:.1f}s")
    lines.append("保存目录: %s" % (summary.out_dir or "-"))

    breakdown = summary.failure_breakdown()
    if breakdown:
        lines.append("失败分类:")
        for reason, count in breakdown.items():
            lines.append("  - %-22s %d" % (reason, count))
        lines.append("（失败条目已列在上面，重跑会自动跳过已完成的）")

    if dry:
        lines.append("")
        lines.append("dry-run 识别到的文件名:")
        for outcome in summary.outcomes:
            if outcome.status is Status.DRY:
                lines.append(f"  {_ICON[Status.DRY]} {outcome.detail or outcome.courseware.label}")
    return lines


def print_summary(summary: Summary, stream=None) -> None:
    stream = stream or sys.stdout
    for line in summary_lines(summary):
        print(line, file=stream)


def dump_json(summary: Summary, path: Path | None = None, stream=None) -> str:
    payload = json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload, file=stream or sys.stdout)
    return payload
