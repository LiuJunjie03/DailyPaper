import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_html import HTMLGenerator, is_complete_publication_date, publication_date_key
from fetchers.cnki import _absolute_cnki_url, _cnki_url
from fetchers.google_scholar import _looks_like_scholar_snippet
from fetchers.cnki_detail import apply_cnki_detail, parse_cnki_detail_html
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


def test_frontend_generation_uses_compact_dashboard(tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "docs"
    write_sample_month(data_dir)

    generator = HTMLGenerator(data_dir=str(data_dir), output_dir=str(output_dir))
    generator.run()

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    css = (output_dir / "css" / "style.css").read_text(encoding="utf-8")
    js = (output_dir / "js" / "main.js").read_text(encoding="utf-8")

    assert "dashboard-summary" in html
    assert "今日新增" in html
    assert "本月新增" in html
    assert "智能 CFD" in html
    assert "筛选条件" in html
    assert "推荐优先" in html
    assert "数据不足时按日期补偿" in html
    assert "选中当前页" in html
    assert "复制标识符" in html
    assert "dashboard-summary" in css
    assert "filter-panel" in css
    assert "recommendationScore" in js
    assert "recommendationDetails" in js
    assert "score-pill" in js
    assert "filteredPapers.slice(0, loadedCount)" in js
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
        "tags": ["娴佷綋鍔涘"],
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
    js = (output_dir / "js" / "main.js").read_text(encoding="utf-8")
    summary_values = re.findall(r'<span class="summary-value">(.*?)</span>', html)

    assert summary_values[:2] == ["1", "1"]
    assert is_complete_publication_date(today)
    assert not is_complete_publication_date(today[:4])
    assert publication_date_key(complete_paper) > publication_date_key(year_only_paper)
    assert "function isCompleteDate" in js
    assert "function sortTimestamp" in js
    assert "if (!isCompleteDate(paper.published)) return 365;" in js


def test_frontend_template_never_displays_scholar_snippet_as_abstract():
    js = (Path(__file__).parent.parent / "scripts" / "templates" / "main.js").read_text(encoding="utf-8")

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
