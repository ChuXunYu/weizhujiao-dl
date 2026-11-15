"""测试替身：假响应、假 requests 会话、假页面。"""
from __future__ import annotations

from weizhujiao_dl.errors import DirectLinkMissing
from weizhujiao_dl.models import Courseware


class FakeResponse:
    def __init__(self, status: int = 200, chunks=(b"x" * 1024,),
                 content_type: str = "application/octet-stream"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self._chunks = list(chunks)
        self.closed = False

    def iter_content(self, chunk_size: int = 8192):
        for chunk in self._chunks:
            yield chunk

    def close(self):
        self.closed = True


class FakeSession:
    """按 URL 路由：值可以是 FakeResponse、Exception 实例，或 `(响应, 备注)`。"""

    def __init__(self, routes: dict[str, object] | None = None):
        self.routes = routes or {}
        self.calls: list[tuple[str, dict]] = []

    def _resolve(self, url: str):
        if url in self.routes:                 # 先精确匹配（避免 "a.pdf" 抢了 "a.pdf?e=1"）
            return self.routes[url]
        for key, value in self.routes.items():
            if key in url:
                return value
        return FakeResponse(status=200)

    def get(self, url, stream=True, headers=None, timeout=None):
        self.calls.append((url, {"stream": stream, "headers": headers or {}, "timeout": timeout}))
        value = self._resolve(url)
        if isinstance(value, Exception):
            raise value
        return value

    @property
    def urls(self) -> list[str]:
        return [c[0] for c in self.calls]


class FakePage:
    """假页面：只实现 Runner 用到的那几个动作。"""

    def __init__(self, items: list[Courseware], link: str | None = "https://h/x.pdf",
                 preview_exc: Exception | None = None):
        self.items = items
        self.link = link
        self.preview_exc = preview_exc
        self.opened: list[str] = []
        self.backs = 0

    def open(self, url):
        self.opened.append(url)

    def wait_courseware(self, xpath):
        return None

    def courseware(self, xpath):
        return self.items

    def open_preview(self, item, xpath):
        if self.preview_exc is not None:
            raise self.preview_exc
        return "https://preview.example/1"

    def pick_link(self, filename):
        if self.link is None:
            raise DirectLinkMissing("预览页没有给出可下载的直链")
        return self.link

    def back_to_list(self, url):
        self.backs += 1

    def cookies(self):
        return {"session": "abc"}

    def user_agent(self):
        return "Mozilla/5.0 test"
