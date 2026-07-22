import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from daily_paper.sources.cnki import _absolute_cnki_url, _cnki_advanced_browser_script, _cnki_query_specs, _cnki_url


def test_cnki_urls_can_use_proxy_base():
    config = {
        "home_url": "http://www--cnki--net--https.example.edu:9000/",
        "kns_base_url": "http://kns--cnki--net--https.example.edu:9000/",
    }

    assert _cnki_url(config, "search_page_url", "/kns8s/search") == (
        "http://kns--cnki--net--https.example.edu:9000/kns8s/search"
    )
    assert _cnki_url(config, "home_url", "/") == "http://www--cnki--net--https.example.edu:9000/"
    assert _absolute_cnki_url(config, "/kcms2/article/abstract?v=1") == (
        "http://kns--cnki--net--https.example.edu:9000/kcms2/article/abstract?v=1"
    )


def test_cnki_structured_advanced_query_preserves_exact_journal_filter():
    specs = _cnki_query_specs({
        "advanced_queries": [
            {"topic": "神经网络*(流场+湍流)", "journal": "计算力学学报"},
            "物理信息神经网络 流体力学",
        ]
    })

    assert specs == [
        {"query": "神经网络*(流场+湍流)", "journal": "计算力学学报"},
        {"query": "物理信息神经网络 流体力学", "journal": ""},
    ]


def test_cnki_advanced_script_uses_result_paging_and_partial_status():
    script = _cnki_advanced_browser_script("神经网络", "计算力学学报", 100, 5)

    assert ".gradeSearch" in script
    assert ".pages-next" in script
    assert "pagesRead" in script
    assert "partial" in script
