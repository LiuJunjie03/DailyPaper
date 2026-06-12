import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_html import (
    HTMLGenerator,
    build_dashboard_stats,
    build_smart_cfd_trends,
    is_complete_publication_date,
)
from daily_paper.sources.google_scholar import _looks_like_scholar_snippet
from daily_paper.sources.cnki_detail import apply_cnki_detail, parse_cnki_detail_html
from enrich_abstracts import is_reliable_abstract, needs_enrichment, openalex_abstract


def write_sample_month(data_dir: Path):
    data_dir.mkdir()
    papers = [
        {
            "id": "2606.00001",
            "title": "Neural surrogate model for turbulent flow",
            "authors": ["Ada Lovelace", "Qian Xuesen"],
            "abstract": "A CFD surrogate model for turbulent flow.",
            "published": "2026-06-01",
            "tags": ["流体力学", "流体力学 / 智能CFD", "机器学习"],
            "keywords": ["CFD", "turbulence"],
            "categories": ["physics.flu-dyn"],
            "arxiv_id": "2606.00001",
            "arxiv_url": "https://arxiv.org/abs/2606.00001",
            "paper_url": "https://arxiv.org/abs/2606.00001",
            "pdf_url": "https://arxiv.org/pdf/2606.00001",
            "doi": "10.0000/example",
            "citation_count": 5,
        }
    ]
    (data_dir / "2026-06.json").write_text(json.dumps(papers, ensure_ascii=False), encoding="utf-8")


def _read_all_js(output_dir: Path) -> str:
    """拼接 docs/js/ 下所有 JS 文件内容，用于跨模块断言"""
    parts = []
    for f in sorted((output_dir / "js").glob("*.js")):
        parts.append(f.read_text(encoding="utf-8"))
    return "".join(parts)


def test_frontend_generation_uses_compact_dashboard(tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "docs"
    write_sample_month(data_dir)

    generator = HTMLGenerator(data_dir=str(data_dir), output_dir=str(output_dir))
    generator.run()

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    css = (output_dir / "css" / "style.css").read_text(encoding="utf-8")
    js = _read_all_js(output_dir)

    assert "dashboard-summary" in html
    assert "dailyDatePicker" in html
    assert "按日期查看新增论文" in html
    assert "summary-detail" in html
    assert "summary-compare" in html
    assert "summary-spark" in html
    assert "summary-ring" in html
    assert "data-summary-action=\"pdf\"" in html
    assert "data-summary-action=\"smart-cfd\"" in html
    assert "smartCfdTrendsData" in html
    assert "data-trend-mode=\"year\"" in html
    assert "data-trend-mode=\"quarter\"" in html
    assert "data-chart-type=\"line\"" in html
    assert "data-chart-type=\"bar\"" in html
    assert "trendYearSelect" in html
    assert "今日新增" in html
    assert "本月新增" in html
    assert "较上月" in html
    assert "总量" in html
    assert "智能 CFD" in html
    assert "预出版" in html
    assert "筛选条件" in html
    assert "推荐优先" in html
    assert "影响力优先" in html
    assert "影响力分综合影响因子" in html
    assert "选中当前页" in html
    assert "复制标识符" in html
    assert "dashboard-summary" in css
    assert "daily-date-picker" in css
    assert "summary-action" in css
    assert "再次点击恢复默认" in css
    assert "summary-spark" in css
    assert "summary-ring" in css
    assert "conic-gradient" in css
    assert "filter-panel" in css
    assert "recommendationScore" in js
    assert "recommendationDetails" in js
    assert "score-pill" in js
    assert "currentDate" in js
    assert "currentSpecial" in js
    assert "summaryActionIsActive" in js
    assert "state.currentDate !== ''" in js
    assert "summaryActions" in js
    assert "stopDatePickerPropagation" in js
    assert "addEventListener('pointerdown', stopDatePickerPropagation)" in js
    assert "addEventListener('click', stopDatePickerPropagation)" in js
    assert "event.stopPropagation()" in js
    assert "event.target.closest('#dailyDatePicker')" in js
    assert ": localToday()" in js
    assert "early-access" in js
    assert "syncDailyPickerToMonth" in js
    assert "SMART_CFD_TRENDS" in js
    assert "currentChartType" in js
    assert "currentMode" in js
    assert "`${month}-01`" in js
    assert "新增 ${state.filteredPapers.length} 篇论文" in js
    assert "filteredPapers.slice(0, state.loadedCount)" in js
    assert "摘要待补全" in js


def test_google_scholar_snippets_are_not_reliable_abstracts():
    """GS snippet 不应作为前端摘要；但若已被可靠来源补全则允许有 abstract。"""
    _RELIABLE_SOURCES = {"crossref", "openalex", "semantic_scholar", "publisher_meta"}
    data_dir = Path(__file__).parent.parent / "data"
    for month_file in data_dir.glob("????-??.json"):
        papers = json.loads(month_file.read_text(encoding="utf-8"))
        for paper in papers:
            if paper.get("abstract_status") == "unreliable_google_scholar_snippet":
                assert paper.get("source") == "google_scholar"
                # 如果已被可靠来源补全，abstract 可不为空
                enriched_by = paper.get("abstract_source", "")
                if enriched_by not in _RELIABLE_SOURCES:
                    assert not (paper.get("abstract") or "").strip()
                    assert (paper.get("scholar_snippet") or "").strip()


def test_incomplete_publication_dates_do_not_drive_homepage_stats_or_sorting(tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "docs"
    data_dir.mkdir()
    from datetime import datetime
    import re

    today = datetime.now().strftime("%Y-%m-%d")
    current_month = today[:7]
    complete_paper = {
        "id": "today",
        "title": "Complete date CFD paper",
        "authors": ["Ada"],
        "abstract": "A reliable abstract about CFD.",
        "published": today,
        "tags": ["流体力学"],
        "keywords": [],
        "categories": ["physics.flu-dyn"],
        "arxiv_url": "https://arxiv.org/abs/2606.00001",
        "paper_url": "https://arxiv.org/abs/2606.00001",
        "pdf_url": "",
    }
    year_only_paper = {
        **complete_paper,
        "id": "year-only",
        "title": "Year only CFD paper",
        "published": today[:4],
    }
    (data_dir / f"{current_month}.json").write_text(
        json.dumps([complete_paper, year_only_paper], ensure_ascii=False),
        encoding="utf-8",
    )

    generator = HTMLGenerator(data_dir=str(data_dir), output_dir=str(output_dir))
    generator.run()

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    js = _read_all_js(output_dir)
    summary_values = re.findall(r'<span class="summary-value">(.*?)</span>', html)

    assert summary_values[:2] == ["1", "1"]
    assert is_complete_publication_date(today)
    assert not is_complete_publication_date(today[:4])
    assert "function isCompleteDate" in js
    assert "function sortTimestamp" in js
    assert "if (!isCompleteDate(paper.published)) return 365;" in js


def test_frontend_template_never_displays_scholar_snippet_as_abstract():
    # 该逻辑在 paper-card.js 中
    templates = Path(__file__).parent.parent / "scripts" / "templates"
    js_files = sorted(templates.glob("*.js"))
    js = "".join(f.read_text(encoding="utf-8") for f in js_files)

    assert "paper.scholar_snippet" not in js
    assert 'paper["scholar_snippet"]' not in js
    assert "paper['scholar_snippet']" not in js
    assert "unreliable_google_scholar_snippet" in js


def test_google_scholar_snippet_detector_flags_fragments():
    assert _looks_like_scholar_snippet(
        "using neural networks. Furthermore, there is a potential to develop specialized network   datasets"
    )
    assert not _looks_like_scholar_snippet(
        "This paper presents a complete abstract with a clear subject, method, and result. "
        "It explains the computational setup, summarizes the main finding, and ends as a normal paragraph. "
        "The wording is coherent enough to be treated as an abstract rather than a search-result snippet."
    )


def test_abstract_enrichment_helpers():
    inverted = {"This": [0], "abstract": [2], "is": [1], "ordered": [3]}
    assert openalex_abstract(inverted) == "This is abstract ordered"
    assert not is_reliable_abstract("short fragment")
    assert is_reliable_abstract(
        "This abstract describes a complete study with enough methodological and result detail to be useful. "
        "It explains the experimental setup, the computational procedure, the principal observation, and the "
        "interpretation of the results in a coherent paragraph. The final sentence closes normally."
    )


def test_cnki_detail_parser_extracts_metadata():
    html = """
    <section class="brief">
      <h1>计算流体力学代理模型研究 网络首发</h1>
      <h3 class="author"><a>张三1</a><a>李四2</a></h3>
      <h3 class="author"><a>1. 清华大学</a><a>2. 北京大学</a></h3>
      <span class="icon-shoufa"></span>
    </section>
    <div class="doc-top"><a>力学学报</a></div>
    <div class="head-time">2026-06-01</div>
    <div class="abstract-text">本文提出一种面向流场预测的代理模型方法，用于提升计算流体力学仿真效率。</div>
    <p class="keywords"><a>计算流体力学;</a><a>代理模型;</a></p>
    <p class="fund">国家自然科学基金</p>
    <div class="clc-code">O35</div>
    <ul class="module-tab tpl_lieteratures"><li data-id="cited">被引 12</li></ul>
    """

    detail = parse_cnki_detail_html(html)

    assert detail["title"] == "计算流体力学代理模型研究"
    assert detail["authors"] == ["张三", "李四"]
    assert detail["affiliations"] == ["清华大学", "北京大学"]
    assert detail["journal"] == "力学学报"
    assert detail["keywords"] == ["计算流体力学", "代理模型"]
    assert detail["classification"] == "O35"
    assert detail["isOnlineFirst"] is True
    assert detail["citationInfo"]["cited"]["count"] == 12


def test_cnki_detail_merge_and_enrichment_routing():
    paper = {"source": "cnki", "paper_url": "https://kns.cnki.net/kcms2/article/abstract"}
    assert needs_enrichment(paper)

    updated = apply_cnki_detail(paper, {
        "abstract": "这是一段来自 CNKI 详情页的正式摘要。",
        "keywords": ["流体力学", "机器学习"],
        "journal": "工程力学",
        "fund": "国家自然科学基金",
    })

    assert updated["abstract_source"] == "cnki_detail"
    assert updated["abstract_status"] == "enriched"
    assert updated["official_keywords"] == ["机器学习", "流体力学"]
    assert updated["venue"] == "工程力学"
    assert updated["cnki_detail"]["fund"] == "国家自然科学基金"


def test_build_dashboard_stats_pure_computation():
    """build_dashboard_stats 是纯计算函数，验证核心统计逻辑。"""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    current_month = today[:7]
    papers = [
        {
            "id": "1",
            "title": "Paper A",
            "published": today,
            "tags": ["流体力学", "流体力学 / 智能CFD", "流体力学 / 智能CFD / PINN"],
            "pdf_url": "https://example.com/a.pdf",
            "conference": "NeurIPS",
            "is_early_access": False,
        },
        {
            "id": "2",
            "title": "Paper B",
            "published": today,
            "tags": ["流体力学"],
            "pdf_url": "",
            "is_early_access": True,
        },
        {
            "id": "3",
            "title": "Paper C",
            "published": "2020-01-01",
            "tags": ["机器学习"],
            "is_early_access": False,
        },
    ]

    stats = build_dashboard_stats(papers, {current_month: papers[:2]})

    assert stats["today_count"] == 2
    assert stats["total_count"] == 3
    assert stats["published_count"] == 1
    assert stats["preprint_count"] == 2
    assert stats["pdf_count"] == 1
    assert stats["smart_cfd_count"] == 1
    assert stats["early_access_count"] == 1
    assert stats["pdf_rate"] == 33
    assert stats["current_month_count"] == 2


def test_build_smart_cfd_trends_groups_subdirs_by_year_and_quarter():
    surrogate = "流体力学 / 智能CFD / 代理模型与算子学习"
    turbulence = "流体力学 / 智能CFD / 湍流建模与闭合"
    papers_by_month = {
        "2025-12": [
            {"id": "old", "conference": "Journal", "tags": [surrogate]},
        ],
        "2026-01": [
            {"id": "a", "conference": "Journal", "tags": [surrogate]},
            {"id": "b", "tags": []},
        ],
        "2026-03": [
            {"id": "c", "conference": "Conference", "tags": [turbulence]},
        ],
        "not-a-month": [{"id": "ignored"}],
    }

    trends = build_smart_cfd_trends(papers_by_month)

    assert trends["years"] == ["2025", "2026"]
    assert surrogate in trends["subdirs"]
    assert trends["short_names"][surrogate] == "代理模型与算子学习"
    year_2026 = trends["yearly"]["2026"]
    assert year_2026["labels"][0] == "2026-01"
    assert year_2026["trends"][surrogate][0] == 1
    assert year_2026["trends"][surrogate][1] == 0
    assert year_2026["trends"][surrogate][2] == 0
    assert year_2026["trends"][turbulence][2] == 1
    assert trends["quarters"]["labels"] == ["2025 Q4", "2026 Q1"]
    assert trends["quarters"]["trends"][surrogate] == [1, 1]
    assert trends["quarters"]["trends"][turbulence] == [0, 1]


def test_build_dashboard_stats_empty():
    """空论文列表不崩溃，返回安全的默认值。"""
    stats = build_dashboard_stats([], {})

    assert stats["today_count"] == 0
    assert stats["total_count"] == 0
    assert stats["pdf_rate"] == 0
    assert stats["published_rate"] == 0
    assert stats["smart_top_text"] == "子方向待积累"


def test_all_js_modules_are_deployed(tmp_path):
    """generate_html 将所有 JS module 复制到 docs/js/。"""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "docs"
    write_sample_month(data_dir)

    generator = HTMLGenerator(data_dir=str(data_dir), output_dir=str(output_dir))
    generator.run()

    js_dir = output_dir / "js"
    expected_modules = [
        "main.js", "state.js", "utils.js", "paper-card.js",
        "data-loader.js", "filters.js", "dashboard.js", "trend-chart.js",
    ]
    for name in expected_modules:
        assert (js_dir / name).exists(), f"Missing JS module: {name}"


def test_entry_module_uses_es_imports():
    """main.js 是入口模块，使用 import 语法。"""
    templates = Path(__file__).parent.parent / "scripts" / "templates"
    main_js = (templates / "main.js").read_text(encoding="utf-8")
    assert "import " in main_js
    assert "from './state.js'" in main_js


def test_index_html_uses_module_script(tmp_path):
    """生成的 index.html 使用 type=module 加载 JS。"""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "docs"
    write_sample_month(data_dir)

    generator = HTMLGenerator(data_dir=str(data_dir), output_dir=str(output_dir))
    generator.run()

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert '<script type="module"' in html
    assert "js/main.js" in html
