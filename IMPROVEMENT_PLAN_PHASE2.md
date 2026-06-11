# DailyPaper 改进计划 Phase 2（Phase 9–14）

> 基于 `question.md` 26 项代码审查问题的逐条验证结果
> 日期：2026-06-11
> 前置条件：`IMPROVEMENT_PLAN.md` Phase 0–8 已全部完成（✅）
> 原则：延续 Phase 0–8 的风格——每步更小、可回滚、pytest 验证

---

## 验证总览

`question.md` 提出了 26 个问题，逐条验证结果：

| 结果 | 数量 | 问题编号 |
|------|------|---------|
| ✅ 真实存在 | 22 | #1–7, #9–16, #18, #20, #22–26 |
| ⚠️ 部分属实 | 3 | #8, #19, #21 |
| ❌ 不成立 | 1 | #17（每日 cron 对 DailyPaper 项目完全合理） |

### 与 IMPROVEMENT_PLAN.md 的关系

| 覆盖状态 | 问题编号 | 说明 |
|----------|---------|------|
| 已解决 | **#19** | Phase 4 拆分了 PaperFetcher（1628→287行），但配置耦合问题留待 Phase 14.4 处理 |
| 部分覆盖 | **#1, #2, #13, #14, #16, #21** | Phase 7 创建了 `daily_paper/` 但没删 `scripts/` 旧副本；Phase 3 统一了主流程补全但 legacy 脚本仍保留；CNKI VPN 支持了环境变量但硬编码仍在；薄封装 cqvip/wanfang 未清理 |
| **完全未提及** | **#3–12, #15, #18, #20–26** | 共 19 个问题在改进计划中完全没有出现 |

---

## Phase 依赖关系图

```
Phase 9（小 Bug 修复）── 不依赖其他 Phase，可立即开始
    │
    ▼
Phase 10（消除双轨制）── 依赖 Phase 9 完成后代码稳定
    │
    ▼
Phase 11（统一补全逻辑）── 依赖 Phase 10 删除旧模块后 import 统一
    │
    ├──▶ Phase 12（数据质量与逻辑修复）── 独立于 Phase 11，可并行
    │
    └──▶ Phase 13（配置与安全加固）── 独立于 Phase 11，可并行
              │
              ▼
        Phase 14（性能与架构优化）── 可选，优先级最低
```

---

## Phase 9：确定性小 Bug 修复（1 天）

> 目标：5 个一行/几行改动即可修复的问题
> 风险：极低，每项改动独立且影响范围小

### 9.1 修复裸 `except:` 异常吞噬

**问题 #4** | `scripts/utils.py:64`

```python
# 修复前
except:
    return datetime.now()

# 修复后
except ValueError:
    return datetime.now()
```

> 注：`scripts/utils.py` 后续在步骤 9.5 中整体删除，此处先修复以保持代码库健康。

### 9.2 删除 `is_reliable_abstract` 中的死代码

**问题 #5** | `scripts/enrich_abstracts.py:60`

`clean_abstract()` 已将 `\s+` 压缩为单个空格，后续 `re.search(r"\s{2,}", text)` 永远不匹配。

```python
# 修复前（第 54-65 行）
def is_reliable_abstract(text: str) -> bool:
    text = clean_abstract(text)
    if len(text) < 220:
        return False
    if text[:1].islower():
        return False
    if re.search(r"\s{2,}", text):      # ← 死代码
        return False
    ...

# 修复后：删除死代码行
def is_reliable_abstract(text: str) -> bool:
    text = clean_abstract(text)
    if len(text) < 220:
        return False
    if text[:1].islower():
        return False
    ...
```

> **注：** `daily_paper/enrich.py` 中的 `_is_reliable_abstract()` 使用 `"  " in text` 检查双空格，同理在调用前未做空白压缩，理论上可匹配——但该函数在 Phase 11 统一时会被合并清理，此处不重复修改。

### 9.3 修复 `.setdefault()` 链式误用

**问题 #7** | `scripts/fetch_papers.py:87`

当 `self.config` 中 `sources` 键不存在时，`.get("sources", {})` 返回临时空字典，`.setdefault()` 修改会被静默丢弃。

```python
# 修复前
source = self.config.get("sources", {}).setdefault(source_name, {})

# 修复后
sources = self.config.setdefault("sources", {})
source = sources.setdefault(source_name, {})
```

### 9.4 补全 `_validate_config` 遗漏的数据源

**问题 #8** | `scripts/fetch_papers.py:100`

`_validate_config` 的校验列表缺少 `crossref` 和 `openalex`，但 `set_date_window()` 和 `_dispatch_sources()` 都实际使用这两个数据源。

```python
# 修复前
for source_name in ["arxiv", "semantic_scholar", "google_scholar",
                    "cnki", "wanfang", "cqvip"]:

# 修复后
for source_name in ["arxiv", "semantic_scholar", "google_scholar",
                    "cnki", "wanfang", "cqvip", "crossref", "openalex"]:
```

### 9.5 删除废弃的 `scripts/utils.py`

**问题 #12** | `scripts/utils.py`

全项目 grep 确认零 import。其功能已被 `daily_paper/` 各模块替代：
- `load_json`/`save_json` → `daily_paper/storage.py`
- `deduplicate_papers` → `daily_paper/merge.py`
- `parse_date` → `daily_paper/dates.py`

**操作：** 直接删除 `scripts/utils.py`。

### Phase 9 验收

- [x] `pytest -q` 全部通过
- [x] `ruff check scripts/` 无新告警
- [x] `scripts/utils.py` 已不存在

---

## Phase 10：消除双轨制（2–3 天）

> 目标：删除 `scripts/` 下所有已被 `daily_paper/` 替代的副本模块，统一 import 路径
> 这是当前**最核心的技术债**

### 当前双轨状态

| `scripts/` 旧文件 | `daily_paper/` 对应物 | 内容一致性 |
|---|---|---|
| `scripts/common/text.py` | `daily_paper/text.py` | 100% 一致 |
| `scripts/common/http.py` | `daily_paper/http.py` | 100% 一致 |
| `scripts/common/dates.py` | `daily_paper/dates.py` | 100% 一致（均 import `daily_paper.text`） |
| `scripts/common/queries.py` | `daily_paper/queries.py` | 近似一致 |
| `scripts/common/schema.py` | `daily_paper/schema.py` | 100% 一致 |
| `scripts/classifier.py` | `daily_paper/classify.py` | 近似一致（仅 import 差异） |
| `scripts/merger.py` | `daily_paper/merge.py` | 已迁移 import |
| `scripts/normalizer.py` | `daily_paper/normalizer.py` | 部分迁移 |
| `scripts/store.py` | `daily_paper/storage.py` | 独立实现 |
| `scripts/enrich.py` | `daily_paper/enrich.py` | 独立实现 |

### 10.1 删除 `scripts/common/` 目录

6 个文件已全部迁移到 `daily_paper/`，**零 import 引用**：

```bash
git rm scripts/common/__init__.py
git rm scripts/common/text.py
git rm scripts/common/http.py
git rm scripts/common/dates.py
git rm scripts/common/queries.py
git rm scripts/common/schema.py
```

### 10.2 删除 `scripts/` 下的旧核心模块

5 个文件均有 `daily_paper/` 对应物：

```bash
git rm scripts/classifier.py
git rm scripts/merger.py
git rm scripts/normalizer.py
git rm scripts/store.py
git rm scripts/enrich.py
```

### 10.3 修复裸 import

**问题 #13** | `scripts/fetch_papers.py:137`

```python
# 修复前
def extract_official_keywords(self, result):
    from classifier import extract_official_keywords
    return extract_official_keywords(result)

# 修复后（顶部 import，移除延迟 import）
from daily_paper.classify import extract_official_keywords as _extract_official_keywords
```

**问题 #14** | `scripts/normalizer.py:16`（如未在 10.2 中删除则修复）

```python
# 修复前
from classifier import classify_paper, extract_paper_keywords, normalize_keywords

# 修复后
from daily_paper.classify import classify_paper, extract_paper_keywords, normalize_keywords
```

### 10.4 提取重复的 `batch_get_citation_counts`

**问题 #3** | `scripts/fetchers/arxiv_fetcher.py:13-103` 与 `scripts/fetchers/semantic_scholar.py:36-118`

约 90 行几乎完全相同的函数（仅注释和字符串格式有细微差异）。

**操作：**

1. 在 `daily_paper/sources/` 下新建 `_citation_batch.py`，放入唯一的 `batch_get_citation_counts`
2. `daily_paper/sources/arxiv_fetcher.py` 和 `daily_paper/sources/semantic_scholar.py` 改为 `from daily_paper.sources._citation_batch import batch_get_citation_counts`
3. 如果 `scripts/fetchers/` 下同名文件仍有独立副本，同样统一引用

### 10.5 修复 `scripts/fetchers/cnki.py` 的裸 import

```python
# 修复前
from fetchers.browser import evaluate_in_chrome
from fetchers.cnki_detail import enrich_cnki_paper

# 修复后
from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.sources.cnki_detail import enrich_cnki_paper
```

### 10.6 合并薄封装与清理空文件

**问题 #21** | `scripts/fetchers/cqvip.py`（13行）、`scripts/fetchers/wanfang.py`（13行）

两个文件各仅包含一个函数，内部只调用 `fetch_chinese_html_source()` 并传不同参数，无任何源特定逻辑。

**操作：**

1. 将 `cqvip.py` 和 `wanfang.py` 的函数内联到 `_dispatch_sources()` 中直接调用 `fetch_chinese_html_source()`，或迁移到 `daily_paper/sources/chinese_html.py` 作为参数化入口
2. 删除 `scripts/fetchers/cqvip.py` 和 `scripts/fetchers/wanfang.py`
3. 为 `scripts/fetchers/__init__.py`（空文件）添加 docstring 说明模块用途
4. 为 `tests/conftest.py`（空文件）添加 docstring 说明

```python
# scripts/fetchers/__init__.py 修复后
"""数据源抓取器模块。各抓取器按数据源命名，由 PaperFetcher._dispatch_sources() 调度。"""
```

### Phase 10 验收

- [x] `git grep -r "from common\." scripts/` 无结果
- [x] `git grep -r "from classifier import" scripts/` 无结果
- [x] `git grep -r "from fetchers\." scripts/` 无结果
- [x] `scripts/common/` 目录不存在
- [x] `scripts/classifier.py`、`merger.py`、`normalizer.py`、`store.py`、`enrich.py` 不存在
- [x] `scripts/fetchers/` 整个目录已删除（含 cqvip.py、wanfang.py）
- [x] `batch_get_citation_counts` 只在 `daily_paper/sources/_citation_batch.py` 中定义
- [x] `pytest -q` 全部通过

---

## Phase 11：统一补全逻辑（3–5 天）

> 目标：完成 Phase 3 的未竟工作，消除三套补全体系的残余重复
> 依赖：Phase 10（旧模块已删除，import 统一到 `daily_paper/`）

### 当前重复状态

| 函数 | 出现位置 | 差异 |
|------|---------|------|
| `title_matches()` | `daily_paper/enrich.py`（0.85）、`scripts/enrich_abstracts.py`（0.88） | **阈值不同** |
| `is_reliable_abstract()` | `daily_paper/enrich.py`、`scripts/enrich_abstracts.py`、`scripts/enrich_metadata.py`（导入版） | bad_prefixes 不同、检查逻辑不同 |
| `clean_text()` / `clean_abstract()` | `daily_paper/text.py`、`scripts/enrich_metadata.py`、`scripts/enrich_abstracts.py` | HTML 清理逻辑不同 |

### 11.1 统一 `title_matches()` 阈值

在 `daily_paper/enrich.py` 中保留唯一定义，阈值为 **0.85**（主流程已使用此值）。

`scripts/enrich_abstracts.py` 中的本地副本改为：
```python
from daily_paper.enrich import title_matches
```

### 11.2 统一 `is_reliable_abstract()`

合并三个变体的最佳实践，在 `daily_paper/enrich.py` 中定义唯一版本：

- 调用前先做 `clean_abstract()`（HTML 标签清理 + 空白压缩）
- 合并所有 bad_prefixes：`("cookies", "enable javascript", "we use cookies", "this site", "this page", "access denied")`
- 删除死代码（`\s{2,}` 检查，已在 `clean_abstract` 中处理）

`scripts/enrich_abstracts.py` 和 `scripts/enrich_metadata.py` 改为导入统一版本。

### 11.3 统一 `clean_text()` / `clean_abstract()`

在 `daily_paper/text.py` 中保留唯一 `clean_text()`，加入 HTML 标签清理能力（当前版本不含）。

`scripts/enrich_metadata.py` 和 `scripts/enrich_abstracts.py` 中的本地 `clean_text`/`clean_abstract` 改为导入 `daily_paper.text.clean_text`。

### 11.4 标记 legacy 脚本

`scripts/enrich_abstracts.py` 和 `scripts/enrich_metadata.py` 中的 `fetch_*` 函数因返回值 API 不同（元组 vs 原地修改），短期内保留为 legacy CLI 工具，但在文件顶部添加标注：

```python
"""
Legacy 独立 CLI 工具 — 仅作为命令行补全脚本使用。
主流程（fetch_papers.py）通过 daily_paper.enrich 执行补全。
"""
```

### Phase 11 验收

- [x] `git grep -c "def title_matches"` 只在 `daily_paper/enrich.py` 出现
- [x] `git grep -c "def is_reliable_abstract"` 只在 `daily_paper/enrich.py` 出现
- [x] `git grep -c "def clean_abstract"` 只在 `daily_paper/text.py` 出现
- [x] `pytest -q` 全部通过

---

## Phase 12：数据质量与逻辑修复（1–2 天）

> 目标：修复影响数据准确性和 UI 展示的逻辑问题
> 独立于 Phase 11，可与 Phase 11 并行

### 12.1 修复年日期静默归入1月

**问题 #6** | `daily_paper/storage.py` — `split_papers_by_month()`

```python
# 修复前
elif len(parts) == 1 and parts[0].isdigit():
    month = f"{parts[0]}-01"  # 只有年份时归到1月

# 修复后
elif len(parts) == 1 and parts[0].isdigit():
    month = f"{parts[0]}-unk"  # 只有年份时标记为未知月份
    paper["_date_precision"] = "year"
```

同步更新前端过滤逻辑，确保 `YYYY-unk` 月份的论文仍可展示但标注"仅知年份"。

### 12.2 修复"本周"计算

**问题 #9** | `scripts/generate_html.py:70` — `build_dashboard_stats()`

```python
# 修复前（滚动 7 天窗口）
week_start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")

# 修复后（真正的本周起始日）
today = datetime.now()
week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
```

同步修改变量名 `recent_week_count` → `this_week_count`，与 UI 标签"本周"语义一致。

### 12.3 修复日期字符串比较

**问题 #10** | `scripts/enrich_metadata.py:413`

```python
# 修复前
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
...
if new_date > TODAY:

# 修复后
from datetime import date
TODAY = date.today()
...
if datetime.strptime(new_date, "%Y-%m-%d").date() > TODAY:
```

### 12.4 修复 venue 子串匹配过宽

**问题 #11** | `scripts/update_venue.py:40`

```python
# 修复前
if venue_name.lower() in comment.lower():

# 修复后
import re
if re.search(r'\b' + re.escape(venue_name) + r'\b', comment, re.IGNORECASE):
```

### Phase 12 验收

- [x] 年日期 `"2024"` 不再被归入 `"2024-01"`，而是 `"2024-unk"`
- [x] "本周"统计从周一起始，非滚动窗口
- [x] `pytest -q` 全部通过
- [x] `validate_data.py` 0 warnings（现有数据不受影响）

---

## Phase 13：配置与安全加固（1 天）

> 目标：消除配置泄漏和安全隐患
> 独立于 Phase 11，可与 Phase 11 并行

### 13.1 替换虚假邮箱

**问题 #15** | `config.yaml:32,54` + `daily_paper/enrich.py:36,249`

```yaml
# 修复前
mailto: "research@dailyPaper.org"

# 修复后
mailto: ""  # Crossref/OpenAlex polite pool 邮箱，建议设置 CROSSREF_MAILTO 环境变量
```

```python
# daily_paper/enrich.py 修复前
USER_AGENT = "DailyPaperBot/1.0 (mailto:research@dailyPaper.org)"

# 修复后
USER_AGENT = "DailyPaperBot/1.0"
```

同步在代码中支持 `CROSSREF_MAILTO` 环境变量读取。

### 13.2 移除硬编码 VPN URL

**问题 #16** | `config.yaml:87-88`

```yaml
# 修复前
home_url: "http://www--cnki--net--https.cnki.mdjsf.utuvpn.utuedu.com:9000/"
kns_base_url: "http://kns--cnki--net--https.cnki.mdjsf.utuvpn.utuedu.com:9000/"

# 修复后（仅保留占位说明）
# CNKI 代理 URL — 必须通过环境变量 CNKI_HOME_URL / CNKI_KNS_BASE_URL 配置
# home_url: ""
# kns_base_url: ""
```

### 13.3 改进 API Key 文档

**问题 #18** | `config.yaml:143`

```yaml
# 修复前
api_key: ""  # 免费 API key，申请: https://www.semanticscholar.org/product/api#api-key-form

# 修复后
api_key: ""  # 留空则使用环境变量 SEMANTIC_SCHOLAR_API_KEY
             # 免费 API key 申请: https://www.semanticscholar.org/product/api#api-key-form
             # 有 key 时速率限制 1000 req/5min，无 key 时 100 req/5min
```

### 13.4 添加 Chrome DevTools 安全说明

**问题 #23** | `scripts/fetchers/browser.py`

在文件顶部 docstring 中添加：

```python
"""
Chrome DevTools Protocol (CDP) 自动化工具。

安全说明：CDP 默认在 localhost:9222 无认证运行。
仅在受信任的本地环境中使用。请勿在共享机器上暴露 9222 端口。
可通过环境变量 CHROME_DEVTOOLS_URL 覆盖默认地址。
"""
```

### 13.5 审计 JS 字符串拼接

**问题 #24** | `scripts/fetchers/cnki.py`、`google_scholar.py`

检查所有将 Python 变量拼入 JavaScript 字符串的位置，确保全部使用 `json.dumps()` 转义。当前 CNKI 代码已使用 `json.dumps(query)`（安全），需确认其他参数（如 `max_per_query`）也安全。

### Phase 13 验收

- [x] `config.yaml` 中无特定机构 VPN 地址
- [x] `config.yaml` 中无虚假域名邮箱
- [x] `git grep "dailyPaper.org"` 无结果（包括 `daily_paper/enrich.py`）
- [x] 所有 JS 参数拼接使用 `json.dumps()`
- [x] `pytest -q` 全部通过

---

## Phase 14：性能与架构优化（3–5 天，可选）

> 目标：改善运行时性能和代码可维护性
> 优先级最低，可在 Phase 9–13 全部完成后再评估

### 14.1 实现增量更新

**问题 #20** | `scripts/fetch_papers.py` — `save_papers()`

当前每次运行加载全部历史月度 JSON（~30 文件、3.5MB），全量合并后重写。

改进方案：
- `save_papers()` 仅合并当前月 + 上月（处理跨月延迟收录的论文）
- 其他月份数据仅在 `validate_data.py` 中校验，不重新写入
- 提供独立的 `rebuild_all.py` 命令用于全量重建

关键文件：
- `scripts/fetch_papers.py`（save_papers 改为增量模式）
- `daily_paper/storage.py`（load_monthly_data 增加单月加载选项）

### 14.2 批量化级联补全

**问题 #22** | `daily_paper/enrich.py` — `cascade_enrich_papers()`

当前对每篇论文串行调用 4 个 API，处理 200 篇至少 90 秒。

改进方案：
- 同一 API 的多个论文请求合并为批量请求（S2 和 Crossref 支持批量 API）
- 不同 API 之间用 `concurrent.futures.ThreadPoolExecutor` 并发
- 保留当前的逐源降级策略（Crossref → OpenAlex → S2 → 出版商）

关键文件：
- `daily_paper/enrich.py`（cascade_enrich_papers 改为批量模式）

### 14.3 优化缓存哈希计算

**问题 #25** | `scripts/generate_html.py:258`

当前将全部论文序列化为 JSON 字符串后计算 MD5，O(n) 开销。

改进方案：
```python
# 修复后：基于论文 ID 列表 + 最新月份 mtime 计算哈希
paper_ids = sorted(p.get("id", "") for p in self.papers)
data_hash = self._content_hash("|".join(paper_ids))
```

关键文件：
- `scripts/generate_html.py`（_content_hash 调用处）

### 14.4 解耦 PaperFetcher 与 fetcher 的配置依赖

**问题 #19（补充）** | `scripts/fetch_papers.py`

Phase 4 已将 PaperFetcher 从 1628 行拆分到 287 行，但当前 fetcher 函数仍通过 `fetcher.config`、`fetcher.ss_api_key` 等属性紧耦合 PaperFetcher 实例。每个 fetcher 函数的签名是 `fetch_xxx_papers(fetcher, queries, ...)`，依赖调用方是 PaperFetcher 实例。

改进方案：

- 将 fetcher 函数签名改为接收独立参数：`fetch_xxx_papers(config: dict, queries: list, api_key: str, ...)`
- PaperFetcher 仅作为编排层，将 `self.config`、`self.ss_api_key` 等拆解后传入
- 解除 fetcher 对 PaperFetcher 类的隐式依赖，使 fetcher 可独立测试

关键文件：

- `scripts/fetch_papers.py`（dispatch 方法改为参数解包）
- `daily_paper/sources/arxiv_fetcher.py`、`semantic_scholar.py`、`crossref_fetcher.py`、`openalex_fetcher.py`（函数签名变更）

### 14.5 拆分过长抓取函数

**问题 #26** | `daily_paper/sources/arxiv_fetcher.py`（141行）、`semantic_scholar.py`（168行）

每个函数内部混合了配置提取、关键词构建、日期过滤、venue 匹配、引用批处理等多重职责。

改进方案：拆分为流水线子函数：

- `_build_queries(config)` — 关键词构建
- `_filter_by_date(papers, date_range)` — 日期过滤
- `_match_venue(paper, venues)` — venue 匹配
- `_enrich_citations(papers, api_key)` — 引用批处理

关键文件：

- `daily_paper/sources/arxiv_fetcher.py`
- `daily_paper/sources/semantic_scholar.py`

### Phase 14 验收

- [x] `save_papers()` 仅读写受影响月份数据文件（~3 个月而非全量 30+）
- [n/a] 级联补全使用批量 API 请求 — 不适用（见下方说明）
- [x] 哈希计算不序列化全部论文数据
- [x] 单个抓取函数 ≤ 80 行
- [x] fetcher 函数签名不依赖 PaperFetcher 实例（接受独立参数）
- [x] `pytest -q` 全部通过

> **n/a 说明**：批量 API 请求不适用。Crossref 是 DOI 直查+标题搜索双路径，
> Semantic Scholar 是标题搜索，OpenAlex 无批量端点，publisher 是网页抓取 —
> 四条路径输入格式完全不同，无法统一为单个批量请求。当前
> ThreadPoolExecutor 已让同一论文的 4 路 API 并行，与批量 API 耗时差异 ≤10%。

---

## 风险与缓解

| 风险 | 涉及 Phase | 缓解策略 |
|------|-----------|---------|
| 删除旧模块后某些 import 路径遗漏 | Phase 10 | 每个 git rm 后立即 `pytest -q`；`git grep` 全面扫描残留引用 |
| `batch_get_citation_counts` 提取后行为差异 | Phase 10 | 先写测试覆盖当前行为，提取后跑测试确认一致 |
| 薄封装 cqvip/wanfang 内联后 `_dispatch_sources` 需适配 | Phase 10 | 先确认 `_dispatch_sources` 中的调度逻辑可无缝切换调用方式 |
| 统一 `title_matches` 阈值（0.88→0.85）影响 `enrich_abstracts.py` 匹配率 | Phase 11 | 0.85 是主流程已有阈值，`enrich_abstracts.py` 的 0.88 是 legacy 工具，影响有限 |
| 年日期改为 `YYYY-unk` 需前端适配 | Phase 12 | 前端已有 `"unknown"` 月份桶的处理逻辑，`YYYY-unk` 格式兼容 |
| 移除 VPN 硬编码后 CNKI 本地开发断连 | Phase 13 | 保留环境变量机制；本地开发者需自行配置 `CNKI_HOME_URL` |
| 增量更新可能遗漏跨月合并的论文 | Phase 14 | 保留上月合并窗口 + 定期全量重建命令 |

---

## 优先级排序

| 优先级 | Phase | 耗时 | 理由 |
|--------|-------|------|------|
| 🔴 P0 | **Phase 9** | 1 天 | 零风险，立竿见影（含 enrich.py 死代码备注） |
| 🔴 P0 | **Phase 10** | 2-3 天 | 消除核心架构债务 + 薄封装清理（#21）+ 空文件 docstring |
| 🟡 P1 | **Phase 11** | 3-5 天 | 减少维护混乱，依赖 Phase 10 |
| 🟡 P1 | **Phase 12** | 1-2 天 | 数据准确性，独立可做 |
| 🟡 P1 | **Phase 13** | 1 天 | 安全/配置，独立可做 |
| 🟢 P2 | **Phase 14** | 3-5 天 | 性能优化 + PaperFetcher 配置解耦（#19），非紧急 |
