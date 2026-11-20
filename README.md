# weizhujiao-dl

> 微助教（teachermate）课件批量下载器：**老师没开「允许学生下载」、网页端只给在线预览的课件，也能按原名批量存到本地。**
> 断点续传、直链三级降级重试、登录态复用，配一次就能整门课跑完。

![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078d4)
![python](https://img.shields.io/badge/python-3.9%2B-3776ab)
![tests](https://img.shields.io/badge/tests-87%20offline-4c1)
![license](https://img.shields.io/badge/license-MIT-green)

微助教的课件有「开启」和「允许学生下载」两个开关。老师只开「开启」、关掉「允许学生下载」时，
网页端就只剩「预览课件」，学生没有下载入口——想复习时导不出来的课件，多半就是这个状态。

但「预览」不是拿不到文件：预览是把课件交给 ow365 在线打开，预览页里能拿到指向文件本身的直链，
网页端的「允许学生下载」开关管不到这条直链。这个工具用真实浏览器（带你的登录态）把这条路自动化：
`列表页 →「预览课件」→ ow365 预览页 → 直链`，再用同一份 Cookie 把文件搬回本地，并按课件原名保存。
**没有下载权限、只能在线预览的课件也能下**，这是它和普通「下载器」的区别。

## 特性

- **没有下载权限也能下**：老师没开「允许学生下载」、网页端只给在线预览的课件，照样把原文件存下来——本项目的核心用途
- **批量 + 原名**：`K0002-1-1 Chapter One From C to C++.ppt 已读 Chapter One From C to C++.ppt`
  → `Chapter One From C to C++.ppt`
- **三级降级重试**：无签名直链 → 带签名原始链接 → 按课件名重写 URL（平台给的链接里文件名编码乱：`C++` 的加号被吃掉、空格写法也不对）
- **断点续传**：`downloads/.wzd-state.json` 记着下过什么；中断后重跑自动跳过，`--force` 才会重下
- **原子写**：先落 `.part` 再替换，中途断网不会留下半截 PDF
- **错误页识别**：200 但返回 HTML（登录失效/链接被拒）时直接报错，不会把网页存成 `.pdf`
- **`--dry-run`**：先只识别文件名，确认解析对不对再动手
- **`--json`**：汇总可以导出成 JSON，方便接脚本
- **登录态复用**：`--user-data-dir` 持久化 profile，扫码登录一次就够
- **可测**：87 个离线用例，不联网、不开浏览器、不需要 selenium

## 安装

```bash
git clone https://github.com/ChuXunYu/weizhujiao-dl.git
cd weizhujiao-dl
pip install -r requirements.txt      # selenium / requests / webdriver-manager
```

也可以装成命令（可选）：

```bash
pip install -e .
weizhujiao-dl --version
```

## 配置

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

| 变量 | 说明 |
| --- | --- |
| `COURSE_LIST_URL` | 课件列表页完整地址（含 `courseid`、`openid`）。登录微助教 → 打开「课件」→ 地址栏整段复制 |
| `COURSE_BUTTON_LOCATOR_XPATH` | 课件按钮的 XPath。F12 选中按钮 → 右键 Copy → Copy XPath，形如 `//*[@class='aK9HC-ZsTCNapKFaNj5fN']/button` |
| `OUT_DIR` | 可选，默认 `./downloads` |
| `STATE_FILE` | 可选，默认 `<OUT_DIR>/.wzd-state.json` |

> `openid` 是绑定你微信身份的票据：**不要提交 `.env`、不要发给别人**。重新登录后可能变化，变了就重新复制。

配置来源三层覆盖：**命令行 > `.env` > 系统环境变量**。

## 用法

```bash
python -m weizhujiao_dl --dry-run         # 先看能不能正确认名
python -m weizhujiao_dl                   # 正式下载到 ./downloads
python -m weizhujiao_dl -o D:\课件 --limit 5
python -m weizhujiao_dl --user-data-dir .chrome-profile   # 复用登录态
python -m weizhujiao_dl --headless --user-data-dir .chrome-profile
```

| 参数 | 说明 |
| --- | --- |
| `--course-url` / `--xpath` | 覆盖 `.env` 里的同项配置 |
| `-o, --out DIR` | 保存目录（默认 `./downloads`） |
| `--state PATH` | 断点状态文件路径 |
| `--json PATH` | 把汇总另存 JSON |
| `--limit N` | 只处理前 N 个课件 |
| `--dry-run` | 只识别文件名，不下载 |
| `--force` | 忽略状态文件，已下载的也重下 |
| `--retries N` | 换链接重试上限（默认 2，即最多试 `1+N` 条直链；直链本身最多 3 条） |
| `--delay-min/-max` | 课件之间的随机间隔（默认 1.0–2.0 秒） |
| `--headless` | 无头模式（先有头登录一次并存 profile） |
| `--user-data-dir DIR` | 持久化 Chrome profile |
| `--chrome-binary PATH` | 指定 `chrome.exe` / `msedge.exe` |
| `--timeout N` | 等页面元素的秒数（默认 20） |
| `--download-timeout N` | 单文件下载超时（默认 60） |
| `-q` / `-v` / `-vv` | 少说 / 多说 / 说细节 |
| `--version` | 版本号 |

退出码：`0` 全成；`1` 有失败或被中断；`2` 配置/环境问题。

## 工作原理

微助教的「预览课件」不是自己渲染：它给 ow365（OfficeWeb365）一个 iframe，由 ow365 按拿到的文件直链显示课件。
「允许学生下载」开关只挡住网页端的下载入口，挡不住预览用的这条文件直链——所以**没开下载权限也能下**。

工具把这条路自动化：

```
列表页(登录态) ──点按钮──►「预览课件」菜单 ──► iframe src(ow365.cn)
      ▲                                             │
      │                                        ssl=1 → ssl=0
      │                                             ▼
      └──── 回到列表页 ◄── 逐个处理 ◄── 预览页里的直链候选（CSS → 全页扫 → 源码正则）
                                                  │
                                    三级降级下载 ◄┘  requests + 浏览器 Cookie
```

直链不是每次都能直接用，按下面的顺序降级（`weizhujiao_dl/links.py::link_plan`）：

| 顺序 | 试什么 | 什么时候往下走 |
| --- | --- | --- |
| 1 | 去掉签名参数的无签名直链 | 403（签名被拒）/ 404（名字对不上） |
| 2 | 预览页给的带签名原始链接 | 403 / 404 |
| 3 | 按课件名重写 URL 里的文件名（`C++` → `C%2B%2B`、空格 → `+`） | 失败即记一笔 |

先试无签名直链是故意的：预览页给的链接只是套了层签名参数，剥掉后仍指向同一个文件；
平台对签名挑刺（403）或参数里的文件名和真实文件对不上（404）时，才走后面两级兜底。

一条课件的流程：**认名 → 预览 → 取链 → 降级下载 → 记状态 → 回列表 → 随机间隔**。
任何一步出问题只影响这一条（登录态失效例外：直接停，避免后面全错）。

## 代码结构

```
weizhujiao_dl/
├── cli.py          命令行入口（解析参数 → 建配置 → 起浏览器 → 交给 Runner）
├── config.py       .env/环境变量/命令行 三层合并 + 校验
├── naming.py       从卡片文字认文件名、清成合法文件名（纯函数）
├── links.py        直链判断、候选挑选、剥签名、按名重拼、降级顺序（纯函数）
├── selectors.py    XPath / CSS / JS 常量 —— 平台改版只改这里
├── browser.py      Selenium 封装：列表、预览、抠直链（selenium 延迟 import）
├── downloader.py   原子写、状态码分流、错误页识别（不依赖 requests，鸭子类型）
├── errors.py       异常层次（配置/登录态/选择器/直链/HTTP/网络）
├── state.py        断点续传状态（原子保存）
├── runner.py       单条课件编排 + 降级链
├── report.py       汇总（人话 / JSON）
├── models.py       Courseware / Outcome / Summary
└── net.py          requests 会话（Cookie 搬自浏览器）
tests/              87 个离线用例（含 403→带参、404→改名的完整链路）
```

设计上刻意做的三件事：

1. **纯函数与 IO 分离**：命名、直链、状态这些都是可单测的纯逻辑，浏览器/网络靠注入
2. **selenium/requests 全部延迟 import**：没装依赖也能 `--help`、也能跑单测
3. **选择器集中**：平台改版通常只影响 `selectors.py`（外加 XPath 配置）

## 测试

```bash
python -m unittest discover -s tests -t .    # 87 个用例，~0.1 秒，全程离线
pip install ruff && ruff check .             # 静态检查
```

用例不需要 selenium / requests：`browser.py` 的 selenium 与 `net.py` 的 requests 都是**函数内延迟 import**，
干净环境（只有标准库）就能跑完全部用例。

> 本项目**不接 CI/CD**：没有 GitHub Actions，也不生成发布产物。测试与检查都在本地手动跑，
> 需要什么就 `pip install -r requirements.txt`。这样改一行代码不会被流水线拦着，也不会为了跑测试去联网装浏览器。

覆盖：文件名解析（含已读/未读、编号粘连、中文冒号）、文件名净化（非法字符/超长/Windows 保留名）、
直链挑选与重写、配置三层合并与校验、下载器（原子写、403/HTML/空文件/连接中断）、
状态文件（大小校验、force）、编排链路（成功、跳过、403→带参、404→改名、登录失效中断、dry-run、limit）、
汇总输出。

## 常见问题

**一直等不到课件按钮**
XPath 是改版后第一个废掉的东西。重新 Copy XPath 填进 `.env`；也可能是登录态过期（页面跳到了登录页）。

**全是 403**
签名和当前会话绑定。用同一个 profile 跑（`--user-data-dir`），下载过程中别重新登录。

**老师没开「允许学生下载」，能下吗？**
能，这正是这个工具的主要用途。只要课件还出现在你自己的课件列表里（老师开了「开启」），
「预览课件」就能打开 ow365，工具从预览页取到文件直链后下载；老师开没开「允许学生下载」不影响这一步。

**什么课件下不了？**
预览页里抠不到文件直链的会记 `no-direct-link`（非文档类资源，或平台改版后预览页不再暴露直链）；
被拒/找不到、且三级降级全失败的记 `http-403` / `http-404`。这些只影响那一条，其它课件照下。

**`--headless` 下不来**
先有头扫码登录一次、把登录态写进 profile，再 `--headless --user-data-dir ./.chrome-profile`。
平台对无头 UA 更敏感，被拦就有头跑。

**文件名还是不对**
拿 `--dry-run` 看「文件名」那行；平台卡片文字结构变了的话，改 `naming.py::filename_from_label`，
`tests/test_naming.py` 里有现成用例照着加。

**想确认某一节下全了**
看 `downloads/.wzd-state.json`（每个文件的 size 都记着），或 `--json report.json` 后看 `items`。

## 免责声明

仅用于把自己能查看的课程资料保存到本地做离线复习，**不要传播、不要牟利**。
老师关掉「允许学生下载」通常只是不想课件被扩散——能下不等于可以转发：
不要上传到公开网盘、不要发给别人、不要拿去卖。也请遵守微助教/学校的使用条款，
不要传播他人课件或 `openid`，也不要把 `--delay-min` / `--delay-max` 调到 0 去压平台。见 [LICENSE](LICENSE)。
