"""命令行入口：``python -m weizhujiao_dl`` / 安装后的 ``weizhujiao-dl``。

只做四件事：解析参数 → 建配置 → 起浏览器并提示登录 → 交给 Runner 跑完、打印汇总。
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import sys

from . import __version__
from .config import ENV_BUTTON_XPATH, ENV_COURSE_URL, Settings
from .errors import ConfigError, LoginRequired, WzdError
from .models import Status, Summary
from .report import dump_json, print_summary
from .state import StateStore

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weizhujiao-dl",
        description="微助教（teachermate）课件下载器：没有下载权限、只能在线预览的课件也能批量保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m weizhujiao_dl --dry-run            只识别课件名\n"
            "  python -m weizhujiao_dl                      按 .env 配置下载到 ./downloads\n"
            "  python -m weizhujiao_dl -o D:\\课件 --limit 5  只下前 5 个\n"
            "  python -m weizhujiao_dl --user-data-dir .chrome-profile   复用登录态\n"
        ),
    )
    cfg = parser.add_argument_group("配置（也可写进 .env）")
    cfg.add_argument("--course-url", help=f"课件列表页完整地址（.env: {ENV_COURSE_URL}）")
    cfg.add_argument("--xpath", help=f"课件按钮 XPath（.env: {ENV_BUTTON_XPATH}）")
    cfg.add_argument("--env", default=".env", help="配置文件路径（默认 ./.env）")

    out = parser.add_argument_group("输出")
    out.add_argument("-o", "--out", default="downloads", help="保存目录（默认 ./downloads）")
    out.add_argument("--state", help="断点状态文件（默认 <out>/.wzd-state.json）")
    out.add_argument("--json", metavar="PATH", help="把汇总另存为 JSON")
    out.add_argument("-q", "--quiet", action="store_true", help="只输出汇总与错误")
    out.add_argument("-v", "--verbose", action="count", default=0, help="输出更多细节，可叠加 -vv")

    run = parser.add_argument_group("运行")
    run.add_argument("--limit", type=int, help="只处理前 N 个课件")
    run.add_argument("--dry-run", action="store_true", help="只识别课件名，不下载")
    run.add_argument("--force", action="store_true", help="忽略状态文件，已下载的也重下")
    run.add_argument("--retries", type=int, default=2,
                     help="换链接重试上限（默认 2，即最多试 1+N 条直链；直链本身最多 3 条）")
    run.add_argument("--delay-min", type=float, default=1.0, help="课件间隔下限秒（默认 1.0）")
    run.add_argument("--delay-max", type=float, default=2.0, help="课件间隔上限秒（默认 2.0）")

    browser = parser.add_argument_group("浏览器")
    browser.add_argument("--headless", action="store_true", help="无头模式（建议先有头登录一次并存 profile）")
    browser.add_argument("--user-data-dir", help="持久化 Chrome profile 目录，复用登录态")
    browser.add_argument("--chrome-binary", help="指定 chrome.exe / msedge.exe 路径")
    browser.add_argument("--timeout", type=float, default=20.0, help="等页面元素的秒数（默认 20）")
    browser.add_argument("--download-timeout", type=float, default=60.0, help="单文件下载超时秒数（默认 60）")

    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


def _setup_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("weizhujiao_dl")
    logger.handlers.clear()
    level = logging.WARNING if settings.quiet else (
        logging.DEBUG if settings.verbose else logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def _force_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，中文会乱码；统一按 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run(args) -> int:
    try:
        settings = Settings.build(args)
    except ConfigError as exc:
        print(f"配置有误：{exc}", file=sys.stderr)
        print("（跑 `--help` 看说明，或照着 .env.example 填）", file=sys.stderr)
        return EXIT_USAGE

    logger = _setup_logging(settings)

    # 依赖与浏览器都在这里才 import：没装依赖时 --help 仍然能用
    try:
        from .browser import BrowserPage, launch_driver
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    from .net import make_session
    from .runner import Runner

    state = StateStore(settings.state_file).load()
    logger.debug("状态文件: %s（已有 %d 条记录）", settings.state_file, len(state.data))

    driver = None
    summary = Summary()
    try:
        driver = launch_driver(headless=settings.headless,
                               user_data_dir=str(settings.user_data_dir) if settings.user_data_dir else None,
                               chrome_binary=settings.chrome_binary,
                               implicit_wait=3)
        page = BrowserPage(driver=driver, timeout=settings.page_timeout)
        logger.info("打开课件列表: %s", settings.course_url)
        page.open(settings.course_url)

        if not settings.headless and not settings.dry_run:
            input("需要登录的话（微信扫码/短信），登录完成后按回车继续…")

        session = make_session(page.cookies(), page.user_agent())
        runner = Runner(settings=settings, page=page, session=session, state=state,
                        user_agent=page.user_agent())
        summary = runner.run()
    except LoginRequired as exc:
        print(f"登录态失效：{exc}", file=sys.stderr)
        return EXIT_USAGE
    except WzdError as exc:
        print(f"出错了：{exc}", file=sys.stderr)
        return EXIT_PARTIAL
    except KeyboardInterrupt:
        print(f"\n已中断，已下载的文件都在 {settings.out_dir}", file=sys.stderr)
    finally:
        if driver is not None:
            with contextlib.suppress(Exception):
                driver.quit()
        state.save()

    if not summary.outcomes:
        return EXIT_PARTIAL if not summary.total_found else EXIT_OK

    print_summary(summary)
    if settings.json_out:
        dump_json(summary, settings.json_out)
        logger.info("汇总已写入 %s", settings.json_out)

    if summary.count(Status.FAILED):
        return EXIT_PARTIAL
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
