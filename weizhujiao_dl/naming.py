"""命名相关的纯函数：从卡片文字里认文件名、清成合法文件名。

全部无副作用、不碰网络，`tests/test_naming.py` 直接打这些。
"""
from __future__ import annotations

import os
import re

# 认得的课件后缀（决定"哪个词算文件名的结尾"）
DOC_EXTS: tuple[str, ...] = (
    ".ppt", ".pptx", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".txt", ".csv", ".zip", ".rar", ".7z", ".caj", ".mp4",
)

# 卡片文字里的已读标记：真名在标记之后
READ_MARKS: tuple[str, ...] = ("已读", "未读")

# Windows 文件名非法字符（换到别的系统也照样清，宁可保守）
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# 课件编号前缀，如 "K0002-1-1"、"K1234"
ID_PREFIX = re.compile(r"^(K\d+|\d{3,})([-\s]\d+)*[- ]?$")

DEFAULT_NAME = "未命名课件"
MAX_NAME_LEN = 180
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str | None, max_len: int = MAX_NAME_LEN) -> str:
    """清成可落盘的名字：非法字符换下划线、去尾部点与空格、限长保后缀、避开保留名。"""
    # 先折叠空白（含 \t \n），再清非法字符；顺序反了会把换行变成下划线
    text = re.sub(r"\s+", " ", (name or "").strip())
    text = ILLEGAL_CHARS.sub("_", text).strip(" .")

    if len(text) > max_len:
        stem, dot, ext = text.rpartition(".")
        keeps_ext = bool(dot) and 0 < len(ext) <= 8
        text = stem[: max_len - len(ext) - 1] + "." + ext if keeps_ext else text[:max_len]

    if not text:
        return DEFAULT_NAME
    if os.path.splitext(text)[0].upper() in _RESERVED:
        text = "_" + text
    return text


def filename_from_label(label: str | None) -> str | None:
    """从课件卡片文字里抠出文件名。

    卡片实测长这样::

        K0002-1-1 Chapter One From C to C++.ppt 已读 Chapter One From C to C++.ppt
        K0003-1 第三章 线性表.pdf

    规则：找第一个以课件后缀结尾的词当**结尾**，往前取到最后一个「已读/未读」之后；
    没有标记时把开头的课件编号（``K0002-1-1``）剥掉。认不出返回 None。
    """
    parts = (label or "").split()
    if not parts:
        return None

    end = next((i for i, p in enumerate(parts) if p.lower().endswith(DOC_EXTS)), None)
    if end is None:
        return None

    start = 0
    for j in range(end, -1, -1):
        if parts[j] in READ_MARKS:
            start = j + 1
            break

    picked = parts[start:end + 1]
    # 没命中已读标记时，开头多半还挂着课件编号
    while len(picked) > 1 and ID_PREFIX.match(picked[0]) and not picked[0].lower().endswith(DOC_EXTS):
        picked = picked[1:]

    # 编号与名字粘在一起（"K0004-2-3实验报告.docx"）时不硬切，交给 safe_filename 兜住
    return safe_filename(" ".join(picked)) if picked else None
