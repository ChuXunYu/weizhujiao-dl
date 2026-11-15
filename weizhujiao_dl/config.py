"""配置：命令行 > .env > 环境变量，三层合并后变成一个使用不便出错的 Settings。

不再依赖 `python-dotenv`：自己解析 .env 只有几十行，行为反而更可预测（也更好测）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

ENV_COURSE_URL = "COURSE_LIST_URL"
ENV_BUTTON_XPATH = "COURSE_BUTTON_LOCATOR_XPATH"
ENV_OUT_DIR = "OUT_DIR"
ENV_STATE = "STATE_FILE"

_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def read_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """解析 .env：支持 `KEY=v`、`KEY="v"`、`KEY='v'`、`export KEY=v`、# 注释、空行。

    文件不存在返回空 dict（不报错）—— 允许纯命令行 + 环境变量的用法。
    """
    p = Path(path)
    if not p.is_file():
        return {}

    values: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    course_url: str
    button_xpath: str
    out_dir: Path
    state_file: Path
    limit: int | None = None
    dry_run: bool = False
    headless: bool = False
    user_data_dir: Path | None = None
    chrome_binary: str | None = None
    page_timeout: float = 20.0
    download_timeout: float = 60.0
    delay_min: float = 1.0
    delay_max: float = 2.0
    retries: int = 2
    force: bool = False
    json_out: Path | None = None
    verbose: int = 0
    quiet: bool = False

    @classmethod
    def build(cls, args, environ: dict[str, str] | None = None) -> Settings:
        """把 argparse 结果 + 配置文件 + 环境变量合成一份配置，并做一次集中校验。"""
        env = dict(os.environ if environ is None else environ)
        env.update(read_env_file(getattr(args, "env", ".env")))

        course_url = (getattr(args, "course_url", None) or env.get(ENV_COURSE_URL, "")).strip()
        button_xpath = (getattr(args, "xpath", None) or env.get(ENV_BUTTON_XPATH, "")).strip()
        if not course_url:
            raise ConfigError(
                f"缺少课件列表页地址：在 .env 里填 {ENV_COURSE_URL}，或用 --course-url 传入")
        if not button_xpath:
            raise ConfigError(
                f"缺少课件按钮 XPath：在 .env 里填 {ENV_BUTTON_XPATH}，或用 --xpath 传入")

        out_dir = Path(getattr(args, "out", None) or env.get(ENV_OUT_DIR) or "downloads").expanduser()
        state_file = Path(getattr(args, "state", None) or env.get(ENV_STATE)
                          or out_dir / ".wzd-state.json").expanduser()

        limit = getattr(args, "limit", None)
        if limit is not None and limit <= 0:
            raise ConfigError("--limit 必须是正整数")

        delay_min = float(getattr(args, "delay_min", 1.0))
        delay_max = float(getattr(args, "delay_max", 2.0))
        if delay_min < 0 or delay_max < 0:
            raise ConfigError("--delay-min / --delay-max 不能为负")
        if delay_max < delay_min:
            delay_min, delay_max = delay_max, delay_min

        user_data_dir = getattr(args, "user_data_dir", None)
        json_out = getattr(args, "json", None)

        return cls(
            course_url=course_url,
            button_xpath=button_xpath,
            out_dir=out_dir.resolve(),
            state_file=state_file.resolve(),
            limit=limit,
            dry_run=_as_bool(getattr(args, "dry_run", False)),
            headless=_as_bool(getattr(args, "headless", False)),
            user_data_dir=Path(user_data_dir).expanduser().resolve() if user_data_dir else None,
            chrome_binary=getattr(args, "chrome_binary", None),
            page_timeout=float(getattr(args, "timeout", 20)),
            download_timeout=float(getattr(args, "download_timeout", 60)),
            delay_min=delay_min,
            delay_max=delay_max,
            retries=max(0, int(getattr(args, "retries", 2))),
            force=_as_bool(getattr(args, "force", False)),
            json_out=Path(json_out).expanduser().resolve() if json_out else None,
            verbose=int(getattr(args, "verbose", 0) or 0),
            quiet=_as_bool(getattr(args, "quiet", False)),
        )
