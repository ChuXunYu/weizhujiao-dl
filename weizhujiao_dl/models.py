"""数据结构：课件条目、单条结果、汇总。

刻意保持"哑"：只有字段和方法，不做 IO，方便单测与 `--json` 序列化。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    """一条课件的结局。"""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"
    DRY = "dry-run"

    def __str__(self) -> str:  # 让日志里直接 f"{status}" 可读
        return self.value


class Reason(str, Enum):
    """失败/跳过原因。分类的意义是汇总时能一眼看出"卡在哪一环"。"""

    ALREADY_DOWNLOADED = "already-downloaded"
    LOGIN_REQUIRED = "login-required"
    NO_LINK = "no-direct-link"
    DENIED = "http-403"
    NOT_FOUND = "http-404"
    HTTP_ERROR = "http-error"
    NETWORK = "network-error"
    SELECTOR = "selector-not-found"
    UNSUPPORTED = "unsupported-format"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Courseware:
    """列表里的一个课件卡片。`filename` 为 None 表示没能从卡片文字里认出名字。"""

    index: int          # 1-based，体现在日志的 [i/N]
    label: str          # 卡片原始文字
    filename: str | None

    @property
    def display_name(self) -> str:
        return self.filename or self.label or f"第 {self.index} 个课件"


@dataclass
class Outcome:
    """一个课件的处理结果。"""

    courseware: Courseware
    status: Status
    reason: Reason | None = None
    detail: str = ""
    path: str | None = None
    size: int = 0
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


@dataclass
class Summary:
    """整轮汇总，`--json` 直接吐它的 dict。"""

    outcomes: list[Outcome] = field(default_factory=list)
    out_dir: str = ""
    total_found: int = 0
    duration_s: float = 0.0

    def add(self, outcome: Outcome) -> Outcome:
        self.outcomes.append(outcome)
        return outcome

    def count(self, status: Status) -> int:
        return sum(1 for o in self.outcomes if o.status is status)

    @property
    def downloaded_bytes(self) -> int:
        return sum(o.size for o in self.outcomes if o.ok)

    def failure_breakdown(self) -> dict[str, int]:
        """失败原因 → 条数，按条数倒序。"""
        buckets: dict[str, int] = {}
        for o in self.outcomes:
            if o.status is Status.FAILED:
                key = str(o.reason or Reason.UNKNOWN)
                buckets[key] = buckets.get(key, 0) + 1
        return dict(sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])))

    def to_dict(self) -> dict:
        return {
            "out_dir": self.out_dir,
            "total_found": self.total_found,
            "duration_s": round(self.duration_s, 2),
            "counts": {str(s): self.count(s) for s in Status},
            "downloaded_bytes": self.downloaded_bytes,
            "failures": self.failure_breakdown(),
            "items": [
                {
                    "index": o.courseware.index,
                    "label": o.courseware.label,
                    "filename": o.courseware.filename,
                    "status": str(o.status),
                    "reason": str(o.reason) if o.reason else None,
                    "detail": o.detail,
                    "path": o.path,
                    "size": o.size,
                    "attempts": o.attempts,
                }
                for o in self.outcomes
            ],
        }
