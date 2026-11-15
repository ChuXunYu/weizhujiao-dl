# 更新日志

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## 3.0.0 — 2026-11-15

从单文件脚本重写为包，命令行入口与内部结构都变了（破坏性升级）。

### 结构

- `downloader.py`（284 行单文件）→ `weizhujiao_dl/` 包，12 个模块按职责拆分：
  `cli / config / naming / links / selectors / browser / downloader / state / runner / report / models / net`
- 入口改为 `python -m weizhujiao_dl`，另可用 `pip install -e .` 得到 `weizhujiao-dl` 命令
- 新增 `pyproject.toml`（打包 + console script + ruff 配置）
- 新增 `CHANGELOG.md`、`.editorconfig`；`requirements.txt` 精简（去掉 `python-dotenv`）

### 新增能力

- **断点续传**：`downloads/.wzd-state.json` 记录每个文件的 size，重跑自动跳过，`--force` 重下
- **三级降级链**：无签名直链 → 带签名链接 → 按课件名重写 URL（`link_plan()`）
- **原子写**：先 `.part` 再替换，任何失败都不留半截文件
- **错误页识别**：200 + `text/html` 视为登录失效/被拒，不再把网页存成 `.pdf`
- **登录失效快速失败**：检测到跳登录页立刻停，不白等 20 秒 × N 个课件
- **`--dry-run`**：只识别文件名不下载
- **`--json PATH`**：汇总导出 JSON
- **`-q/-v/-vv`**：日志分级
- **`--state` / `--force` / `--retries`**：状态文件位置、强制重下、重试上限
- **登录态复用**：`--user-data-dir` 持久化 Chrome profile

### 修掉的老毛病

- 直链硬等 `div[style='color:red']`：现在 CSS 快速路径 → 全页扫"像链接"的文字 → 源码正则兜底
- 按索引点第 N 个按钮、列表重排就点错：现在先按卡片文字重新定位，找不到才退回索引
- 每个课件都 `driver.get(列表页)` 全量重载：现在优先 `driver.back()`（走缓存），失败才重新打开
- `open(path)` 不关句柄、`except:` 裸捕获、`exit()` 当错误处理：全部改掉
- 文件名直接落盘：现在清非法字符、限长保后缀、避开 Windows 保留名（`CON`/`COM1`…）
- `ChromeDriverManager` 单一依赖：现在优先 Selenium 4 自带 Selenium Manager，失败再退回
- 文件名解析：编号与名字粘连（`K0004-2-3实验报告.docx`）不再被硬切；文件名里带 `-` 也不会被截断

### 测试

- 0 个 → **83 个离线用例**（不联网、不开浏览器、不需要 selenium）
- 覆盖 403→带参、404→改名的完整降级链路，以及原子写、错误页识别、状态校验、登录失效中断、dry-run、limit

## 2.0.0 — 2026-11-15

更名前的一版整理（未单独发布）：仓库 `WeiZhuJiaoDownloads` → `weizhujiao-dl`，
补 README/LICENSE/requirements/.gitignore/.env.example，配置改为 `.env` 可覆盖，`.env` 移出版本库。

## 1.0.0 — 2026-08

首个版本：单文件 `downloader.py`，Selenium 点课件 → ow365 预览页 → 直链 → requests 下载，
文件名从卡片文字里猜，403 时退回带签名链接。
