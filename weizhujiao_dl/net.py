"""HTTP 会话：把浏览器 Cookie 搬进 requests，直链下载才不会被当匿名请求打回。

requests 在这里才 import（`--help` 与单测不需要它）。
"""
from __future__ import annotations


def make_session(cookies: dict[str, str] | None = None,
                 user_agent: str | None = None):
    """建一个带浏览器 Cookie 的 requests 会话。"""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 requests，请执行: pip install -r requirements.txt") from exc

    session = requests.Session()
    if user_agent:
        session.headers["User-Agent"] = user_agent
    for name, value in (cookies or {}).items():
        session.cookies.set(name, value)
    return session
