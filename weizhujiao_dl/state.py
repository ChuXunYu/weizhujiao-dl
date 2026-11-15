"""断点续传状态：记录"哪些课件已经下过"，让重跑/中断恢复不用从头来。

存在 `downloads/.wzd-state.json`（可用 --state 改），和产物同目录，删了就等于清空缓存。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

STATE_VERSION = 1


@dataclass
class StateStore:
    path: Path
    data: dict = field(default_factory=dict)
    dirty: bool = False

    # ---------------- 读写
    def load(self) -> StateStore:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict) and isinstance(raw.get("files"), dict):
            self.data = raw["files"]
        else:  # 兼容空文件/旧格式
            self.data = {}
        return self

    def save(self) -> None:
        if not self.dirty:
            return
        payload = {"version": STATE_VERSION, "files": self.data}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self.path)
        self.dirty = False

    # ---------------- 查询/记录
    def record(self, filename: str, size: int, url: str = "") -> None:
        self.data[filename] = {"size": size, "url": url, "at": int(time.time())}
        self.dirty = True

    def forget(self, filename: str) -> None:
        if self.data.pop(filename, None) is not None:
            self.dirty = True

    def is_done(self, filename: str, target: Path, force: bool = False) -> bool:
        """已下过且文件还在、大小对得上才算完成。`force=True` 一律重下。"""
        if force:
            return False
        entry = self.data.get(filename)
        if not isinstance(entry, dict):
            return False
        if not target.is_file():
            return False
        expected = entry.get("size")
        return expected is None or target.stat().st_size == expected
