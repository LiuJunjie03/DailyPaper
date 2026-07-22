# DailyPaper 数据模式 (DATA_SCHEMA)

> 每条论文记录存储为 JSON 对象，按月归档于 `data/YYYY-MM.json`。
> 本文档基于 2026-05 和 2025-01 数据样本及源码分析生成。

## 字段总表

| # | field_name | type | required | populated_by_sources | read_by_frontend | example_value | notes |
|---|---|---|---|---|---|---|---|
| 1 | `id` | string | **必须** | arxiv_fetcher, google_scholar, crossref_fetcher, openalex_fetcher, semantic_scholar, cnki, chinese_html | 是（checkbox、选择、导出） | `"2605.25679v1"`, `"gs-c5789f84433a"` | ArXiv 原始 ID 或 `{source前缀}-{md5(title)[:12]}`。用于去重和 DOM id。 |
| 2 | `title` | string | **必须** | 所有 fetcher | 是（标题显示、搜索） | `"Transformer-based Neural Operators for …"` | 永不为空，各 fetcher 必须填充。 |
| 3 | `authors` | string | **必须** | 所有 fetcher | 是（作者显示、搜索） | `"Yujia Zhang, Jiaxi Qi, …"` | 逗号分隔（ArXiv/OpenAlex）或分号分隔（CNKI 详情）。 |
| 4 | `abstract` | string | **必须** | arxiv_fetcher（原始）、crossref/openalex/semantic_scholar/cnki_detail/publisher_meta（enrichment） | 是（摘要展示、推荐分、搜索） | `"Accurate prediction of three-dimensional …"` | ArXiv 直接填充；其他源初始为空，经级联补全后填充。 |
| 5 | `published` | string | **必须** | 所有 fetcher + fetch_papers `_finalize_paper` 日期补全 | 是（日期显示、排序、筛选） | `"2026-05-28"`, `"2025-01"` | 格式 `YYYY-MM-DD` 最佳；可为 `YYYY-MM` 或 `YYYY`（会补全为 `YYYY-01-01`）。 |
| 6 | `paper_url` | string | **必须** | 所有 fetcher | 是（标题链接、来源链接） | `"https://doi.org/10.2514/6.2025-0269"` | 论文主页 URL。`_finalize_paper` 会设为 `arxiv_url` 或 `doi` 链接的回退。 |
| 7 | `arxiv_id` | string | 可选-常见 | arxiv_fetcher, openalex_fetcher, semantic_scholar, fetch_papers enrichment | 是（arXiv 链接、PDF 下载、DOI 导出推断） | `"2605.25679v1"`, `""` | ArXiv 来源必填；其他源通常为空串。 |
| 8 | `arxiv_url` | string | 可选-常见 | arxiv_fetcher, openalex_fetcher, semantic_scholar, fetch_papers enrichment | 是（arXiv 链接） | `"http://arxiv.org/abs/2605.25679v1"`, `""` | 有 `arxiv_id` 时由 `_finalize_paper` 自动生成。 |
| 9 | `pdf_url` | string | 可选-常见 | arxiv_fetcher, google_scholar, openalex_fetcher, semantic_scholar, chinese_html detail | 是（PDF 链接、PDF 筛选、批量下载） | `"https://arxiv.org/pdf/2605.25679v1"` | 正式版 PDF。预印本时 `_finalize_paper` 会将其移至 `preprint_pdf_url` 并置空。 |
| 10 | `preprint_pdf_url` | string | 可选-常见 | fetch_papers `_finalize_paper`, openalex_fetcher, semantic_scholar, google_scholar | 是（Preprint PDF 链接、PDF 筛选、批量下载） | `"https://arxiv.org/pdf/2605.25679v1"` | 预印本 PDF。当 `is_preprint=true` 时，原 `pdf_url` 移至此处。 |
| 11 | `categories` | string[] | **必须** | arxiv_fetcher（ArXiv 分类）、其他源为 `[]` 或 `[source_label]` | 否 | `["physics.flu-dyn"]`, `[]` | 合并时取并集。前端不直接读取，仅用于内部去重/分类参考。 |
| 12 | `venue` | string | 可选-常见 | 所有 fetcher, fetch_papers enrichment | 是（venue 徽章、已发表状态判断） | `"Nature"`, `"AIAA SCITECH 2025 Forum"` | 期刊/会议名称。`_finalize_paper` 会从 `conference` 回退。 |
| 13 | `conference` | string | 可选-常见 | 所有 fetcher, fetch_papers enrichment | 是（venue 徽章回退、已发表状态判断） | 同 `venue` | 与 `venue` 互为回退。前端优先用 `venue`。 |
| 14 | `publication_types` | string[] | 可选-常见 | arxiv_fetcher(`["Preprint"]`), crossref(`[item_type]`), openalex(`[work_type]`), cnki(`[]`), semantic_scholar(`publicationTypes`) | 否 | `["Preprint"]`, `["proceedings-article"]`, `[]` | Crossref/ArXiv 的原始发表类型列表。前端不直接读取。 |
| 15 | `publication_type` | string | 可选-常见 | 所有 fetcher 初始为 `""` 或 `"preprint"`；`_finalize_paper` 调用 `_publication_type()` 推断 | 是（发表类型标签、已发表/预印本判断） | `"preprint"`, `"journal"`, `"unknown"` | `_finalize_paper` 从 `venue`/`publication_types`/DOI 前缀推断。 |
| 16 | `doi` | string | 可选-常见 | crossref_fetcher, openalex_fetcher, semantic_scholar, cnki detail, chinese_html detail | 是（DOI 链接、导出、早期发表判断） | `"10.1080/14685248.2026.2665148"` | `_finalize_paper` 会 normalize（小写、去空格）。前端用于 DOI 链接和 DOI 复制导出。 |
| 17 | `external_ids` | object | 可选-常见 | arxiv_fetcher(`{"ArXiv": ...}`), google_scholar(`{"GoogleScholarCID": ...}`), openalex(`{"OpenAlex": ...}`) | 否 | `{"ArXiv": "2605.25679v1"}`, `{}` | 外部系统标识符映射。当前前端不读取。 |
| 18 | `semantic_scholar_id` | string | 稀少 | semantic_scholar | 是（来源标签推断：含此字段时显示 Semantic Scholar） | `"abc123def456"`, `""` | 仅 Semantic Scholar 来源有值。前端在 `sourceLabel()` 中用作推断。 |
| 19 | `code_link` | string | 稀少 | 所有 fetcher 初始为 `""` | 是（Code/Project 链接） | `""` | 当前所有 fetcher 都填充空串。前端有展示逻辑但实际数据中几乎无值。 |
| 20 | `tags` | string[] | **必须** | fetch_papers `classify_paper()` | 是（分类筛选、分类计数、推荐分） | `["机器学习", "流体力学", "流体力学 / 智能CFD"]` | 分类标签，由 `classify_paper()` 基于 `classification_score` 生成。最后一级为 `primary_domain`。 |
| 21 | `keywords` | string[] | **必须** | fetch_papers（合并 `official_keywords` + `custom_keywords` 并去重） | 是（关键词显示、推荐分） | `["PINN", "neural network", "turbulence"]` | 最终展示用关键词列表。`generate_html.py` 会做大小写规范化。 |
| 22 | `official_keywords` | string[] | 可选-常见 | arxiv_fetcher(ArXiv 原始标签), cnki_detail(期刊关键词) | 否 | `["turbulence", "pinn"]`, `[]` | 论文原始关键词（作者/期刊标注）。ArXiv 来源和 CNKI 详情有值；Google Scholar 等来源为空。前端不直接读取。 |
| 23 | `custom_keywords` | string[] | **必须** | fetch_papers `extract_paper_keywords()` | 否 | `["cfd", "neural operator", "transformer"]` | 算法从标题/摘要提取的关键词。前端不直接读取，仅通过合并后的 `keywords` 间接使用。 |
| 24 | `citation_count` | number\|null | 可选-常见 | google_scholar(`citedBy`), crossref, openalex, semantic_scholar, cnki | 是（引用数显示、推荐分） | `47`, `0`, `null` | Google Scholar/Crossref/OpenAlex/Semantic Scholar 提供整数值。未获取时为 `null`。 |
| 25 | `impact_factor` | number\|null | 稀少 | fetch_papers `get_impact_factor()` | 是（推荐分：数据不足判断） | `64.8`, `null` | 从 `config.yaml` 的 `venues` 表匹配。仅部分知名期刊有值。 |
| 26 | `source` | string | **必须** | 所有 fetcher | 是（来源标签、推荐分） | `"google_scholar"`, `"arxiv"`, `"crossref"` | 数据最初来源标识。合并时取 primary source。前端用于来源徽章和推荐分。 |
| 27 | `sources` | string[] | 可选-常见 | fetch_papers 合并逻辑 | 否 | `["crossref", "google_scholar"]` | 合并后该论文经历的所有来源列表。前端当前不读取。 |
| 28 | `is_preprint` | boolean | **必须** | fetch_papers `_finalize_paper` | 是（已发表/预印本筛选、标签、推荐分） | `false`, `true` | `publication_type == "preprint"` 时为 `true`。 |
| 29 | `is_early_access` | boolean | 可选-常见 | fetch_papers `_finalize_paper`, `generate_html.py`（旧数据兼容） | 是（预出版筛选、预出版徽章） | `false`, `true` | True=已录用但未正式出版。对旧 JSON 数据，`generate_html.py` 会回算。 |
| 30 | `classification_score` | object | **必须** | fetch_papers `classify_paper()` | 否 | `{"流体力学 / 智能CFD / 物理信息神经网络": {"score": 5, "strong_hits": […], "context_hits": […], "negative_hits": []}}` | 每个候选分类的匹配分数和命中词。用于调试分类结果。前端不读取。 |
| 31 | `primary_domain` | string | **必须** | fetch_papers `_finalize_paper` | 否 | `"流体力学 / 智能CFD / 物理信息神经网络"` | `tags` 数组最后一个元素。前端不直接读取。 |
| 32 | `scholar_snippet` | string | 稀少 | google_scholar | 否 | `"In order to improve the predicted k, we will use Physics Informed Neural Network …"` | Google Scholar 搜索结果摘要片段。仅 Google Scholar 来源有值。前端不直接展示（用 `abstract_status` 判断）。 |
| 33 | `abstract_status` | string | **必须** | google_scholar(`"unreliable_google_scholar_snippet"`), crossref/openalex/semantic_scholar/cnki_detail(`"enriched"`), chinese_html(`"enriched"`/`"search_snippet_only"`) | 是（摘要显示/隐藏、推荐分） | `"enriched"`, `"unreliable_google_scholar_snippet"` | 控制前端摘要展示策略。`unreliable_google_scholar_snippet` 时隐藏摘要。 |
| 34 | `abstract_source` | string | 稀少 | crossref, openalex, semantic_scholar, cnki_detail, publisher_meta, chinese_html | 否 | `"openalex"`, `"crossref"`, `""` | 记录摘要最终来源。前端不直接读取。 |
| 35 | `date_source` | string | 可选-常见 | fetch_papers enrichment (crossref/openalex/semantic_scholar), `_finalize_paper` | 否 | `"crossref"`, `"google_scholar"`, `""` | 记录日期来源。前端不直接读取。 |
| 36 | `date_status` | string | **必须** | fetch_papers enrichment + `_finalize_paper` | 是（日期警告标志） | `"reliable"`, `"approximate"`, `"year_only"` | `"reliable"` = 精确日期；`"approximate"` / `"year_only"` / `"unreliable"` 时前端显示 ⚠。 |
| 37 | `abstract_enriched_at` | string | 稀少 | enrich_abstracts.py, enrich_metadata.py, cnki_detail | 否 | `"2026-06-08T15:40:39.746096+00:00"` | 摘要补全时间戳（ISO 8601）。仅在离线 enrichment 脚本运行后有值。前端不读取。 |
| 38 | `openalex_id` | string | 稀少 | enrich_abstracts.py, enrich_metadata.py, repair_publication_dates.py | 否 | `"https://openalex.org/W4407415621"` | OpenAlex 实体 ID。仅在离线 enrichment 脚本运行后有值。前端不读取。 |
| 39 | `source_snippet` | string | 稀少 | chinese_html (万方/维普) | 否 | `"实验结果表明…"` | 中文源搜索结果片段。仅 chinese_html fetcher 有值。前端不读取。 |
| 40 | `cnki_detail` | object | 稀少 | cnki_detail | 否 | `{"affiliations": […], "fund": "…", "classification": "…", "isOnlineFirst": true}` | CNKI 详情页元数据（机构、基金、分类号等）。仅 CNKI 来源经详情页解析后有值。前端不读取。 |

## 必填字段汇总 (required)

以下字段在 `_finalize_paper` 中保证存在，每条记录必有：

`id`, `title`, `authors`, `abstract`, `published`, `paper_url`, `categories`, `tags`, `keywords`, `custom_keywords`, `classification_score`, `primary_domain`, `abstract_status`, `date_status`, `source`, `is_preprint`, `is_early_access`

以下字段始终存在但可能为空值：

`arxiv_id`(`""`), `arxiv_url`(`""`), `pdf_url`(`""`), `preprint_pdf_url`(`""`), `venue`(`""`), `conference`(`""`), `doi`(`""`), `publication_type`(`"unknown"` 或推断值), `code_link`(`""`), `external_ids`(`{}`), `semantic_scholar_id`(`""`), `official_keywords`(`[]`), `date_source`(`""`)

以下字段可能完全不存在（需 `.get()` 访问）：

`abstract_enriched_at`, `openalex_id`, `source_snippet`, `cnki_detail`, `abstract_source`, `sources`, `scholar_snippet`

中文采集增量字段：`first_seen`（本系统首次发现日期）、`first_seen_at`、`last_seen_at`、
`relevance_score`（0–100 可解释相关性分）、`access_url`（机构全文或期刊详情入口）、
`zotero_lookup_url`（供 Zotero Connector 识别的 DOI/来源页）、`fulltext_status`。这些字段只保存链接，
不会把机构权限 PDF 写入仓库。

## 数据源标识符

| source 值 | fetcher 模块 | 说明 |
|---|---|---|
| `"arxiv"` | `fetchers/arxiv_fetcher.py` | ArXiv API (`physics.flu-dyn`) |
| `"google_scholar"` | `fetchers/google_scholar.py` | Google Scholar 搜索 (ScraperAPI) |
| `"crossref"` | `fetchers/crossref_fetcher.py` | Crossref API (元数据补全) |
| `"openalex"` | `fetchers/openalex_fetcher.py` | OpenAlex API |
| `"semantic_scholar"` | `fetchers/semantic_scholar.py` | Semantic Scholar API |
| `"cnki"` | `fetchers/cnki.py` | CNKI (中国知网) 搜索 |
| `"wanfang"` | `fetchers/wanfang.py` → `fetchers/chinese_html.py` | 万方数据 |
| `"cqvip"` | `fetchers/cqvip.py` → `fetchers/chinese_html.py` | 维普 (CQVIP) |

## 前端读取字段清单

`main.js` 直接访问的字段（必须确保 JSON 中存在）：

- **显示**：`id`, `title`, `authors`, `abstract`, `published`, `tags`, `keywords`, `venue`, `conference`, `publication_type`, `source`, `citation_count`, `impact_factor`
- **链接**：`paper_url`, `arxiv_url`, `arxiv_id`, `pdf_url`, `preprint_pdf_url`, `doi`, `code_link`
- **状态判断**：`is_preprint`, `is_early_access`, `abstract_status`, `date_status`, `semantic_scholar_id`

`generate_html.py` 读取/修改的字段：

- **关键词规范化**：`keywords`
- **早期发表回算**：`is_early_access`（旧数据兼容）, `doi`, `venue`, `conference`
- **统计**：`is_early_access`（计数）
