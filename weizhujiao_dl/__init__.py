"""微助教（teachermate）课件批量下载器。

包结构::

    config      .env / 环境变量 / 命令行 三层合并 + 校验
    naming      从卡片文字认文件名、清成合法文件名
    links       直链判断、候选挑选、剥签名、按名字重拼、降级顺序
    selectors   XPath / CSS / JS 常量（平台改版只改这里）
    browser     Selenium 封装：列表、预览、抠直链
    downloader  原子写、状态码分流、错误页识别
    state       断点续传状态
    runner      单条课件的编排与降级链
    report      汇总输出（人话 / JSON）
    cli         命令行入口
"""

__version__ = "3.0.0"

__all__ = ["__version__"]
