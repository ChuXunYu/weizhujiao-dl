"""异常层次。

分成"用户能自己修"（配置/登录态）和"这一条课件过不去"（选择器丢了、直链没给出来）两类，
命令行据此给出不同退出码，汇总时也能直接映射成 `Reason`。
"""
from __future__ import annotations


class WzdError(Exception):
    """本项目所有可预期异常的基类。"""


class ConfigError(WzdError):
    """配置缺失或写错：用户改 .env / 参数就能修。"""


class LoginRequired(WzdError):
    """登录态失效（跳回登录页 / 拿不到课件列表）。"""


class SelectorLost(WzdError):
    """页面结构变了：等待的元素没出现。"""


class DirectLinkMissing(WzdError):
    """预览页没给出课件直链（格式不支持、或需要重新预览）。"""


class HttpStatusError(WzdError):
    """下载返回 4xx/5xx。带上状态码，好让上层决定"换 URL 重试"还是"放弃"。"""

    def __init__(self, status: int, url: str) -> None:
        super().__init__("HTTP %d: %s" % (status, url))
        self.status = status
        self.url = url


class NetworkError(WzdError):
    """超时、连接被重置之类的传输层问题。"""
