# DailyPaper 项目指南

## 项目简介

自动化学术论文聚合工具，从 ArXiv `physics.flu-dyn` 类别抓取论文，按自定义研究分类标签化，生成静态网站发布到 GitHub Pages。项目聚焦**流体力学/CFD + 机器学习**方向。

## 技术栈

- **语言**: Python 3.10
- **依赖**: `arxiv`, `requests`, `beautifulsoup4`, `lxml`, `PyYAML`, `pandas`, `numpy`
- **部署**: GitHub Pages（`gh-pages` 分支），GitHub Actions 每日自动更新
- **前端**: 纯静态 HTML/CSS/JS（由 `generate_html.py` 生成）

## 项目结构

```
config.yaml                  # 数据源、分类关键词、期刊列表等核心配置
scripts/
  fetch_papers.py            # 从 ArXiv 抓取论文，分类并存储为月度 JSON
  generate_html.py           # 读取 JSON 数据，生成 docs/ 下的静态网站
  utils.py                   # 共享工具函数（JSON 读写、去重、日期过滤）
  update_venue.py            # 会议/期刊标签更新工具（⚠️ 当前不可用）
data/
  index.json                 # 月份索引
  YYYY-MM.json               # 按月存储的论文数据
docs/                        # GitHub Pages 部署目录
  index.html                 # 主页（由 generate_html.py 生成）
  papers.json                # ⚠️ 过期文件，仅含首月数据
  data/                      # data/ 的部署副本
  css/, js/                  # 前端资源（由 generate_html.py 生成）
quick_test.py / simple_test.py / test.py  # 测试脚本
```

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 抓取论文（读取 config.yaml）
python scripts/fetch_papers.py

# 生成静态网站
python scripts/generate_html.py

# 快速测试（抓 10 篇，使用 cs.AI 类别）
python quick_test.py
```

## 数据流

1. `fetch_papers.py` → ArXiv API → 分类 + 标签化 → `data/YYYY-MM.json`
2. `generate_html.py` → 读取所有月度 JSON → 生成 `docs/` 下完整静态站点
3. GitHub Actions → 每日 UTC 00:00 自动执行上述两步 → 推送到 `main` 和 `gh-pages`

## 配置说明（config.yaml）

- `sources.arxiv.categories`: 当前仅 `physics.flu-dyn`
- `categories`: 6 个自定义分类（多相流、空气动力学、机器学习、智能流体力学、流体力学、CFD与机器学习交叉）
- `venues`: 用于论文发表渠道识别和影响因子匹配
- `output.docs_dir`: 生成网站的输出目录

## 关键约定

- 论文数据按月存储，文件名格式 `YYYY-MM.json`
- 每条论文记录包含：`id`, `title`, `authors`（逗号分隔字符串）, `abstract`, `published`, `arxiv_url`, `pdf_url`, `categories`, `conference`, `tags`, `keywords`, `citation_count`, `impact_factor`
- `docs/data/` 是 `data/` 的部署副本，由 `generate_html.py` 同步

## 已知问题

以下问题已知但尚未修复：

- `fetch_papers.py` 第41行：`IMPACT_FACTOR_TABLE` 中有语法错误（孤立的 `''`）
- `fetch_papers.py` 第113行：Semantic Scholar API 状态码检查为 `1000`，应为 `200`，导致引用数据全部为 null
- `update_venue.py`：硬编码读取 `data/papers.json`（不存在），需要适配月度 JSON
- `simple_test.py`：访问不存在的 `updated` 字段，`save_papers()` 调用参数错误
- `docs/papers.json`：过期文件，仅含首月 95 篇数据
- 分类关键词存在交叉重叠（如 ROM、RANS 同时出现在多个分类中），导致误分类
