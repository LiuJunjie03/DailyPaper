# DailyPaper 项目指南

## 项目简介

自动化学术论文聚合工具，从 9 个学术数据源（ArXiv、Semantic Scholar、Crossref、OpenAlex、Google Scholar、CNKI、万方、维普、出版商网站）抓取论文，按自定义研究分类标签化，生成静态网站发布到 GitHub Pages。项目聚焦**流体力学/CFD + 机器学习**方向。

## 技术栈

- **语言**: Python 3.10
- **依赖**: `arxiv`, `requests`, `beautifulsoup4`, `lxml`, `PyYAML`, `python-dateutil`, `scholarly`, `pyzotero`
- **部署**: GitHub Pages（`gh-pages` 分支），GitHub Actions 每日自动更新
- **前端**: 纯静态 HTML/CSS/JS（由 `generate_html.py` 生成）

## 项目结构

```
config.yaml                  # 数据源、分类关键词、期刊列表等核心配置
scripts/
  fetch_papers.py            # 主入口：抓取论文，分类并存储为月度 JSON
  generate_html.py           # 读取 JSON 数据，生成 docs/ 下的静态网站
  enrich_metadata.py         # 独立元数据补全脚本（日期、摘要）
  enrich_abstracts.py        # 独立摘要补全脚本
  export_to_zotero.py        # 论文导出到 Zotero
  update_venue.py            # 会议/期刊标签更新工具
  utils.py                   # 共享工具函数（JSON 读写、去重、日期过滤）
  fetchers/                  # 各数据源抓取器模块
    arxiv_fetcher.py         # ArXiv API 客户端
    semantic_scholar.py      # Semantic Scholar API 客户端
    crossref_fetcher.py      # Crossref API 客户端
    openalex_fetcher.py      # OpenAlex API 客户端
    google_scholar.py        # Google Scholar 抓取器
    cnki.py / cnki_detail.py # CNKI 知网抓取器
    chinese_html.py          # 通用中文文献门户框架
    wanfang.py / cqvip.py    # 万方/维普薄封装
    browser.py               # Chrome CDP 自动化工具
  templates/
    main.js                  # 前端 JavaScript 模板
    style.css                # 前端 CSS 模板
data/
  index.json                 # 月份索引
  YYYY-MM.json               # 按月存储的论文数据
docs/                        # GitHub Pages 部署目录（构建产物，不手工编辑）
  index.html                 # 主页（由 generate_html.py 生成）
  data/                      # data/ 的部署副本
  css/, js/                  # 前端资源（由 generate_html.py 生成）
tests/                       # pytest 测试套件
```

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest -q

# 抓取论文（读取 config.yaml）
python scripts/fetch_papers.py

# 生成静态网站
python scripts/generate_html.py
```

## 数据流

1. `fetch_papers.py` → 9 个数据源 API → 去重/合并/分类/补全 → `data/YYYY-MM.json`
2. `generate_html.py` → 读取所有月度 JSON → 生成 `docs/` 下完整静态站点
3. GitHub Actions → 每日 UTC 00:00 自动执行上述两步 → 推送到 `main` 和 `gh-pages`

## 配置说明（config.yaml）

- `sources`: 9 个数据源配置（启用状态、查询词、API 密钥等）
- `categories`: 分类体系（15 个子领域分类）
- `venues`: 用于论文发表渠道识别和影响因子匹配
- `output`: 输出目录配置

## 关键约定

- 论文数据按月存储，文件名格式 `YYYY-MM.json`
- 每条论文记录约 30 个字段，详见 `docs/DATA_SCHEMA.md`（待创建）
- `docs/data/` 是 `data/` 的部署副本，由 `generate_html.py` 同步
- `docs/` 是构建产物，不应手工编辑
- CNKI 代理 URL 通过环境变量 `CNKI_HOME_URL` / `CNKI_KNS_BASE_URL` 配置

## 已知问题

以下问题已知但尚未修复：

- 分类关键词存在交叉重叠（如 ROM、RANS 同时出现在多个分类中），导致误分类
- `fetch_papers.py` 仍承担过多职责（1628 行），计划拆分（见 `IMPROVEMENT_PLAN.md`）
- 三套补全体系（`fetch_papers.py`、`enrich_metadata.py`、`enrich_abstracts.py`）存在逻辑重叠
- 前端 HTML 模板硬编码在 Python f-string 中，未使用模板引擎

## 已修复的问题

- ~~`IMPACT_FACTOR_TABLE` 语法错误~~ — 已修复
- ~~Semantic Scholar API 状态码检查为 `1000`~~ — 已修复为 `200`
- ~~`update_venue.py` 硬编码读取 `data/papers.json`~~ — 已改为处理月度 JSON
- ~~`docs/papers.json` 过期文件~~ — 已移除生成逻辑
- ~~`_needs_crossref_enrichment` 永真条件~~ — 已修复（2026-06-10）
- ~~`extract_paper_keywords` KeyError 风险~~ — 已改用 `.get()` 防御（2026-06-10）
- ~~Semantic Scholar 硬编码年份 "2025"~~ — 已改为动态获取（2026-06-10）
- ~~`main.js` codeLink 不安全赋值~~ — 已删除不安全的第一次赋值（2026-06-10）
- ~~`generate_html.py` authors 字段类型假设错误~~ — 已修复兼容字符串和列表（2026-06-10）
