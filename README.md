# DailyPaper - CFD/流体力学论文自动汇总工具

![GitHub Pages](https://img.shields.io/badge/GitHub-Pages-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

每天自动汇总流体力学/CFD + 机器学习领域的最新论文，节省你的检索时间！

## 🎯 功能特点

- ✨ **自动更新**：每天自动抓取最新论文
- 📚 **多源聚合**：支持 ArXiv、顶级会议、期刊等多个数据源
- 🔍 **智能分类**：按研究领域自动分类（多相流、空气动力学、CFD+ML 等）
- 🎨 **美观展示**：响应式网页设计，支持搜索和筛选
- 🔗 **快速访问**：论文原文直接链接

## 📖 支持的数据源

- **ArXiv**：`physics.flu-dyn`（流体动力学）
- **开放学术源**：Crossref、OpenAlex、Semantic Scholar、Google Scholar
- **出版商/索引源**：ScienceDirect、Web of Science / SCI（本地图书馆网络或 API key）
- **中文源**：CNKI、万方、维普（本地浏览器/机构网络可用时启用）
- **重点期刊/会议**：JCP, Physics of Fluids, Journal of Fluid Mechanics, AIAA Journal, NeurIPS, ICML, ICLR, AIAA SciTech Forum 等

## 🚀 快速开始

### 中文期刊与半自动数据库采集

中文流水线每天检查期刊官网，但只在论文首次被系统发现时计入“新增”。来源标注的发表日期和
系统首次发现日期分别保存，避免把半月刊/月刊误解成每日出版。

```powershell
# 只跑公开期刊官网 + imports/chinese 中的人工导出文件
python scripts\collect_chinese_papers.py

# 同时尝试已登录浏览器中的知网、万方和维普
python scripts\collect_chinese_papers.py --portals

# 安装每天北京时间 04:00 的 Windows 任务（错过后自动补跑）
powershell -ExecutionPolicy Bypass -File scripts\install_chinese_task.ps1
```

知网、万方、维普受限时，可把 RIS、EndNote、RefWorks、CSV、XLSX 或保存的 HTML 放入
`imports/chinese/`。程序继续负责解析、去重、智能 CFD 相关性筛选、排序、月度 JSON、中文 Markdown
日报及 GitHub Pages 生成。仓库只保存元数据和全文入口，不保存机构权限 PDF。

期刊选择依据和 15 种中文、15 种英文重点期刊见 [SMART_CFD_JOURNALS.md](SMART_CFD_JOURNALS.md)。

### 本地运行

```bash
# 克隆项目
git clone https://github.com/LiuJunjie03/DailyPaper.git
cd DailyPaper

# 安装依赖
pip install -r requirements.txt

# 运行爬虫
python scripts/fetch_papers.py

# 生成网页
python scripts/generate_html.py
```

### 本地图书馆网络抓取 ScienceDirect / SCI

ScienceDirect 和 Web of Science / SCI 属于“本地机构网络源”：适合在你自己的电脑连接学校图书馆网络或 VPN 后运行，抓到的数据写入 `data/` 和 `docs/data/`，再由你提交到 GitHub。GitHub Actions 默认会跳过这些本地机构源，避免云端 runner 因没有学校网络、登录态或验证码而失败。

#### 完整命令流程（Windows PowerShell）

如果是第一次使用，从克隆、安装到抓取的完整命令如下：

```powershell
# 1. 克隆项目
git clone https://github.com/LiuJunjie03/DailyPaper.git
cd DailyPaper

# 2. 创建并启用虚拟环境
python -m venv .venv

# 如果 PowerShell 阻止激活脚本，先执行这一行
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 4. 连接学校图书馆网络 / VPN 后，启动带 CDP 调试端口的 Edge（推荐）
# Edge 和 Chrome 都是 Chromium 内核，项目都能通过 DevTools Protocol 控制
$browser = "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe"
if (!(Test-Path $browser)) {
  $browser = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
}
& $browser --remote-debugging-port=9222 --user-data-dir="$PWD\outputs\edge-profile-library"

# 如果你的校园网环境下 Chrome 可用，也可以改用 Chrome：
# $browser = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
# & $browser --remote-debugging-port=9222 --user-data-dir="$PWD\outputs\chrome-profile-library"

# 5. 验证浏览器调试端口是否打开；能看到 JSON 即表示正常
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

执行第 4 步后，会打开一个新的 Edge。请在这个 Edge 窗口里手动完成学校图书馆登录，并确认下面两个网站可以打开和检索：

- `https://www.sciencedirect.com/`
- `https://www.webofscience.com/`

保持这个 Edge 窗口不要关闭。然后在另一个 PowerShell 终端继续执行：

```powershell
# 6. 进入项目并启用虚拟环境
cd E:\Dailypaper
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# 7. 可选：如果你有 Clarivate / Web of Science API key，设置后会优先走 API。
# 仅首次执行：保存到当前 Windows 用户环境；新开一个终端后生效。
# 不要把真实 key 写入 config.yaml、.env.example 或 Git。
# [Environment]::SetEnvironmentVariable("WOS_API_KEY", "你的 Clarivate API key", "User")
# 没有 key 可以跳过，程序会尝试使用本地 Edge/Chrome 浏览器路径。

# 8A. 抓取最近 config.yaml 中 days_back 配置范围内的论文
python scripts\fetch_papers.py

# 8B. 或者只补抓某一个月，例如 2026 年 6 月
python scripts\fetch_papers.py --month 2026-06

# 8C. 或者指定任意日期范围
python scripts\fetch_papers.py --start-date 2026-06-01 --end-date 2026-06-30

# 9. 更新期刊/会议信息（可选，失败不会影响主数据）
python scripts\update_venue.py

# 10. 校验数据
python scripts\validate_data.py

# 11. 生成 GitHub Pages 静态网页
python scripts\generate_html.py
```

本地预览网页：

```powershell
# 12. 启动本地预览服务
python -m http.server 8000 -d docs
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

确认没问题后，新开一个 PowerShell 终端提交到 GitHub：

```powershell
# 13. 查看改动
git status

# 14. 暂存数据和网页产物
git add data docs README.md config.yaml daily_paper scripts tests

# 15. 提交
git commit -m "Update papers from local library sources"

# 16. 推送
git push
```

这些日期窗口会传给 ArXiv、Crossref、OpenAlex、Semantic Scholar、万方、维普、ScienceDirect 和 Web of Science。

#### 已经克隆过项目时的最短命令

```powershell
cd E:\Dailypaper
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# 连接学校图书馆网络 / VPN，并保持 9222 Edge/Chrome 已登录
python scripts\fetch_papers.py --month 2026-06
python scripts\validate_data.py
python scripts\generate_html.py

git status
git add data docs
git commit -m "Update papers from local library sources"
git push
```

#### 只启用或关闭本地机构源

默认配置中 `sciencedirect` 和 `webofscience` 是启用的，但只在本地实际抓取；GitHub Actions 会默认跳过。你也可以临时用环境变量控制：

```powershell
# self-hosted runner 或本机中，显式允许所有本地机构源
$env:ENABLE_LOCAL_LIBRARY_SOURCES="true"

# 只允许 ScienceDirect
$env:ENABLE_SCIENCEDIRECT="true"

# 只允许 Web of Science / SCI
$env:ENABLE_WOS="true"
```

推送后 GitHub Pages 会使用你提交的 `docs/` 内容部署。后续 GitHub Actions 自动运行时，默认不会抓 ScienceDirect / Web of Science / SCI，但不会删除你本地已经提交的数据。

#### 常见问题

- **ScienceDirect / Web of Science 抓到 0 篇**：先确认带 `--remote-debugging-port=9222` 的 Edge/Chrome 没关，并且该浏览器窗口里已经通过学校网络登录。
- **出现验证码或安全验证**：手动在 Edge/Chrome 中完成验证后重新运行；如果一直触发，降低 `config.yaml` 中对应源的 `max_results_per_query` 或减少查询词。
- **GitHub Actions 抓不到机构源**：这是预期行为。机构网络源应在本地或 self-hosted runner 上跑；GitHub hosted runner 没有你的学校网络和浏览器登录态。
- **确实想在 self-hosted runner 跑机构源**：设置 `ENABLE_LOCAL_LIBRARY_SOURCES=true`，或分别设置 `ENABLE_SCIENCEDIRECT=true`、`ENABLE_WOS=true`。

### 部署到 GitHub Pages

**快速部署（推荐）：**
```powershell
# 运行一键部署脚本
.\deploy.ps1
```

**手动部署：**
1. 在 GitHub 创建新仓库（名为 `DailyPaper`，Public）
2. 将代码推送到 GitHub
3. 在 Settings > Pages 中配置：Source = `gh-pages` 分支
4. 在 Settings > Actions > General 中配置权限：Read and write
5. 在 Actions 中手动运行 "Update Papers Daily"
6. 访问 `https://liujunjie03.github.io/DailyPaper/`

**详细步骤请查看：[DEPLOYMENT.md](DEPLOYMENT.md)**

## 📁 项目结构

```
DailyPaper/
├── .github/
│   └── workflows/
│       └── update-papers.yml    # GitHub Actions 自动化脚本
├── scripts/
│   ├── fetch_papers.py          # 论文抓取脚本
│   ├── generate_html.py         # 生成静态页面
│   ├── update_venue.py          # 会议/期刊标签更新
│   └── utils.py                 # 工具函数
├── data/
│   ├── index.json               # 月份索引
│   └── YYYY-MM.json             # 按月存储的论文数据
├── docs/                        # GitHub Pages 源文件
│   ├── index.html
│   ├── data/                    # 数据部署副本
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
├── config.yaml                  # 核心配置文件
└── requirements.txt
```

## ⚙️ 配置

编辑 `config.yaml` 文件来自定义：

```yaml
# 抓取配置
sources:
  arxiv:
    enabled: true
    categories:
      - physics.flu-dyn
    max_results: 1000
    days_back: 60

# 领域分类
categories:
  多相流:
    keywords: [multiphase flow, two-phase flow, VOF, ...]
  空气动力学:
    keywords: [aerodynamics, drag reduction, ...]
  CFD与机器学习交叉:
    keywords: [CFD, machine learning, PINN, ...]
  # ...

# 更新频率
schedule:
  cron: "0 0 * * *"  # 每天 UTC 0:00
```

## 📊 数据来源

- [ArXiv](https://arxiv.org/) - 开放获取的预印本论文库

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

感谢所有开源数据源提供者和贡献者！

## ⭐ Star History

如果这个项目对你有帮助，请给个 Star ⭐️
