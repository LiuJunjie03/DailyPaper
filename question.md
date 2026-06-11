# DailyPaper 项目代码审查问题清单

> 生成日期：2025-06-10 | 审查范围：`E:\Dailypaper` 全项目

---

## 一、严重问题 — 大规模代码重复

### 1. `scripts/` 与 `daily_paper/` 双份模块并存

项目维护了两套**并行的核心逻辑副本**，存在漂移风险：

| 副本 A | 副本 B |
|--------|--------|
| `scripts/classifier.py` (27KB) | `daily_paper/classify.py` |
| `scripts/common/text.py` | `daily_paper/text.py` |
| `scripts/common/http.py` | `daily_paper/http.py` |
| `scripts/common/dates.py` | `daily_paper/dates.py` |
| `scripts/common/queries.py` | `daily_paper/queries.py` |
| `scripts/common/schema.py` | `daily_paper/schema.py` |

**症状：** `fetch_papers.py` 第 19 行从 `daily_paper.classify` 导入，第 137 行又从 `classifier`（即 `scripts/classifier.py`）导入，两套同存一处。`generate_html.py` 第 21-33 行还写了 importlib fallback hack 来处理路径问题。

**建议：** 确定唯一权威源（推荐 `daily_paper/` 作为安装包），删除 `scripts/` 下的副本，统一所有 import 路径。

---

### 2. 三套补全逻辑高度重叠

| 文件 | 行数 | 职责 |
|------|------|------|
| `scripts/enrich.py` | - | 级联补全（Crossref→OpenAlex→S2→出版商），在 `save_papers()` 中调用 |
| `scripts/enrich_metadata.py` | 535 行 | 日期 + 摘要补全，独立 CLI |
| `scripts/enrich_abstracts.py` | 309 行 | 仅摘要补全，独立 CLI |

**重复的函数（三个文件中各有独立实现）：**
- `title_matches()` — 相似度阈值不同（0.85 vs 0.88）
- `is_reliable_abstract()` / `clean_text()` / `clean_abstract()` — 三个变体
- `fetch_arxiv_date/abstract()` — `enrich_metadata.py:79-98` vs `enrich_abstracts.py:73-102`
- `fetch_semantic_scholar_*()`, `fetch_openalex_*()`, `fetch_crossref_*()`, `fetch_publisher_meta()` — 全部重复

**建议：** 合并为单一 `enrich.py` 模块，通过参数控制补全深度。

---

### 3. `batch_get_citation_counts` 逐字复制

**完全相同**的约 100 行函数出现在两个文件中：
- `scripts/fetchers/arxiv_fetcher.py:13-103`
- `scripts/fetchers/semantic_scholar.py:36-118`

**建议：** 抽取为共享工具函数，放在 `scripts/common/` 或 `daily_paper/` 中。

---

## 二、高危 Bug

### 4. `scripts/utils.py:64` — 裸 `except:` 吞噬所有异常

```python
def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:          # ← 连 KeyboardInterrupt、SystemExit、MemoryError 都吞
        return datetime.now()
```

**影响：** 按 Ctrl+C 时不会中断，而是静默返回当前时间继续执行。异常日期输入会被无声地替换为 `datetime.now()`，掩盖数据质量问题。

**建议：** 改为 `except ValueError`，并考虑返回 `None` 而非 `datetime.now()`。

---

### 5. `scripts/enrich_abstracts.py:60` — 永假条件的空白检查

```python
def is_reliable_abstract(text):
    text = clean_abstract(text)  # ← 第49行：re.sub(r"\s+", " ", text) 已压缩空白
    ...
    if re.search(r"\s{2,}", text):  # ← 第60行：永远匹配不到，clean后无连续空白
        return False
```

**建议：** 将空白检查移到 `clean_abstract()` 之前，或直接删除这段死代码。

---

### 6. `scripts/store.py:59` — 仅有年份的论文被静默分配到1月

```python
elif len(parts) == 1 and parts[0].isdigit():
    month = f"{parts[0]}-01"  # 仅年份 → 归入1月
```

**影响：** 一篇 2025 年发表的论文被标记为 `2025-01`，破坏了按月统计的语义准确性。

**建议：** 至少记录 `date_precision: "year"` 字段，或在 UI 中注明"仅知年份"。

---

### 7. `scripts/fetch_papers.py:87` — `.setdefault()` 误用

```python
source = self.config.get("sources", {}).setdefault(source_name, {})
```

`.setdefault()` 会**原地修改** `.get()` 返回的字典，而 `self.config` 来自 YAML 解析。此处碰巧可以工作（因为 `.get()` 返回了内部 dict 的引用），但语义错误：`.setdefault()` 应该直接在 dict 对象上调用，而非链式调用在 `.get()` 之后。

**建议：** 改为：
```python
sources = self.config.setdefault("sources", {})
source = sources.setdefault(source_name, {})
```

---

### 8. `scripts/fetch_papers.py:100` — `_validate_config` 遗漏 `crossref` 和 `openalex`

```python
for source_name in ["arxiv", "semantic_scholar", "google_scholar",
                    "cnki", "wanfang", "cqvip"]:  # ← 缺少 crossref, openalex
```

但 `_dispatch_sources()` 中实际会抓取这两个数据源，它们的配置未被校验。

**建议：** 将 `crossref`、`openalex` 加入校验列表。

---

## 三、中危问题

### 9. `scripts/generate_html.py:68-75` — "本周"实际是"近7天"

```python
week_start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
```

变量名 `recent_week_count` 暗示"本周"，但 `today - 6 days` 是滚动 7 天窗口，跨周边界时行为与用户预期不一致。

**建议：** 要么改名为 `recent_7_days_count`，要么改用 `today - timedelta(days=today.weekday())` 实现真正的周一起始。

---

### 10. `scripts/enrich_metadata.py:413` — 日期用字符串比较

```python
if new_date > TODAY:  # TODAY 也是字符串 "YYYY-MM-DD"
```

ISO 格式下碰巧可用，但如果某天引入 `YYYY/MM/DD` 等其他格式就会出错。

**建议：** 解析为 `date` 对象后再比较。

---

### 11. `scripts/update_venue.py:40` — 子串匹配过宽

```python
if venue_name.lower() in comment.lower():
```

`"AIAA"` 会误匹配到 `"NON-AIAA"` 或 `"AIAA-SOMETHING-ELSE"`。

**建议：** 使用单词边界正则：`re.search(r'\b' + re.escape(venue_name) + r'\b', comment, re.IGNORECASE)`

---

### 12. `scripts/utils.py` — 疑似废弃模块

该文件定义了 `load_json`、`save_json`、`deduplicate_papers`、`format_authors`、`truncate_text`、`parse_date`、`get_papers_by_category`、`count_papers_by_category` 等函数，但**全项目没有任何文件 import 它**。CLAUDE.md 中记录它包含"共享工具函数"，但实际似乎已被 `daily_paper/` 替代。

**建议：** 确认是否仍需要。如不需要，删除；如需要，修正 import 链。

---

### 13. `scripts/fetch_papers.py:137` — 混乱的双重导入

```python
# 第19行：from daily_paper.classify import classify_paper, extract_paper_keywords, ...
# 第137行：
def extract_official_keywords(self, result):
    from classifier import extract_official_keywords  # ← 从 scripts/classifier.py 导入
    return extract_official_keywords(result)
```

同一个类中，部分方法用 `daily_paper.classify` 的函数，这个方法又绕回去用 `scripts/classifier.py` 的同名函数。

**建议：** 统一从 `daily_paper.classify` 导入。

---

### 14. `scripts/normalizer.py:16` — 同样的裸 import 问题

```python
from classifier import classify_paper, extract_paper_keywords, normalize_keywords
```

**建议：** 改为 `from daily_paper.classify import ...`。

---

## 四、配置问题

### 15. `config.yaml:32` — 不存在的联络邮箱

```yaml
mailto: "research@dailyPaper.org"
```

Crossref 和 OpenAlex 的 polite pool 要求有效联系方式。该域名 `dailyPaper.org` 实际不存在，可能导致 API 请求被拒或降级。

**建议：** 替换为真实可用的邮箱地址。

---

### 16. `config.yaml:87-88` — 硬编码机构 VPN 代理 URL

```yaml
home_url: "http://www--cnki--net--https.cnki.mdjsf.utuvpn.utuedu.com:9000/"
kns_base_url: "http://kns--cnki--net--https.cnki.mdjsf.utuvpn.utuedu.com:9000/"
```

这些是特定机构的 VPN 代理地址，对任何其他用户无效。

**建议：** 通过环境变量 `CNKI_HOME_URL` / `CNKI_KNS_BASE_URL` 配置（CLAUDE.md 已注明应如此），将 `config.yaml` 中的硬编码值改为空或占位符。

---

### 17. `config.yaml:546` — 过于激进的 cron 调度

```yaml
schedule:
    cron: "0 0 * * *"  # 每天 UTC 午夜
```

每天抓取 9 个数据源，极易触发 rate limit。

**建议：** 考虑在每个数据源配置中添加独立的抓取频率控制，或改为 `0 0 * * 0,3`（每周日+周三）。

---

### 18. `config.yaml:143` — Semantic Scholar API key 为空

```yaml
semantic_scholar:
    api_key: ""
```

无 API key 时 S2 的速率限制更严格（每分钟 100 请求 vs 有 key 的 1000）。

---

## 五、设计与架构问题

### 19. `PaperFetcher` 是一个 God Object 代理

`scripts/fetch_papers.py` 中的 `PaperFetcher` 类本身不实现任何抓取逻辑——它是一个薄门面，将所有工作委托给子模块，仅用于持有 `config` 并传递给 fetcher 函数（`fetcher.config`、`fetcher.ss_api_key` 等紧耦合）。

**建议：** 将配置作为独立对象传入各 fetcher，解除对 `PaperFetcher` 的隐式依赖。

---

### 20. 没有增量更新机制

`save_papers()` 每次都加载**全部**历史月度 JSON 文件，全量合并、重新分类、重新写入。随着月度文件增长（目前已约 30 个文件、3.5MB），IO 和计算开销线性增长。

**建议：** 实现仅处理"新增/变更"的增量逻辑，或按季度归档老旧数据。

---

### 21. 抓取器薄封装与空文件

- `scripts/fetchers/cqvip.py`（13 行）和 `scripts/fetchers/wanfang.py`（13 行）只是调用 `fetch_chinese_html_source()` 的超薄封装，无任何源特定逻辑。
- `scripts/fetchers/__init__.py` — 空文件（0 字节）
- `tests/conftest.py` — 空文件（0 字节）

**建议：** 考虑合并薄封装，或至少为空文件添加 docstring 说明意图。

---

### 22. 级联补全的串行 API 调用

`cascade_enrich_papers()` 对每篇论文串行调用最多 4 个外部 API（Crossref→OpenAlex→Semantic Scholar→出版商），每次间隔 0.15s。处理 100 篇论文可能需要数分钟。

**建议：** 使用 `asyncio` + `aiohttp` 实现并发 API 调用，或在数据源级别做批量请求。

---

## 六、安全问题

### 23. `scripts/fetchers/browser.py:18` — Chrome DevTools 无认证

```python
DEBUGGER_URL = "http://127.0.0.1:9222"
```

Chrome DevTools Protocol 在 localhost 上无认证开放，本机任何进程都可控制浏览器。

**建议：** 至少检查调用来源，或使用 Unix socket 替代 TCP。

---

### 24. `scripts/fetchers/cnki.py` / `google_scholar.py` — 内联 JavaScript 注入风险

浏览器抓取路径中，JavaScript 代码以内联 Python 字符串拼接方式构建。如果查询关键词来自外部输入（如配置文件），则存在注入风险。

**建议：** 对拼入 JS 字符串的关键词做转义，或使用 JSON.stringify 传递参数。

---

## 七、性能问题

### 25. `scripts/generate_html.py:258` — 全量数据序列化计算哈希

```python
data_hash = self._content_hash(
    json.dumps(self.papers, ensure_ascii=False, sort_keys=True)
)
```

为计算缓存破坏用的版本哈希，将**全部论文**序列化为 JSON 字符串（可能几百 KB），开销 O(n)。

**建议：** 改为对最新月度文件的 mtime 做哈希，或仅序列化论文 ID 列表。

---

### 26. `scripts/fetchers/arxiv_fetcher.py` 和 `semantic_scholar.py` 中函数过长

- `fetch_arxiv_papers()` 约 140 行
- `fetch_semantic_scholar_papers()` 约 166 行

两个函数内部混合了关键词构建、日期过滤、venue 匹配、引用批处理、排序等多重职责。

**建议：** 拆分为独立的构建→请求→解析→批处理流水线函数。

---

## 八、测试覆盖缺失

以下关键路径缺少测试：

| 函数/模块 | 缺失的测试场景 |
|-----------|---------------|
| `merge_paper_list()` | 去重边界情况（仅 DOI 不同 / 仅标题不同） |
| `classify_paper()` | 子领域打分 + 排除关键词（`exclude_keywords`） |
| `cascade_enrich_papers()` | API 全部失败 / 部分失败的降级行为 |
| `batch_get_citation_counts()` | HTTP 429 重试逻辑 |
| CNKI / Google Scholar | 浏览器抓取路径（当前零覆盖） |
| `split_papers_by_month()` | 仅有年份的论文 |
| `generate_monthly_data_files()` | 索引文件生成 |

---

## 九、汇总统计

| 严重程度 | 数量 | 类别分布 |
|---------|------|---------|
| CRITICAL（严重） | 4 | 代码重复 |
| HIGH（高危） | 5 | Bug / 设计 |
| MEDIUM（中危） | 7 | Bug / 配置 / 设计 |
| LOW（低危） | 5 | 安全 / 性能 / 缺失 |
| **总计** | **26** | — |

---

## 十、优先修复建议（排序）

1. **统一模块来源**（问题 #1、#2、#3、#13、#14）— 消除 `scripts/` 与 `daily_paper/` 的双轨制
2. **修复裸 except**（问题 #4）— 一行改动，避免异常吞噬
3. **修复死代码空白检查**（问题 #5）— 删除或前移
4. **修复 `.setdefault()` 误用**（问题 #7）
5. **修复 `_validate_config` 遗漏数据源**（问题 #8）
6. **修复日期字符串比较**（问题 #10）
7. **替换 config.yaml 中硬编码的 VPN URL 和邮箱**（问题 #15、#16）
8. **清理废弃模块**（问题 #12）— `scripts/utils.py`
