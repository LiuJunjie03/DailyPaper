# DailyPaper 项目体检与改进计划

分析日期：2026-06-10  
分析范围：当前工作区代码、配置、数据目录、测试与 GitHub Actions。  
验证命令：`pytest -q`，结果为 `47 passed in 2.27s`。

## 一句话结论

这个项目不是不可维护的“屎山代码”，但已经进入了脚本项目常见的“单体膨胀期”：功能可用、测试有一定保护、数据流也基本清楚；真正的问题是复杂度集中在少数大文件里，领域规则、抓取流程、数据修复、生成逻辑和历史兼容代码交织在一起。继续直接堆功能，会越来越像屎山；如果现在分层整理，成本仍然可控。

我的判断是：

- 代码质量：中等偏可维护。
- 架构复杂度：业务本身需要多源抓取，存在合理复杂度；但当前有明显偶然复杂度。
- 屎山程度：轻到中度风险，不是灾难，但已经有局部屎山化迹象。
- 最值得优先做的事：把数据模型、抓取源接口、元数据补全、分类规则、静态站点生成拆出边界，并清理生成物与历史文件。

## 项目现状概览

DailyPaper 是一个面向“流体力学/CFD + 机器学习”论文聚合的 Python 项目，主要流程为：

1. 从 ArXiv、Crossref、OpenAlex、Semantic Scholar、Google Scholar、CNKI、万方、维普等来源抓取论文。
2. 对论文做去重、合并、元数据补全、日期修复、领域分类。
3. 按月份写入 `data/YYYY-MM.json`。
4. 用 `scripts/generate_html.py` 生成 `docs/` 静态站点并发布到 GitHub Pages。

当前数据规模：

- `data/` 中有 27 个月份 JSON，共 1577 篇论文。
- `data/*.json` 约 5.0 MB，`docs/data/*.json` 约 4.9 MB。
- `data/*.bak` 有 25 个，约 3.8 MB，且已经被 Git 跟踪。
- 当前代码库跟踪文件约 157 个。

核心代码规模：

| 文件 | 行数 | 说明 |
| --- | ---: | --- |
| `scripts/fetch_papers.py` | 1628 | 主抓取、合并、分类、补全、落盘入口 |
| `scripts/generate_html.py` | 583 | 静态站点生成入口 |
| `scripts/enrich_metadata.py` | 585 | 元数据补全脚本 |
| `scripts/templates/main.js` | 990 | 前端交互逻辑 |
| `scripts/templates/style.css` | 1202 | 前端样式 |
| `scripts/fetchers/*.py` | 多个 100-300 行文件 | 各数据源抓取器 |

最长的几个函数或类：

- `PaperFetcher`：约 1060 行。
- `HTMLGenerator`：约 509 行。
- `generate_index_html()`：约 205 行。
- `fetch_cnki_papers()`：约 180 行。
- `fetch_semantic_scholar_papers()`：约 172 行。
- `save_papers()`：约 171 行。

这些数字不等于坏代码，但说明主要复杂度高度集中。

## 优点

### 1. 功能闭环完整

项目不是半成品。它具备完整链路：抓取、合并、补全、分类、生成站点、GitHub Actions 定时执行、GitHub Pages 发布。对一个个人/小团队研究工具来说，这个闭环很重要。

### 2. 数据源覆盖面强

当前已经覆盖：

- 预印本：ArXiv。
- 正式出版元数据：Crossref、OpenAlex。
- 语义搜索与引用：Semantic Scholar。
- 搜索补充：Google Scholar。
- 中文来源：CNKI、万方、维普。

这使项目的论文召回能力明显强于单一 ArXiv 抓取器。

### 3. 已经有测试，而且测试现在是绿的

`tests/` 覆盖了若干关键回归点：

- 标题、DOI、ArXiv ID 归一化。
- 关键词边界匹配。
- 相关性判断。
- 月份日期窗口。
- Crossref 月份过滤。
- Google Scholar 摘要片段过滤。
- CNKI URL 与详情页解析。
- 前端生成结果中的关键结构。

这说明项目不是完全靠手工试运行撑着。

### 4. 数据去重效果目前不错

对 `data/` 中 1577 条记录抽查统计，标题、DOI、ArXiv ID 未发现重复键。这说明当前合并逻辑虽然集中在大文件里，但实际产物并非混乱失控。

### 5. 配置化意识较好

`config.yaml` 已经把数据源、查询词、分类、期刊会议、输出目录等放到配置中。虽然配置和代码之间仍有重复规则，但方向是对的。

### 6. 对外部服务失败有降级意识

多个抓取器都有超时、限速、异常捕获、浏览器后端失败后 fallback 的处理。对学术搜索和反爬场景来说，这是实用设计。

### 7. 前端交互体验比普通静态页更完整

前端不是简单把 JSON 展平展示，而是已经实现了一些对论文检索真正有用的交互：

- 使用懒加载逐批渲染论文卡片，避免一次性渲染全部记录。
- 支持月份、发表状态、PDF 可用性、分类、搜索词等多维筛选。
- 支持层级分类导航，能按“流体力学 / 智能CFD / 子方向”逐级钻取。
- 通过推荐分综合来源质量、引用、时效性、全文可用性等因素，帮助用户优先浏览。
- 有选择、导出、复制标识符等偏工作流的功能，而不是只做展示页。

这部分说明项目已经有“研究检索工具”的雏形，不只是一个每日列表页面。

### 8. 中文数据源抽象有值得保留的模式

`scripts/fetchers/chinese_html.py` 抽出了中文文献门户的通用 HTML 搜索、详情页解析、字段清洗和浏览器渲染 fallback，`wanfang.py`、`cqvip.py` 则只是很薄的数据源封装。这是当前项目里比较健康的抽象模式：

- 通用复杂逻辑放在一处。
- 新增同类中文数据源时只需要少量配置和封装代码。
- 与 `cnki.py` 这种更特殊的数据源区分开，避免把所有中文站点逻辑揉成一团。

后续新增数据源时，应该优先复用这种“通用框架 + 薄 source adapter”的模式。

## 主要问题

### 1. `fetch_papers.py` 承担职责过多

`scripts/fetch_papers.py` 同时承担：

- 全局分类规则定义。
- 数据源调度。
- 论文身份归一化。
- 多源合并。
- 引用数查询。
- 级联元数据补全。
- 论文分类。
- 月度 JSON 落盘。
- 备份生成。
- CLI 参数处理。

这导致一个文件既是 domain 层、service 层、repository 层、CLI 层，又包含部分配置常量。最大的问题不是“行数多”，而是修改任何一个环节都容易影响其他环节。

建议拆分为：

- `daily_paper/models.py`：论文数据结构与校验。
- `daily_paper/sources/`：统一数据源接口和各 fetcher。
- `daily_paper/merge.py`：身份键、去重、合并策略。
- `daily_paper/enrich.py`：Crossref/OpenAlex/Semantic Scholar/publisher 级联补全。
- `daily_paper/classify.py`：分类规则和评分。
- `daily_paper/storage.py`：月度 JSON 读写、备份、索引。
- `daily_paper/cli.py`：命令行入口。

### 2. 领域规则在代码和配置中重复

分类相关规则分散在：

- `config.yaml` 的 `categories`。
- `fetch_papers.py` 的 `FLUID_RELATED_TERMS`、`FLUID_RELATED_TAGS`、`SUBDOMAIN_RULES`、`PARENT_TAGS`、`KEYWORD_CANONICAL`。

这会带来两个问题：

- 修改分类时，不知道应该改配置还是代码。
- 测试的是代码规则，但产品筛选按钮来自配置，容易产生“分类出来了但前端不显示”或“配置里有但分类逻辑不会命中”的漂移。

建议让配置成为单一事实来源，代码只负责编译规则和评分。

### 3. 数据模型没有明确 schema

论文记录目前是松散 `dict`，字段有 38 个左右。很多字段只在某些来源或历史数据里存在，比如：

- `doi`、`venue`、`conference` 大量为空，这是数据源差异造成的合理现象。
- `code_link` 当前 1577 条全为空，像是遗留字段。
- `official_keywords` 几乎为空。
- `publication_date_source` 与 `date_source` 可能存在命名漂移。
- `abstract_status`、`abstract_source`、`scholar_snippet` 是后续补全逻辑逐渐加出来的。

没有 schema 的结果是：前端、补全脚本、测试都依赖“约定俗成”的字段。未来字段改名或新增状态时，很容易出现静默错误。

建议用 `dataclass` 或 Pydantic 定义 `PaperRecord`，至少提供：

- 必填字段。
- 可选字段默认值。
- 字段别名兼容。
- 输出 JSON 的稳定顺序。
- schema 版本号，例如 `schema_version: 2`。

### 4. 多源抓取器接口不统一

现在各 fetcher 大多是“接收 `fetcher` 对象，再调用其内部方法”的形式，例如调用 `fetcher._finalize_paper()`、`fetcher.get_impact_factor()`、`fetcher.config`。这让数据源模块看似拆出去了，实际仍紧耦合到 `PaperFetcher`。

更好的边界是：

- 每个 source 只负责返回标准化前的 `RawPaper` 或标准 `PaperRecord`。
- 公共上下文通过 `FetchContext` 传入，包括配置、HTTP client、logger、rate limiter。
- `_finalize_paper()` 作为独立 normalization pipeline，而不是 fetcher 私有方法。

### 5. 元数据补全逻辑重复

`fetch_papers.py`、`enrich_metadata.py`、`enrich_abstracts.py`、部分 `fetchers/*.py` 里都有类似逻辑：

- `request_json()`。
- `normalize_title()`。
- Crossref 日期提取。
- OpenAlex 摘要重建。
- 可靠摘要判断。
- 标题相似匹配。

这类重复不是小问题，因为外部 API 行为变化时，修一个地方很可能漏另一个地方。

更具体地看，项目里实际上存在三套相互重叠的补全体系：

| 位置 | 主要用途 | 与其他文件重叠的能力 |
| --- | --- | --- |
| `fetch_papers.py` | 抓取主流程中的级联补全 | Crossref、OpenAlex、Semantic Scholar、publisher meta |
| `enrich_abstracts.py` | 独立补全摘要 | Crossref、OpenAlex、Semantic Scholar、publisher meta |
| `enrich_metadata.py` | 独立补全日期和摘要 | Crossref、OpenAlex、Semantic Scholar、publisher meta |

这会造成一个隐蔽风险：同一个 API 的匹配阈值、摘要可靠性判断、日期解析规则可能在不同入口下表现不一致。比如标题匹配阈值、OpenAlex 摘要倒排索引重建、Crossref 日期解析等逻辑，都不应该各维护一份。

建议建立：

- `daily_paper/http.py`：统一重试、超时、User-Agent、限速、缓存。
- `daily_paper/text.py`：标题归一化、文本清洗、摘要可靠性判断。
- `daily_paper/providers/crossref.py` 等：只处理 API 映射。

### 6. 生成物和源数据边界不清

仓库同时跟踪：

- `data/YYYY-MM.json` 源数据。
- `docs/data/YYYY-MM.json` 发布副本。
- `docs/papers.json` 兼容文件。
- `docs/css/style.css`、`docs/js/main.js` 生成物。
- `docs/css/style.css.hash`、`docs/js/main.js.hash`。
- `data/*.bak` 备份文件。

这不是一定错误，因为 GitHub Pages 需要 `docs/`。但需要明确策略：

- 哪些是源文件。
- 哪些是构建产物。
- 哪些允许人工编辑。
- 哪些应该在 CI 中生成。
- `.bak` 是否应该入库。

当前 `.bak` 文件已被跟踪，长期会让历史和 diff 噪音变大。建议停止跟踪 `.bak`，并把备份策略改为本地临时目录或 Git 历史。

### 7. 前端生成方式混合了模板、业务统计和静态 HTML

`generate_html.py` 同时：

- 读取数据。
- 过滤相关论文。
- 统计首页指标。
- 生成大段 HTML。
- 同步数据到 `docs/data`。
- 拷贝 CSS/JS 模板。

其中 `generate_papers_html()` 等函数看起来像旧版静态列表生成逻辑，当前主页面更多依赖前端 JS 加载数据，存在遗留代码痕迹。

建议：

- 将 HTML 模板改为单独模板文件，例如 Jinja2 或最小自定义模板。
- Python 只注入 `CATEGORIES`、`DATA_VERSION`、统计摘要。
- 前端 JS 独立维护，不在 Python 字符串里拼大量 HTML。
- 删除确认为未使用的旧生成函数。

### 8. 模块导入存在全局副作用

`scripts/generate_html.py` 在模块级执行：

```python
config = load_config()
CATEGORIES = list(config.get('categories', {}).keys())
```

这意味着只要 `import generate_html`，就会立即读取磁盘上的 `config.yaml`。当前测试能跑通，但这个设计会让模块复用、单元测试和未来包化变得笨重，也迫使调用方依赖特定目录结构。

更好的方式是：

- 在 `HTMLGenerator.__init__` 中显式加载配置，允许测试传入临时配置。
- 或提供 `HTMLGenerator(config=..., data_dir=..., output_dir=...)`，把文件读取和业务对象构造分开。
- 去掉 `importlib.util.spec_from_file_location()` 这种动态导入兜底，改为规范包结构或明确设置测试导入路径。

### 9. 已确认的具体代码瑕疵

除架构问题外，还发现两处可以直接修复的小问题：

1. `scripts/fetch_papers.py` 中 `_needs_crossref_enrichment()` 的条件存在永真子句：

```python
bool(paper.get("doi")) or not paper.get("doi")
```

这个表达式对任意 `doi` 状态都为真，所以当前判断基本退化成 `not self._metadata_complete(paper)`，除了 ArXiv 且无 DOI 的早退分支。它不一定导致错误结果，但会让 Crossref 补全触发条件比代码表面含义更宽，建议改成更明确的条件。

2. `scripts/templates/main.js` 中 `codeLink` 对同一个 `paper.code_link` 连续赋值两次，第一次赋值马上被第二次覆盖。第二次写法更安全，但重复代码说明这里有 copy-paste 痕迹，应删除第一次赋值并保留转义后的版本。

3. `scripts/fetch_papers.py` 中 `extract_paper_keywords()` 使用 `paper["title"]` 和 `paper["abstract"]` 直接下标访问。大部分主流程记录会有这两个字段，但只要某个数据源或历史数据缺字段，就会触发 `KeyError`。这里应改成 `paper.get("title", "")` 和 `paper.get("abstract", "")`。

4. `scripts/fetchers/semantic_scholar.py` 在 `publicationDate` 解析失败或缺失时使用 `"2025"` 作为默认年份。当前日期已是 2026-06-10，这会让部分无完整日期的论文被错误归入 2025。建议改成 `item.get("year")`，若仍为空则使用 `unknown` 或显式跳过日期归档，而不是写死年份。

### 10. 缓存和硬编码存在长期漂移风险

有几处短期不一定出错，但会随时间或运行规模变坏：

- `fetch_papers.py` 的 `_CASCADE_JSON_CACHE` 是模块级字典，没有大小上限和过期策略。日常单次运行风险不高，但历史月份回填或长时间进程可能造成内存持续增长。建议改成 LRU cache 或按运行阶段清空。
- `config.yaml` 中 `google_scholar.year_from: 2026` 是时间硬编码，到了下一年需要人工维护。更稳妥的方式是支持相对配置，例如 `years_back: 1` 或默认使用当前年。
- `scripts/generate_html.py` 和已生成的 `docs/index.html` 页脚仍是 `© 2025`，这类展示层年份应由当前日期生成或改为不写固定年份。
- `config.yaml` 中 CNKI 代理 URL 绑定到具体校园 VPN 域名，不利于迁移和公开复用。建议允许通过环境变量或本地私有配置覆盖。

### 11. 待确认的遗留代码和死代码清理项

以下项从静态检索看像遗留代码，但删除前需要逐项确认前端行为和测试覆盖：

- `generate_html.py` 的 `generate_papers_html()`：主页面已由前端 JS 渲染论文卡片，该方法看起来是旧版静态列表生成逻辑。
- `scripts/templates/main.js` 的 `loadStateFromURL()`：函数存在，但需要确认初始化流程是否实际调用；如果未调用，则 URL 状态持久化只保存不恢复。
- `scripts/templates/main.js` 的 `downloadFile()`：当前未看到直接调用方，可能是早期导出逻辑遗留。
- `fetch_papers.py` 的 `get_citation_count()`：标注为兼容保留，但主流程主要使用批量引用查询和 source fetcher。
- `scripts/templates/style.css` 的 `@keyframes shimmer` 与重复的 `.category-children > .filter-btn.active::after` 规则：可能是样式迭代遗留。

这类清理不应和业务重构混在一起做。建议先用全文检索、浏览器回归和测试确认，再分小提交删除。

### 12. 文档存在漂移

`CLAUDE.md` 中的部分信息已经过期，例如：

- 技术栈里写了 `pandas`、`numpy`，但 `requirements.txt` 没有这些依赖。
- “已知问题”里提到 `update_venue.py` 仍硬编码 `data/papers.json`，但当前代码已改为处理月度 JSON。
- “Semantic Scholar 状态码 1000”这类历史问题在当前代码中已看不到。

文档漂移会让后来的人误以为项目仍有已修复问题，或者按错误路径排查。

### 13. 依赖和工程化配置不足

当前缺少：

- `pyproject.toml` 或明确的包结构。
- 依赖锁定策略。
- formatter/linter 配置，例如 Ruff。
- 类型检查配置，例如 mypy 或 pyright。
- CI 中的测试步骤。

GitHub Actions 现在主要做抓取、生成、提交、部署，没有在抓取前运行单测。建议至少加入 `pytest -q`。

### 14. 外部服务抓取存在稳定性和合规风险

Google Scholar、CNKI、万方、维普等来源天然不稳定，可能遇到：

- CAPTCHA。
- 代理不可用。
- DOM 结构变化。
- 速率限制。
- 校园代理地址泄漏或迁移。

当前代码已有降级处理，但缺少统一的 provider health report。建议每次运行输出数据源级别状态，例如：

- 请求次数。
- 成功条数。
- 失败原因。
- 限速次数。
- 被跳过原因。

## 是否结构过于复杂

结论：业务复杂度是合理的，代码结构复杂度偏高。

合理复杂度来自：

- 多数据源。
- 多语言数据。
- 预印本与正式出版元数据合并。
- 日期不完整、摘要不可靠、引用数缺失等现实问题。
- 前端需要本地静态加载和筛选。

不合理复杂度来自：

- 一个类承担过多职责。
- 规则在配置和代码中重复。
- 工具函数重复实现。
- 历史兼容代码和当前主路径混在一起。
- 源数据、发布副本、备份、生成物都在同一个仓库路径中。

换句话说，这不是“需求太复杂导致必然混乱”，而是“缺少模块边界导致复杂度堆在少数文件里”。

## 是否是屎山代码

我会给一个比较诚实的判断：还不是屎山，但有局部屎山化趋势。

不是屎山的理由：

- 主流程能跑。
- 测试通过。
- 数据产物没有明显重复失控。
- 多源抓取器已经部分拆分。
- 有日志、异常处理和配置化。
- 静态站点生成有可验证测试。

有屎山化趋势的理由：

- `PaperFetcher` 已经接近上帝类。
- 分类、补全、合并、落盘互相缠绕。
- 同类函数重复出现在多个脚本。
- 历史脚本、临时修复脚本、正式流程边界不清。
- 文档和现实代码有漂移。
- 数据 schema 靠约定，没有强约束。

更准确的标签是：可运行的研究型脚本系统，正在向工程化系统过渡，但还没有完成分层。

## 风险分级

### 高优先级

1. `fetch_papers.py` 单体过大，后续改动风险高。
2. 数据模型无 schema，字段漂移会导致静默错误。
3. 分类规则代码与配置重复，容易不一致。
4. `.bak` 和生成物策略不清，长期污染版本历史。
5. 三套元数据补全体系并行存在，容易产生规则漂移和维护遗漏。
6. `extract_paper_keywords()` 对缺失字段不防御，存在运行时崩溃风险。
7. Semantic Scholar 默认年份写死为 2025，存在数据归档错误风险。

### 中优先级

1. 元数据补全逻辑重复，维护成本高。
2. 外部 API 请求与重试策略分散。
3. 前端生成脚本混合 HTML 模板和业务统计。
4. CI 未明确先跑测试再抓取部署。
5. 文档漂移。
6. `generate_html.py` import 时读取配置，存在模块级副作用。
7. `_needs_crossref_enrichment()` 条件表达式含永真子句，代码意图不清。
8. `_CASCADE_JSON_CACHE` 无上限，历史回填或长进程下可能造成内存增长。
9. Google Scholar 起始年份、页脚年份、CNKI 代理地址存在硬编码和迁移成本。

### 低优先级

1. `utils.py` 基本未被使用，可以清理或重新定位。
2. 顶层 `quick_test.py`、`simple_test.py`、`test.py` 和 `fix_dates*.py` 更像临时脚本，需要归档。
3. 影响因子静态表维护成本较高，但短期不是核心瓶颈。
4. `main.js` 中 `codeLink` 重复赋值，应作为小型前端清理项修复。
5. `loadStateFromURL()`、`downloadFile()`、`get_citation_count()`、旧 CSS 动画等疑似遗留代码需要逐项确认。

## 改进计划

### 第 0 阶段：先稳住现状，1 天内

目标是不改变行为，只降低维护噪音。

建议任务：

1. 新增 `pytest -q` 到 GitHub Actions，在抓取前执行。
2. 更新 `CLAUDE.md`、`README.md`、`docs/USAGE.md` 中过期描述。
3. 在 `.gitignore` 中加入 `*.bak`，并计划停止跟踪已有 `data/*.bak`。
4. 明确 `docs/` 是发布产物，`scripts/templates/` 是前端源模板。
5. 标注 `docs/papers.json` 的兼容用途，或者确认无用后删除。
6. 给当前 JSON schema 写一份 `docs/DATA_SCHEMA.md`。
7. 修复 `_needs_crossref_enrichment()` 的永真条件，让触发逻辑和注释一致。
8. 删除 `main.js` 中第一次不安全且会被覆盖的 `codeLink` 赋值。
9. 将根目录临时脚本归档到 `scripts/maintenance/` 或删除已无用脚本。
10. 修复 `extract_paper_keywords()` 的直接下标访问。
11. 移除 Semantic Scholar 中 `"2025"` 默认年份，改为明确的未知日期策略。
12. 把页脚年份改为动态年份，或移除固定年份。

验收标准：

- 测试仍为 `47 passed` 或更多。
- 文档描述与当前代码一致。
- 新贡献者能分清源文件和生成物。

### 第 1 阶段：抽出稳定基础模块，3-5 天

目标是减少重复，不大改流程。

建议新增模块：

- `scripts/common/text.py`：标题归一化、DOI/ArXiv ID 归一化、摘要清洗。
- `scripts/common/http.py`：统一 `request_json()`、重试、超时、User-Agent。
- `scripts/common/dates.py`：完整日期判断、月份窗口、Crossref/OpenAlex 日期转换。
- `scripts/common/schema.py`：论文字段默认值和 schema 校验。

迁移策略：

- 先复制测试覆盖。
- 每迁移一个函数，只替换调用，不改业务。
- 保留旧函数一小段时间作为兼容 wrapper。

验收标准：

- `fetch_papers.py` 行数减少 200 行以上。
- 重复的 `normalize_title()`、`request_json()`、日期解析逻辑显著减少。
- 核心测试继续通过。

### 第 2 阶段：拆分 `PaperFetcher`，1-2 周

目标是把上帝类拆成几个小服务。

建议拆成：

- `SourceRunner`：按配置调度各数据源。
- `PaperNormalizer`：补默认字段、规范 ID、链接、出版类型。
- `PaperMerger`：身份键、来源优先级、字段合并。
- `PaperClassifier`：分类评分和标签生成。
- `PaperEnricher`：级联补全。
- `PaperStore`：读写月度 JSON、索引、备份策略。

迁移顺序：

1. 先拆 `PaperMerger`，因为可用现有数据做纯单测。
2. 再拆 `PaperClassifier`，把规则输入固定。
3. 再拆 `PaperStore`，隔离文件读写。
4. 最后拆 `SourceRunner` 和 `PaperEnricher`。

验收标准：

- `PaperFetcher` 只保留 orchestration 或被删除。
- 单个类最好不超过 250-300 行。
- `save_papers()` 不再是 170 行的长函数。

### 第 3 阶段：前端生成整理，1 周

目标是让静态站点生成更清晰。

建议：

1. 把 `generate_index_html()` 的 HTML 移到模板文件。
2. 确认并删除未使用的 `generate_papers_html()` 及其辅助函数，或把它标记为 legacy。
3. 将首页统计逻辑提取为 `build_dashboard_stats(papers)` 并单测。
4. 将 `docs/data` 同步逻辑移入 `PaperStore` 或独立 build 步骤。

验收标准：

- `generate_html.py` 下降到 250-350 行。
- 模板、数据同步、统计计算分开。
- 前端回归测试继续通过。

### 第 4 阶段：数据与发布策略收敛，1 周

目标是减少仓库噪音和发布风险。

建议决策：

- 若 `data/` 是事实源，则 `docs/data/` 由 CI 生成，开发时可不手工提交。
- 若 GitHub Pages 必须直接从 `docs/` 发布，则保留 `docs/data/`，但必须在文档中说明它是构建产物。
- `.bak` 不入库，必要时备份到 `.cache/dailypaper/backups/` 或依赖 Git 历史。
- 为月度 JSON 增加 schema 校验命令，例如 `python -m daily_paper validate-data`。

验收标准：

- 普通抓取更新的 diff 可读。
- 不再出现大量 `.bak` 噪音。
- CI 能发现 JSON 字段缺失或类型错误。

### 第 5 阶段：工程化，持续推进

建议：

1. 增加 `pyproject.toml`。
2. 引入 Ruff，先只开启安全的基础规则。
3. 引入类型检查，但先从核心模块开始，不必一次覆盖全部脚本。
4. 增加 provider health report。
5. 增加端到端 dry-run 测试：用 fixture 数据模拟多源返回，不访问外网。

验收标准：

- 新人能用 `pip install -e .` 或标准命令运行。
- CI 包含 test、lint、validate-data、build-site。
- 多源主流程有离线测试。

## 推荐目标结构

一个稳妥的目标结构可以是：

```text
daily_paper/
  __init__.py
  cli.py
  config.py
  models.py
  text.py
  dates.py
  http.py
  classify.py
  merge.py
  enrich.py
  storage.py
  sources/
    __init__.py
    base.py
    arxiv.py
    crossref.py
    openalex.py
    semantic_scholar.py
    google_scholar.py
    cnki.py
    chinese_html.py
  site/
    build.py
    templates/
      index.html
      main.js
      style.css
scripts/
  fetch_papers.py        # 轻量兼容入口
  generate_html.py       # 轻量兼容入口
tests/
docs/
data/
```

关键原则：

- `daily_paper/` 放可测试业务代码。
- `scripts/` 只保留命令入口，避免堆业务逻辑。
- `sources/` 不直接操作磁盘。
- `storage.py` 不访问外网。
- `classify.py` 不知道前端存在。
- `site/build.py` 不负责抓取。

## 不建议的改法

不建议一次性大重构。这个项目有真实数据和发布流程，外部 API 又不稳定，如果一次重写，很容易把现在可用的链路弄断。

也不建议先追求完美抽象。更好的策略是：

1. 先写边界测试。
2. 再搬重复工具函数。
3. 再拆纯逻辑模块。
4. 最后改 orchestration。

每一步都保证 `pytest -q` 和站点生成通过。

## 优先级最高的 15 个具体行动

1. 在 GitHub Actions 抓取前加入 `pytest -q`。
2. 新增 `docs/DATA_SCHEMA.md`，定义论文字段。
3. 停止跟踪 `data/*.bak`，并把 `*.bak` 加入 `.gitignore`。
4. 更新过期项目文档。
5. 修复 `_needs_crossref_enrichment()` 的永真条件。
6. 清理 `main.js` 中重复的 `codeLink` 赋值。
7. 修复 `extract_paper_keywords()` 对缺失字段的 `KeyError` 风险。
8. 移除 Semantic Scholar 的 `"2025"` 默认年份。
9. 把页脚年份、Google Scholar 起始年份、CNKI 代理地址改成动态或可配置。
10. 把归一化和日期工具抽到公共模块。
11. 统一 `fetch_papers.py`、`enrich_abstracts.py`、`enrich_metadata.py` 的补全逻辑。
12. 把 `PaperMerger` 从 `fetch_papers.py` 拆出来。
13. 把 `PaperClassifier` 从 `fetch_papers.py` 拆出来。
14. 给多源合并写 fixture 测试。
15. 把 `generate_index_html()` 改成模板渲染，并删除或归档未使用的旧函数和临时脚本。

## 总结

DailyPaper 当前的最大价值是“能跑且有数据”，最大风险是“所有聪明逻辑都挤在少数脚本里”。它还没有坏到需要推倒重来，但已经到了必须整理边界的阶段。

最现实的改进路线不是重写，而是渐进式收敛：先稳定文档和 CI，再抽公共工具，再拆 `PaperFetcher`，最后整理前端构建和数据发布策略。这样可以在不破坏现有发布链路的前提下，把项目从研究脚本逐步推进到可长期维护的小型工程系统。
