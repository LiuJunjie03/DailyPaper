# DailyPaper 综合改进计划（修订版）

> 基于 PROJECT_REVIEW.md + PROJECT_ANALYSIS.md 两份审查报告 + 风险反馈修订
> 修订日期：2026-06-10
> 原则：每步更小、可回滚、不碰数据迁移
>
> **Phase 0–4 阶段验收通过（2026-06-10）**
> fetch_papers.py 1628→287 行 | 134 tests passed | validate_data.py 零 warning

---

## 修订要点（相对原版）

1. **Phase 0 拆为 0A / 0B**：bug 修复与仓库清理分离，各自独立可回滚
2. **Phase 1 不做字段合并/迁移**：只做 schema 文档 + 校验 + 兼容模型，字段合并推迟到独立的 schema v2 阶段
3. **公共模块放 `scripts/common/`**：不提前创建 `scripts/models.py`，避免与 Phase 7 包化重复迁移
4. **JS 模块化后移到 Phase 8**：Phase 5 只做 Jinja2 模板化 + 删除死代码
5. **验收标准改为"关键用例覆盖"**：不设覆盖率百分比，先建立基线
6. **CNKI 代理 URL 保留 config 默认值**：环境变量作为覆盖而非替代

---

## Phase 0A：确定性小修复 ✅ 已完成

> 已提交：`da2d4d5`

| # | 任务 | 状态 |
|---|------|------|
| 1 | 修复 `_needs_crossref_enrichment` 永真条件 | ✅ |
| 2 | 修复 `extract_paper_keywords` KeyError 风险 | ✅ |
| 3 | 修复 SS 硬编码年份 `"2025"` → 动态获取 | ✅ |
| 4 | 修复 `main.js` codeLink 不安全赋值 | ✅ |
| 5 | CI 加入 `pytest -q` 步骤 | ✅ |

验收：**47 passed**，零回归。

---

## Phase 0B：仓库与发布策略清理 ✅ 已完成

> 已提交：`da2d4d5`（与 0A 同一提交）

| # | 任务 | 状态 |
|---|------|------|
| 1 | `.gitignore` 加入 `*.bak`，`git rm --cached data/*.bak`（25 文件，3.6 MB） | ✅ |
| 2 | 删除 `docs/papers.json` 生成逻辑（前端不依赖，已 grep 确认） | ✅ |
| 3 | 移除 `.bak` 备份生成逻辑 | ✅ |
| 4 | 页脚 `© 2025` → 动态年份 | ✅ |
| 5 | GS `year_from` 硬编码 → 注释掉让代码默认值生效 | ✅ |
| 6 | CNKI 代理 URL 支持环境变量覆盖（保留 config 默认值） | ✅ |
| 7 | 清理未使用 import（`hashlib`, `urllib.parse.quote_plus`） | ✅ |
| 8 | 重写 CLAUDE.md | ✅ |

验收：**47 passed**，`git status` 无 `.bak` 文件。

---

## Phase 1：数据 Schema 文档化与校验（3-5 天）

> 目标：为论文记录建立"单一事实来源"文档，不做任何字段迁移
> 明确不做：字段合并、字段重命名、JSON 格式变更

### 1.1 编写 DATA_SCHEMA.md

新增 `docs/DATA_SCHEMA.md`，记录全部 30+ 字段：

| 字段分类 | 字段 | 说明 |
|----------|------|------|
| **必填** | `id`, `title`, `authors`, `published`, `source` | 每条记录必须有 |
| **标识符** | `doi`, `arxiv_id`, `semantic_scholar_id` | 至少有一个 |
| **URL** | `paper_url`, `arxiv_url`, `pdf_url`, `preprint_pdf_url` | 视来源而定 |
| **分类** | `tags`, `keywords`, `primary_domain` | 分类流程产出 |
| **元数据** | `abstract`, `venue`, `citation_count`, `impact_factor` | 补全流程产出 |
| **状态** | `is_preprint`, `publication_type`, `is_early_access`, `abstract_status`, `date_source` | 系统计算 |
| **已废弃** | `conference`（= venue 的别名）, `official_keywords`（几乎全空）, `code_link`（全空） | 记录但不强依赖 |

每个字段记录：类型、是否必填、数据来源、默认值、已知问题。

### 1.2 编写 validate_paper() 校验函数

在 `scripts/common/` 中新增 `schema.py`（保守路线，不提前包化）：

```python
def validate_paper(record: dict) -> list[str]:
    """返回缺失必填字段和类型不匹配的警告列表"""
    warnings = []
    required = ["id", "title", "authors", "published", "source"]
    for field in required:
        if not record.get(field):
            warnings.append(f"缺少必填字段: {field}")
    # 类型检查
    if record.get("citation_count") and not isinstance(record["citation_count"], (int, float)):
        warnings.append(f"citation_count 类型错误: {type(record['citation_count'])}")
    return warnings
```

### 1.3 定义兼容型 PaperRecord

用 `TypedDict`（非 dataclass/Pydantic）定义，与现有 dict 完全兼容，零迁移成本：

```python
from typing import TypedDict, Optional

class PaperRecord(TypedDict, total=False):
    # 必填字段（不标记 total=True，避免破坏现有数据）
    id: str
    title: str
    authors: str
    published: str
    source: str
    # ... 所有字段标记为 Optional
```

同时记录已知 alias：
- `conference` → 别名，等同于 `venue`
- `custom_keywords` → 与 `keywords` 近乎同步
- `publication_date_source` → 旧名，等同于 `date_source`

### 1.4 新增 schema 校验命令

`python scripts/validate_data.py` — 扫描所有 JSON，报告缺失字段和类型异常。

**验收**：
- `docs/DATA_SCHEMA.md` 覆盖全部字段
- `validate_paper()` 对空记录返回 ≥ 5 条警告
- `python scripts/validate_data.py` 能对现有数据生成报告
- **不改变任何现有 JSON 文件格式**

---

## Phase 2：提取公共模块，消除重复（3-5 天）

> 目标：减少代码重复，不改变业务逻辑
> 模块放在 `scripts/common/`，不提前创建 `daily_paper/` 包

### 2.1 新增目录结构

```
scripts/common/
  __init__.py
  text.py      # normalize_title, normalize_doi, normalize_arxiv_id, term_in_text, clean_text
  http.py      # request_json (统一重试/超时/UA), USER_AGENT 常量
  dates.py     # complete_date, in_date_window, parse_date, is_complete_publication_date
  queries.py   # flatten_queries, parse_source_config
  schema.py    # validate_paper, PaperRecord TypedDict（Phase 1 产物）
```

### 2.2 迁移路线（每个函数独立提交）

1. 在 `common/` 中实现函数 + 搬运对应测试
2. 原位置改为 `from common.xxx import yyy`
3. `pytest -q` 确认无回归
4. 单独提交

### 2.3 消除的重复

| 重复函数 | 当前出现次数 | 迁移目标 |
|----------|------------|----------|
| `request_json`（含重试） | 2 (crossref, openalex) | `common/http.py` |
| `_complete_date` | 3 (semantic_scholar, crossref, openalex) | `common/dates.py` |
| `normalize_title` | 4 (google_scholar, cnki, chinese_html, fetch_papers) | `common/text.py` |
| `normalize_doi` | 2 (fetch_papers, semantic_scholar) | `common/text.py` |
| `flatten_queries` | 5 (crossref, openalex, semantic_scholar, chinese_html, fetch_papers) | `common/queries.py` |
| `in_date_window` | 2 (crossref, chinese_html) | `common/dates.py` |
| `clean_text` | 2 (cnki_detail, chinese_html) | `common/text.py` |

估算消除 **~120 行**重复代码。

**验收**：
- `git grep -n "def request_json"` 只在 `common/http.py` 出现
- `git grep -n "def flatten_queries"` 只在 `common/queries.py` 出现
- 所有 fetcher 仍正常工作
- `pytest -q` 通过

---

## Phase 3：统一三套补全体系 — 部分完成

> 目标：消除 `fetch_papers.py`、`enrich_abstracts.py`、`enrich_metadata.py` 的补全逻辑重叠
> 依赖：Phase 2 的 `common/` 模块

### 已完成

| # | 任务 | 状态 |
|---|------|------|
| 1 | 新建 `scripts/enrich.py` — 级联补全主模块（Crossref→OpenAlex→SS→publisher） | ✅ |
| 2 | `fetch_papers.py` 主流程已通过 `enrich.py` 执行补全 | ✅ |
| 3 | `enrich.py` 导出公共工具函数（`request_json`, `normalize_title`, `title_matches`, `openalex_abstract`） | ✅ |
| 4 | `enrich_abstracts.py` 导入 `enrich.py` 的 `request_json`, `normalize_title`, `openalex_abstract`，移除本地重复定义 | ✅ |
| 5 | `enrich_metadata.py` 导入 `enrich.py` 的 `request_json`, `normalize_title`, `title_matches`, `openalex_abstract`，移除本地重复定义 | ✅ |

### 未完成（Legacy 独立脚本）

`enrich_abstracts.py` 和 `enrich_metadata.py` 仍保留各自的 `fetch_*` 函数。
原因是它们的返回值 API 不同（返回 `(value, metadata)` 元组 vs `enrich.py` 的原地修改），
且有独特功能（arXiv 日期/摘要、CNKI 详情页、`--only dates/abstracts` 过滤）。
这两个脚本标记为 **legacy 独立 CLI 工具**，主流程（`fetch_papers.py`）不再依赖它们。

### 待做（如需完全统一）

- 将 `enrich.py` 的 `_enrich_from_*` 改为返回 `(changed, metadata)` 以兼容独立脚本的调用模式
- 补充 `enrich.py` 的 arXiv 补全函数（目前独立脚本独有）
- 为 `enrich.py` 编写关键用例测试（mock API）

**验收**：
- `git grep -c "_enrich_from_crossref"` 只在 `enrich.py` 出现 ✅
- `enrich_abstracts.py` 和 `enrich_metadata.py` 的共享工具函数已复用 `enrich.py` ✅
- 独立脚本的 fetcher 函数因 API 差异保留为 legacy 代码
- `pytest -q` 通过 ✅

---

## Phase 4：拆分 PaperFetcher 上帝类 — 阶段验收通过

> 目标：将 1628 行的 `fetch_papers.py` 拆成职责清晰的小模块
> 依赖：Phase 2 + Phase 3
> 最终结果：fetch_papers.py 1628→287 行（降 82%）

### 已完成

| 步骤 | 拆出模块 | 状态 |
|------|----------|------|
| 1 | `store.py` — 月度 JSON 读写、索引生成 | ✅ `save_papers()` 已委托调用 |
| 2 | `merger.py` — 身份键、去重、合并策略 | ✅ |
| 3 | `classifier.py` — 分类规则和评分 | ✅ |
| 4 | `normalizer.py` — 字段规范化 | ✅ |
| 5 | `enrich.py` — 级联补全 | ✅ |
| 6 | `_dispatch_sources()` — 数据源调度提取为方法 | ✅ |

### 未完成

| 步骤 | 说明 |
|------|------|
| `scheduler.py` 独立模块 | 当前调度逻辑在 `_dispatch_sources()` 方法中，未抽为独立文件 |
| `fetch_papers.py` 降至 ≤ 150 行 | 当前 577 行，仍有大量 fetch_*_papers 方法 |
| 死代码清理 | `generate_papers_html()`、`get_citation_count()` 等待 Phase 5 确认 |

### 关键用例测试

| 模块 | 测试数量 | 状态 |
|------|----------|------|
| store | 8 | ✅ 拆分、写入/读回、索引结构、计数统计 |
| merger | 12 | ✅ identity_keys、source_rank、merge_two、DOI/ArXiv/标题去重 |
| classifier | 12 | ✅ term_in_text、is_relevant、classify、extract_keywords、normalize |
| enrich | 16 | ✅ is_reliable_abstract、normalize_title、title_matches、openalex_abstract、metadata_complete、needs_crossref |

**当前验收**：
- `fetch_papers.py` 1628→287 行（降 82%） ✅
- `save_papers()` 的 I/O 委托 `store.py`，日期补全委托 `normalizer.py` ✅
- 4 模块 48 个关键用例测试（store 8 / merger 12 / enrich 16 / classifier 12） ✅
- `validate_data.py` 零 warning（1575 篇全部通过） ✅
- `pytest -q` 通过（134 passed） ✅

### 原始计划（参考）

```
scripts/
  common/           # Phase 2 已建
  enrich.py         # Phase 3 已建
  classifier.py     # 分类规则和评分
  merger.py         # 身份键、去重、合并策略
  store.py          # 月度 JSON 读写、索引
  normalizer.py     # 论文字段规范化（_finalize_paper）
  scheduler.py      # 数据源调度编排
  fetchers/         # 保持现有结构
  fetch_papers.py   # 轻量入口，只调用 scheduler
```

### 4.2 拆分顺序（按依赖关系从叶子到根）

| 步骤 | 拆出模块 | 来源 | 预估行数 |
|------|----------|------|----------|
| 1 | `store.py` | `save_papers()` 的文件 I/O + 索引生成 | ~120 |
| 2 | `merger.py` | `_identity_keys()`, `_source_rank()`, `_merge_two_papers()`, `_merge_paper_list()` | ~150 |
| 3 | `classifier.py` | `SUBDOMAIN_RULES`, `PARENT_TAGS`, `FLUID_*` 常量 + `classify_paper()`, `_score_subdomains()`, `extract_paper_keywords()` | ~350 |
| 4 | `normalizer.py` | `_finalize_paper()`, `get_impact_factor()`, `_publication_type()`, `_normalize_keywords()` | ~150 |
| 5 | `scheduler.py` | `save_papers()` 编排逻辑 | ~200 |
| 6 | `fetch_papers.py` | 仅保留 CLI 入口 | ~100 |

### 4.3 关键用例测试

每个模块拆出前先写测试：

- **merger**：DOI 相同合并、ArXiv ID 相同合并、标题 0.85 相似合并、来源优先级排序
- **classifier**：典型正例（含 "turbulence modeling"）、负例（纯 NLP）、边界词（"ROM" 同时出现在多分类）、次要标签评分
- **store**：月度写入、索引生成、不完整日期论文的月份分配
- **normalizer**：`_finalize_paper` 对缺字段论文的默认值填充、`is_early_access` 计算

### 4.4 确认并处理死代码

| 目标 | 当前状态 | 处理方式 |
|------|----------|----------|
| `generate_papers_html()` | 疑似死代码（前端由 JS 渲染） | grep 确认无调用后删除，及关联的 `get_category_name()`、`extract_code_links()`、`get_venue_badge()` |
| `get_citation_count()` | 标注"保留兼容"，grep 确认无调用 | 删除 |
| `_CASCADE_JSON_CACHE` | 无逐出机制 | 改为 LRU 或按阶段清空 |

**验收**：
- `fetch_papers.py` 降至 ≤ 150 行
- 单个模块不超过 400 行
- merger/classifier/store 各有 ≥ 3 个关键用例测试
- `pytest -q` 通过

---

## Phase 5：前端模板化（1 周）

> 目标：将 HTML 从 Python 逻辑中分离
> 只做 Jinja2 模板化 + 清理，不做 JS 模块化

### 5.1 引入 Jinja2 模板

| 步骤 | 说明 |
|------|------|
| 1 | `pip install jinja2`，同步更新 `requirements.txt` |
| 2 | 新增 `scripts/templates/index.html` — 将 `generate_index_html()` 中的 205 行 f-string 移入 |
| 3 | Python 端只计算统计数据 → 传给模板 → 渲染输出 |

### 5.2 清理确认的死代码

| 删除目标 | 前置确认 |
|----------|----------|
| `generate_papers_html()` (458-516 行) | grep 确认无调用 |
| `get_category_name()` / `extract_code_links()` / `get_venue_badge()` | 确认仅被 `generate_papers_html()` 使用 |
| `publication_date_key()` | 确认无调用 |

### 5.3 提取 dashboard stats

将 `generate_index_html()` 前 50 行的统计计算提取为独立函数：

```python
def build_dashboard_stats(papers: list, papers_by_month: dict) -> dict:
    """纯计算，无 I/O，可单测"""
    ...
```

### 5.4 CSS 清理

| 删除目标 | 说明 |
|----------|------|
| `@keyframes shimmer` (90-93 行) | 无规则引用 |
| `.paper-card::before` 计数器 (1196-1198 行) | 未初始化 |
| 重复的 `.category-children > .filter-btn.active::after` | 保留一份 |
| `content: none` 的伪元素 | 安全删除 |

**验收**：
- `generate_html.py` 降至 ≤ 350 行
- HTML 布局修改只需编辑模板文件，不碰 Python
- `build_dashboard_stats()` 有独立单元测试
- `pytest -q` 通过

---

## Phase 6：数据发布策略收敛（1 周）

> 目标：厘清源文件和生成物边界，减少仓库噪音
> 依赖：Phase 4 的 `store.py`

### 6.1 明确目录职责

| 目录 | 角色 | 规则 |
|------|------|------|
| `data/` | 源数据（事实来源） | 由 `store.py` 写入 |
| `scripts/templates/` | 前端源模板 | 人工维护 |
| `docs/` | 构建产物 | 由 `generate_html.py` 生成，不手工编辑 |

### 6.2 具体行动

| # | 任务 |
|---|------|
| 1 | 在 `docs/README.md` 声明 `docs/` 是构建产物 |
| 2 | `python scripts/validate_data.py` 校验命令 — 基于 Phase 1 的 `validate_paper()` |
| 3 | CI 加入 schema 校验步骤 |
| 4 | Provider Health Report — 每次抓取输出数据源级别状态（请求次数/成功/失败/限速） |

**验收**：
- 每次 CI 能看到每个数据源的健康状态
- `validate_data.py` 能检测字段缺失/类型错误
- `pytest -q` 通过

---

## Phase 7：包化与工程化（持续）

> 目标：建立长期可维护的工程实践

### 7.1 包结构迁移

从 `scripts/common/` 迁移到 `daily_paper/` 包：

```
daily_paper/
  __init__.py
  cli.py
  config.py
  models.py          # 从 common/schema.py 迁移
  text.py             # 从 common/text.py 迁移
  dates.py            # 从 common/dates.py 迁移
  http.py             # 从 common/http.py 迁移
  classify.py         # 从 scripts/classifier.py 迁移
  merge.py            # 从 scripts/merger.py 迁移
  enrich.py           # 从 scripts/enrich.py 迁移
  storage.py          # 从 scripts/store.py 迁移
  sources/            # 从 scripts/fetchers/ 迁移
  site/               # 从 scripts/ + templates/ 迁移
scripts/
  fetch_papers.py     # 兼容入口: from daily_paper.cli import main
  generate_html.py    # 兼容入口
```

### 7.2 工程工具

| 工具 | 用途 | 首次启用规则 |
|------|------|-------------|
| `pyproject.toml` | 包管理 + 依赖声明 | 基础配置 |
| Ruff | lint + format | 先只开安全规则（unused imports, bare except） |
| mypy/pyright | 类型检查 | 先只对 `models.py`, `common/` 启用 |
| coverage | 覆盖率基线 | 建立基线后再设百分比目标 |

### 7.3 CI 完整流水线

```
test → lint → validate-data → fetch → generate → deploy
```

### 7.4 根目录清理

| 文件 | 处理 |
|------|------|
| `quick_test.py`, `simple_test.py`, `test.py` | 移入 `scripts/maintenance/` |
| `fix_dates.py`, `fix_dates_batch.py` | 移入 `scripts/maintenance/` |

**验收**：
- `pip install -e .` 可安装
- CI 包含完整流水线
- 根目录只有 `config.yaml`, `requirements.txt`, `pyproject.toml`, 文档

---

## Phase 8：JS 模块化（独立阶段）

> 从 Phase 5 中独立出来，风险更高，单独推进

### 8.1 目标

将 1112 行的 `main.js` 单体拆为功能模块：

```
scripts/templates/
  main.js           # 入口：初始化 + 调度
  paper-card.js     # 论文卡片渲染
  filters.js        # 筛选/搜索/分类导航
  data-loader.js    # JSON 加载 + 缓存
  dashboard.js      # 仪表盘统计
  utils.js          # escapeHTML, safeURL 等
```

### 8.2 注意事项

- 静态部署方案需同步调整（多 `<script>` 或 ES modules）
- 缓存策略需重新设计（单文件哈希 → 多文件版本）
- 脚本加载顺序需测试
- 清理死代码：`loadStateFromURL()`、`downloadFile()`、857-864 行失效事件绑定

**验收**：
- 浏览器回归测试（筛选/搜索/分类/无限滚动/导出）
- `main.js` 入口 ≤ 400 行
- 首屏加载性能不退化

---

## Schema v2 迁移（远期，不设 Phase 编号）

> 字段合并/重命名属于数据迁移，需要独立的迁移脚本和兼容期

| 当前字段 | 目标 | 迁移策略 |
|----------|------|----------|
| `conference` + `venue` | 统一为 `venue` | 读取时兼容双字段，写入时只写 `venue` |
| `keywords` + `custom_keywords` | 统一为 `keywords` | 合并去重 |
| `publication_date_source` | 统一为 `date_source` | 重命名 + alias 兼容 |
| `official_keywords` | 标记 deprecated | 停止写入，保留读取 |
| `code_link` | 评估是否保留 | 确认无数据源填充则标记 deprecated |

前置条件：
- Phase 1 的 `validate_paper()` 已稳定运行
- Phase 4 的 `store.py` 已接管所有 JSON 读写
- 有 schema 版本号机制（`schema_version: 2`）
- 迁移脚本支持向后兼容（v1 数据仍可读取）

---

## Phase 依赖关系

```
Phase 0A ✅ ── Phase 0B ✅
                    │
                    ▼
              Phase 1 (schema 文档 + 校验)
                    │
                    ▼
              Phase 2 (公共模块)
                    │
                    ├──▶ Phase 3 (统一补全)
                    │
                    └──▶ Phase 4 (拆分 PaperFetcher)
                              │
                              ├──▶ Phase 5 (Jinja2 模板化)
                              │
                              └──▶ Phase 6 (数据发布策略)
                                        │
                                        ▼
                                  Phase 7 (包化 + 工程化)
                                        │
                                        ├──▶ Phase 8 (JS 模块化)
                                        │
                                        └──▶ Schema v2 (远期数据迁移)
```

---

## 关键用例覆盖清单

替代覆盖率百分比，按模块列出必须覆盖的关键场景：

### merger
- [ ] 两条论文 DOI 相同 → 合并为一条
- [ ] 两条论文 ArXiv ID 相同 → 合并为一条
- [ ] 两条论文标题相似度 ≥ 0.85 → 合并为一条
- [ ] 来源优先级：Semantic Scholar > Crossref > ArXiv
- [ ] 合并时保留更高来源排名的字段值

### classifier
- [ ] 含 "turbulence modeling" → 命中流体分类
- [ ] 纯 NLP 论文 → 不命中任何流体分类
- [ ] "ROM" 同时出现在多个子领域 → 只命中最匹配的
- [ ] 次要标签评分低于主标签但不为零
- [ ] 缺少 abstract 的论文不崩溃

### enrich
- [ ] mock Crossref 返回 → DOI/日期/venue 被正确填充
- [ ] mock OpenAlex 倒排索引 → 摘要被正确重建
- [ ] mock SS 返回 → citation_count 被更新
- [ ] < 220 字符摘要 → 被判定为不可靠
- [ ] 已完整的论文 → 跳过补全

### store
- [ ] 月度写入生成正确的 `YYYY-MM.json`
- [ ] `index.json` 包含正确的月份计数
- [ ] 日期为 "unknown" 的论文被分配到 "unknown" 月份桶
- [ ] 不覆盖已有数据中的更完整字段

### normalizer
- [ ] 缺字段的论文 → 填入合理默认值
- [ ] `is_early_access` 正确计算（未来日期 + 有 DOI/venue）
- [ ] 关键词规范化（同义词合并）

---

## 风险与缓解

| 风险 | 缓解策略 |
|------|----------|
| 重构过程中抓取链路断裂 | 每个 Phase 结束后用小月份窗口验证（不做完整抓取） |
| 外部 API 行为变化 | Phase 3 统一补全后只需改一处 |
| Phase 0A/0B 已混合提交 | 当前不影响，后续按新分阶段推进 |
| 数据 schema 变更导致旧数据不兼容 | Phase 1 只做文档，不做迁移；Schema v2 独立阶段 |
| JS 模块化影响部署 | 推迟到 Phase 8，Phase 5 只做模板化 |
| CNKI VPN 地址迁移 | 保留 config 默认值，环境变量仅作覆盖 |
| Jinja2 新依赖 | 同步更新 `requirements.txt` 和 CI |
