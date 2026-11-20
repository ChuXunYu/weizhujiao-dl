"""微助教（teachermate）课件下载器。

核心用途：老师没开「允许学生下载」、网页端只给在线预览的课件，也能按原名批量保存到本地。

包结构::

    config      .env / 环境变量 / 命令行 三层合并 + 校验
    naming      从卡片文字认文件名、清成合法文件名
    links       直链判断、候选挑选、剥签名、按名字重拼、降级顺序
    selectors   XPath / CSS / JS 常量（平台改版只改这里）
    browser     Selenium 封装：列表、预览、抠直链
    downloader  原子写、状态码分流、错误页识别
    errors      异常层次（配置/登录态/选择器/直链/HTTP/网络）
    state       断点续传状态
    runner      单条课件的编排与降级链
    report      汇总输出（人话 / JSON）
    cli         命令行入口
"""

__version__ = "3.0.0"

__all__ = ["__version__"]
