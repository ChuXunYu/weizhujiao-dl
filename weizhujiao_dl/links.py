"""直链相关：判断、挑候选、剥签名、按文件名重拼。

预览页给的链接有三种坏法（都实测遇过）：
  1. 带一堆签名参数，去掉才能当"无签名直链"试；
  2. 文件名部分被平台错误编码（`C++` → `C++`、空格变 `+`）；
  3. 参数齐全但文件名与卡片上的名字对不上 → 404。
所以这里只有纯字符串处理，具体怎么试由 runner 的降级链决定。
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote, unquote, urlparse

from .naming import DOC_EXTS

# 平台在 URL 里塞的编号前缀，如 "9cdLn-1693370741604-"
URL_ID_PREFIX = re.compile(r"^[A-Za-z0-9]+-\d{6,}-")


def looks_like_direct_link(text: str | None) -> bool:
    """判断一段文字是不是课件直链（扫预览页用，不依赖任何内联样式）。"""
    if not text:
        return False
    value = text.strip()
    if not value.lower().startswith(("http://", "https://")):
        return False
    return urlparse(value).path.lower().endswith(DOC_EXTS)


def pick_direct_link(candidates: list[str] | None, filename: str | None = None) -> str | None:
    """从候选里挑最像"这一份课件"的直链。

    优先与课件同名（或同扩展名）的那条；都没有就取第一个合法直链。
    """
    links = [c.strip() for c in (candidates or []) if looks_like_direct_link(c)]
    if not links:
        return None

    if filename:
        want_ext = os.path.splitext(filename)[1].lower()
        want_stem = os.path.splitext(filename)[0].lower()
        for link in links:
            stem, ext = os.path.splitext(
                unquote(os.path.basename(urlparse(link).path)).replace("+", " "))
            if ext.lower() == want_ext and want_stem and want_stem in stem.lower():
                return link
        for link in links:
            if os.path.splitext(urlparse(link).path)[1].lower() == want_ext:
                return link

    return links[0]


def strip_query(url: str) -> str:
    """去掉签名参数，先拿它试无签名直链。"""
    return url.split("?", 1)[0]


def rebuild_url(url: str, filename: str | None) -> str:
    """按文件名重写直链的文件名部分。

    例：``.../9cdLn-1693370741604-Chapter One From C to C .ppt``
    → ``.../9cdLn-1693370741604-Chapter+One+From+C+to+C%2B%2B.ppt``

    只认平台那种 ``<字母数字串>-<13 位以上数字>-`` 前缀；认不出就原样返回 ——
    旧实现用 `rfind('-')` 硬切，文件名里带 `-` 时会切错位置，反而把好链接改坏。
    """
    if not filename:
        return url
    parsed = urlparse(url)
    dir_part, _, base = parsed.path.rpartition("/")
    match = URL_ID_PREFIX.match(base)
    if not match:
        return url
    encoded = quote(filename, safe=".").replace("%20", "+")
    new_path = f"{dir_part}/{match.group(0)}{encoded}"
    return parsed._replace(path=new_path).geturl()


def filename_from_url(url: str) -> str:
    """没有课件名时，从 URL 尾部猜一个（先剥掉平台那种 ``9cdLn-1693370741604-`` 前缀）。"""
    from .naming import safe_filename

    # 平台的 URL 用 + 代表空格，而真加号是 %2B：先还原 +，再 unquote，两个才对
    raw_name = os.path.basename(urlparse(url).path).split("?")[0]
    base = unquote(raw_name.replace("+", " "))
    if not base:
        return "download"

    match = URL_ID_PREFIX.match(base)
    if match and base[match.end():]:
        return safe_filename(base[match.end():])
    return safe_filename(base.split("-")[-1] or base)


def link_plan(link: str, filename: str | None) -> list[tuple[str, str]]:
    """降级顺序：无签名直链 → 带签名原始链接 → 按课件名重写文件名。

    返回 [(说明, URL)]，runner 逐条试，遇 403/404 就往下走一条。
    """
    plain = strip_query(link)
    plan: list[tuple[str, str]] = [("无签名直链", plain)]
    if link != plain:
        plan.append(("带签名原始链接", link))
    fixed = rebuild_url(plain, filename)
    if fixed != plain:
        plan.append(("按课件名重写文件名", fixed))
    return plan
