"""编排：一条课件走完"定位 → 预览 → 取链 → 降级下载 → 记状态"，最后汇总。

这里不 import selenium / requests，只依赖注入进来的 page 与 session，
所以单测可以用假对象把整条链路跑通（含 403→带参、404→改名的降级）。
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Settings
from .downloader import fetch, human_size
from .errors import (
    DirectLinkMissing,
    HttpStatusError,
    LoginRequired,
    NetworkError,
    SelectorLost,
)
from .links import link_plan
from .models import Courseware, Outcome, Reason, Status, Summary
from .state import StateStore

LOG = logging.getLogger("weizhujiao_dl")


@dataclass
class Runner:
    settings: Settings
    page: object                      # BrowserPage 或测试替身
    session: object                   # requests.Session 或测试替身
    state: StateStore
    user_agent: str = ""
    sleep: Callable[[float], None] = time.sleep
    rand: Callable[[float, float], float] = random.uniform
    summary: Summary = field(default_factory=Summary)
    aborted: bool = False

    # ---------------- 主循环
    def run(self) -> Summary:
        started = time.monotonic()
        self.summary.out_dir = str(self.settings.out_dir)
        self.settings.out_dir.mkdir(parents=True, exist_ok=True)

        # 页面由 cli 打开（那里还要提示登录），这里只管"等列表出现"
        self.page.wait_courseware(self.settings.button_xpath)
        items = self.page.courseware(self.settings.button_xpath)
        self.summary.total_found = len(items)
        LOG.info("检测到 %d 个课件%s", len(items),
                 "（dry-run，只识别不下载）" if self.settings.dry_run else "")

        selected = items[: self.settings.limit] if self.settings.limit else items
        if self.settings.limit and self.settings.limit < len(items):
            LOG.info("按 --limit 只处理前 %d 个", len(selected))

        total = len(selected)
        for item in selected:
            if self.aborted:
                break
            LOG.info("")
            LOG.info("[%d/%d] %s", item.index, total, item.display_name)
            outcome = self._process(item)
            self.summary.add(outcome)
            self._log_outcome(outcome)
            self.state.save()

        self.summary.duration_s = time.monotonic() - started
        return self.summary

    # ---------------- 单条
    def _process(self, item: Courseware) -> Outcome:
        name = item.filename or ""
        if not name:
            LOG.debug("卡片文字里没认出文件名，落盘时用直链尾部猜：%s", item.label)

        if self.settings.dry_run:
            return Outcome(item, Status.DRY, detail=name or "")

        target = self.settings.out_dir / name if name else None
        if target is not None and self.state.is_done(name, target, force=self.settings.force):
            return Outcome(item, Status.SKIPPED, Reason.ALREADY_DOWNLOADED,
                           detail=human_size(target.stat().st_size), path=str(target),
                           size=target.stat().st_size)

        try:
            preview_url = self.page.open_preview(item, self.settings.button_xpath)
            link = self.page.pick_link(name or None)
            LOG.debug("直链候选命中: %s", link)
            return self._download(item, link, preview_url, name)
        except LoginRequired as exc:
            self.aborted = True
            return Outcome(item, Status.FAILED, Reason.LOGIN_REQUIRED, detail=str(exc))
        except DirectLinkMissing as exc:
            return Outcome(item, Status.FAILED, Reason.NO_LINK, detail=str(exc))
        except SelectorLost as exc:
            return Outcome(item, Status.FAILED, Reason.SELECTOR, detail=str(exc))
        except KeyboardInterrupt:
            self.aborted = True
            return Outcome(item, Status.FAILED, Reason.INTERRUPTED, detail="用户中断")
        except Exception as exc:  # 兜住单条课件的任何意外，不影响后面
            LOG.debug("处理课件出错", exc_info=True)
            return Outcome(item, Status.FAILED, Reason.UNKNOWN, detail=str(exc))
        finally:
            self._after_each(item)

    def _download(self, item: Courseware, link: str, preview_url: str,
                  name: str) -> Outcome:
        headers = {"Referer": preview_url}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent

        plan = link_plan(link, name or None)
        # --retries 是"再换几条链接"的上限：默认 2 → 最多试 1 + 2 = 3 条，正好覆盖三级降级；
        # 调小可以更快放弃，调大也超不过 plan 本身的条数。
        retries = max(0, int(self.settings.retries or 0))
        limit = min(len(plan), 1 + retries)
        if limit < len(plan):
            LOG.debug("--retries=%d：本课件只试前 %d 条直链（共 %d 条）", retries, limit, len(plan))
        last_error = ""
        attempts = 0

        for label, url in plan[:limit]:
            attempts += 1
            LOG.debug("  尝试[%d] %s: %s", attempts, label, url)
            try:
                transfer = fetch(self.session, url, self.settings.out_dir / self._target_name(name, url),
                                 headers=headers, timeout=self.settings.download_timeout)
            except HttpStatusError as exc:
                last_error = "%s → HTTP %d" % (label, exc.status)
                LOG.debug("  %s", last_error)
                if exc.status in (403, 404) and attempts < limit:
                    continue          # 换下一条 URL 试
                reason = Reason.DENIED if exc.status == 403 else (
                    Reason.NOT_FOUND if exc.status == 404 else Reason.HTTP_ERROR)
                return Outcome(item, Status.FAILED, reason, detail=last_error, attempts=attempts)
            except NetworkError as exc:
                last_error = f"{label} → {exc}"
                return Outcome(item, Status.FAILED, Reason.NETWORK, detail=last_error,
                               attempts=attempts)
            else:
                self.state.record(transfer.path.name, transfer.size, url)
                LOG.info("    已保存 %s（%s，%s）", transfer.path.name,
                         transfer.human_size, label)
                return Outcome(item, Status.OK, path=str(transfer.path),
                               size=transfer.size, attempts=attempts)

        return Outcome(item, Status.FAILED, Reason.HTTP_ERROR,
                       detail=last_error or "全部降级方案都失败", attempts=attempts)

    def _target_name(self, name: str, url: str) -> str:
        if name:
            return name
        from .links import filename_from_url
        return filename_from_url(url)

    # ---------------- 收尾
    def _after_each(self, item: Courseware) -> None:
        if self.settings.dry_run:
            return
        try:
            self.page.back_to_list(self.settings.course_url)
        except Exception:
            LOG.debug("回列表页失败，忽略", exc_info=True)
        delay = self.rand(self.settings.delay_min, self.settings.delay_max)
        if delay > 0:
            LOG.debug("    暂停 %.2fs", delay)
            self.sleep(delay)

    def _log_outcome(self, outcome: Outcome) -> None:
        if outcome.status is Status.OK:
            return
        if outcome.status is Status.SKIPPED:
            LOG.info("    跳过（已下载，%s）", outcome.detail)
        elif outcome.status is Status.DRY:
            LOG.info("    文件名: %s", outcome.detail or "（未识别）")
        else:
            LOG.info("    失败 [%s] %s", outcome.reason, outcome.detail)


def target_path(out_dir: Path, name: str) -> Path:
    """给测试和外部脚本用的便捷函数。"""
    return Path(out_dir) / name
