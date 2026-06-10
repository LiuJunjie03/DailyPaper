import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetchers import chinese_html
from fetchers.wanfang import fetch_wanfang_papers


class FakeFetcher:
    def __init__(self, config):
        self.config = config

    def get_impact_factor(self, _paper):
        return None

    def _finalize_paper(self, paper):
        return paper


SEARCH_HTML = """
<html><body>
  <div class="result-item">
    <h3><a href="/paper/detail?id=wf1" title="计算流体力学代理模型研究">计算流体力学代理模型研究</a></h3>
    <span class="author">张三; 李四</span>
    <span class="source">工程力学</span>
    <span class="date">2026-03-12</span>
    <p class="abstract">介绍流场预测代理模型的检索片段。</p>
  </div>
</body></html>
"""


DETAIL_HTML = """
<html><head>
  <meta name="citation_title" content="计算流体力学代理模型研究">
  <meta name="citation_author" content="张三">
  <meta name="citation_author" content="李四">
  <meta name="citation_journal_title" content="工程力学">
  <meta name="citation_publication_date" content="2026-03-12">
  <meta name="citation_abstract" content="本文提出一种面向流场预测的代理模型方法，用于提升计算流体力学仿真效率。">
  <meta name="citation_keywords" content="计算流体力学;代理模型;机器学习">
  <meta name="citation_doi" content="10.1234/example">
</head></html>
"""


def test_chinese_search_parser_extracts_result():
    records = chinese_html.parse_search_results(SEARCH_HTML, "https://example.org/search", {})

    assert records == [{
        "title": "计算流体力学代理模型研究",
        "paper_url": "https://example.org/paper/detail?id=wf1",
        "authors": "张三; 李四",
        "venue": "工程力学",
        "published": "2026-03-12",
        "source_snippet": "介绍流场预测代理模型的检索片段。",
    }]


def test_wanfang_fetcher_uses_detail_metadata(monkeypatch):
    def fake_request_html(url, params=None, timeout=25):
        if "detail" in url:
            return DETAIL_HTML
        assert params == {"q": "计算流体力学"}
        return SEARCH_HTML

    monkeypatch.setattr(chinese_html, "request_html", fake_request_html)
    monkeypatch.setattr(chinese_html.time, "sleep", lambda _seconds: None)

    fetcher = FakeFetcher({
        "sources": {
            "wanfang": {
                "enabled": True,
                "queries": ["计算流体力学"],
                "max_results_per_query": 3,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        }
    })

    papers = fetch_wanfang_papers(fetcher)

    assert len(papers) == 1
    paper = papers[0]
    assert paper["source"] == "wanfang"
    assert paper["title"] == "计算流体力学代理模型研究"
    assert paper["authors"] == "张三; 李四"
    assert paper["abstract_status"] == "enriched"
    assert paper["doi"] == "10.1234/example"
    assert paper["keywords"] == ["计算流体力学", "代理模型", "机器学习"]
