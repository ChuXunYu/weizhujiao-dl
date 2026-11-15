"""把直链落成文件：原子写、状态码分流、错误页识别。

刻意不 import requests：只要求传进来一个"像 requests.Session"的对象
（有 `.get(url, stream=True, headers=..., timeout=...)` 且返回带 `iter_content` /
`status_code` / `headers` 的响应）。这样单测可以用假 session，不用起网络。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import HttpStatusError, NetworkError

CHUNK = 64 * 1024
HTML_TYPES = ("text/html", "application/xhtml")


@dataclass
class Transfer:
    path: Path
    size: int
    url: str
    content_type: str = ""

    @property
    def human_size(self) -> str:
        return human_size(self.size)


def human_size(num: float) -> str:
    """字节数转人话。"""
    if num < 1024:
        return f"{num} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num /= 1024
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}"
    return f"{num:.1f} TB"


def _content_type(resp) -> str:
    headers = getattr(resp, "headers", None) or {}
    try:
        return (headers.get("Content-Type") or "").lower()
    except AttributeError:  # 假响应/异常对象
        return ""


def fetch(session, url: str, target: Path, *,
          headers: dict[str, str] | None = None,
          timeout: float = 60.0,
          chunk: int = CHUNK,
          min_bytes: int = 1) -> Transfer:
    """下载 `url` 到 `target`。

    - 4xx/5xx → `HttpStatusError`（带状态码，让上层决定换 URL 还是放弃）
    - 超时/连接错误 → `NetworkError`
    - 200 但拿到 HTML（登录页/错误页）→ `NetworkError`，避免把网页存成 .pdf

    写法上先落 `.part` 再 `os.replace`，中途挂掉不会留下半截文件。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")

    try:
        try:
            resp = session.get(url, stream=True, headers=headers or {}, timeout=timeout)
        except Exception as exc:  # requests 的各种连接异常
            raise NetworkError(f"请求失败: {exc}") from exc

        try:
            status = int(getattr(resp, "status_code", 200) or 200)
            if status >= 400:
                raise HttpStatusError(status, url)

            ctype = _content_type(resp)
            if any(t in ctype for t in HTML_TYPES) and target.suffix.lower() not in {".html", ".htm"}:
                raise NetworkError(f"拿到的是网页（{ctype}），多半是登录态失效或链接被拒")

            written = 0
            with tmp.open("wb") as fh:
                for block in resp.iter_content(chunk_size=chunk):
                    if block:
                        fh.write(block)
                        written += len(block)
                fh.flush()
                os.fsync(fh.fileno())

            if written < min_bytes:
                raise NetworkError("文件是空的（%d 字节）" % written)
        finally:
            close = getattr(resp, "close", None)
            if callable(close):
                close()

        tmp.replace(target)
        return Transfer(path=target, size=written, url=url, content_type=_content_type(resp))
    except BaseException:
        # 任何失败（含 Ctrl+C）都不留半截文件
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
