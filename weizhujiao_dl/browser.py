"""浏览器层：把"点开课件 → 拿预览页 → 抠直链"封装成几个方法。

selenium 全部在方法里 import：没装依赖时 `--help`、单测都不受影响。
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from .errors import DirectLinkMissing, LoginRequired, SelectorLost
from .links import looks_like_direct_link, pick_direct_link
from .models import Courseware
from .naming import filename_from_label
from .selectors import (
    DIRECT_LINK_CSS,
    FIND_LINK_CANDIDATES_JS,
    LOGIN_HINTS,
    PREVIEW_IFRAME_XPATH,
    PREVIEW_MENU_TEXT,
)


def _selenium():
    """集中 import，缺依赖时给一句人话。"""
    try:
        from selenium.common.exceptions import (  # noqa: F401
            NoSuchElementException,
            StaleElementReferenceException,
            TimeoutException,
            WebDriverException,
        )
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 selenium，请执行: pip install -r requirements.txt") from exc
    return {
        "By": By,
        "EC": EC,
        "WebDriverWait": WebDriverWait,
        "TimeoutException": TimeoutException,
        "NoSuchElementException": NoSuchElementException,
        "StaleElementReferenceException": StaleElementReferenceException,
        "WebDriverException": WebDriverException,
    }


def launch_driver(*, headless: bool, user_data_dir: str | None,
                  chrome_binary: str | None, implicit_wait: float) -> object:
    """启动 Chrome：Selenium 4 自带的 Selenium Manager 优先，失败退回 webdriver-manager。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 selenium，请执行: pip install -r requirements.txt") from exc

    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,900")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    if chrome_binary:
        options.binary_location = chrome_binary
    for arg in ("--disable-gpu", "--no-first-run", "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled"):
        options.add_argument(arg)
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])

    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            raise SelectorLost("浏览器启动失败，且没装 webdriver-manager") from None
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                                  options=options)

    driver.implicitly_wait(implicit_wait)
    return driver


@dataclass
class BrowserPage:
    """对 driver 的一层薄封装：只暴露本项目用到的动作，方便替换成假对象做测试。"""

    driver: object
    timeout: float = 20.0

    # ---------------- 基础
    def open(self, url: str) -> None:
        self.driver.get(url)

    def current_url(self) -> str:
        return str(getattr(self.driver, "current_url", "") or "")

    def page_source(self) -> str:
        try:
            return str(self.driver.page_source or "")
        except Exception:
            return ""

    def user_agent(self) -> str:
        try:
            return str(self.driver.execute_script("return navigator.userAgent;") or "")
        except Exception:
            return ""

    def cookies(self) -> dict[str, str]:
        try:
            return {c["name"]: c["value"] for c in self.driver.get_cookies()}
        except Exception:
            return {}

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.driver.quit()

    # ---------------- 列表页
    def wait_courseware(self, xpath: str) -> None:
        """等课件按钮出现；等不到就判断是"没登录"还是"页面改版了"。"""
        se = _selenium()
        By, EC, WebDriverWait = se["By"], se["EC"], se["WebDriverWait"]
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
        except se["TimeoutException"] as exc:
            url = self.current_url().lower()
            source = self.page_source().lower()
            if any(hint in url or hint in source for hint in LOGIN_HINTS):
                raise LoginRequired(
                    "登录态失效了（页面回到了登录/扫码页）。重新登录后重跑，"
                    "或用 --user-data-dir 复用 profile") from exc
            raise SelectorLost(
                f"等了 {self.timeout}s 没等到课件按钮：{xpath}。平台可能改版，请重新 Copy XPath") from exc

    def courseware(self, xpath: str) -> list[Courseware]:
        """读列表：每个按钮的可见文字就是卡片文字。"""
        se = _selenium()
        By, EC, WebDriverWait = se["By"], se["EC"], se["WebDriverWait"]
        elements = WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, xpath)))
        items: list[Courseware] = []
        for idx, el in enumerate(elements, start=1):
            try:
                label = " ".join((el.text or "").split())
            except Exception:  # stale
                label = ""
            items.append(Courseware(index=idx, label=label,
                                    filename=filename_from_label(label)))
        return items

    def locate_courseware(self, item: Courseware, xpath: str):
        """按文字重新定位按钮，避免用旧索引点到别的课件（列表会重排）。"""
        se = _selenium()
        By = se["By"]
        elements = self.driver.find_elements(By.XPATH, xpath)
        if not elements:
            raise SelectorLost("列表里已经没有课件按钮了（页面可能被刷新）")
        if item.label:
            for el in elements:
                try:
                    if " ".join((el.text or "").split()) == item.label:
                        return el
                except Exception:
                    continue
        return elements[min(item.index - 1, len(elements) - 1)]

    # ---------------- 预览页
    def open_preview(self, item: Courseware, xpath: str) -> str:
        """点开课件 →「预览课件」→ 等 iframe，返回（已改 ssl 的）预览页地址。"""
        se = _selenium()
        By, EC, WebDriverWait = se["By"], se["EC"], se["WebDriverWait"]

        button = self.locate_courseware(item, xpath)
        try:
            self.driver.execute_script("arguments[0].click();", button)
        except Exception:
            button.click()

        menu = WebDriverWait(self.driver, self.timeout).until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//*[normalize-space(text())='{PREVIEW_MENU_TEXT}']")))
        try:
            self.driver.execute_script("arguments[0].click();", menu)
        except Exception:
            menu.click()

        iframe = WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.XPATH, PREVIEW_IFRAME_XPATH)))
        src = str(iframe.get_attribute("src") or "")
        if not src:
            raise DirectLinkMissing("预览 iframe 没有 src（可能需要重新点一次预览）")

        preview_url = src.replace("ssl=1", "ssl=0")
        self.open(preview_url)
        return preview_url

    def direct_link_candidates(self) -> list[str]:
        """在预览页里找直链候选：先走已知的 CSS，再扫全页"像链接"的文字，最后扫源码。"""
        candidates: list[str] = []
        se = _selenium()
        By = se["By"]

        try:
            el = self.driver.find_element(By.CSS_SELECTOR, DIRECT_LINK_CSS)
            candidates.append((el.text or "").strip())
        except Exception:
            pass

        try:
            found = self.driver.execute_script(FIND_LINK_CANDIDATES_JS) or []
            candidates.extend(str(x) for x in found)
        except Exception:
            pass

        if not any(looks_like_direct_link(c) for c in candidates):
            candidates.extend(_links_from_source(self.page_source()))

        seen: set[str] = set()
        unique: list[str] = []
        for cand in candidates:
            value = cand.strip()
            if value and value not in seen and looks_like_direct_link(value):
                seen.add(value)
                unique.append(value)
        return unique

    def pick_link(self, filename: str | None):
        """返回最可能的直链；一个都没有就抛 DirectLinkMissing。"""
        best = pick_direct_link(self.direct_link_candidates(), filename)
        if not best:
            raise DirectLinkMissing("预览页没有给出可下载的直链（文档可能只支持在线预览）")
        return best

    # ---------------- 回到列表
    def back_to_list(self, url: str) -> None:
        """能后退就后退（走缓存，比重新 get 快），失败再兜底重新打开列表页。"""
        try:
            self.driver.back()
            if self.current_url().startswith("about:"):
                raise RuntimeError("back 到了空白页")
        except Exception:
            self.open(url)


def _links_from_source(html: str) -> list[str]:
    """从页面源码里捞直链（没有 JS 执行环境时的兜底）。"""
    import re

    pattern = re.compile(r"https?://[^\s\"'<>]{8,}?\.(?:ppt|pptx|pdf|docx?|xlsx?|zip|rar|7z|caj|mp4)",
                         re.IGNORECASE)
    return pattern.findall(html or "")
