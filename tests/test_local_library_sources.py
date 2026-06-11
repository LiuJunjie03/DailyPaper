from unittest.mock import patch

from daily_paper.sources import sciencedirect, webofscience
from daily_paper.sources.sciencedirect import fetch_sciencedirect_papers
from daily_paper.sources.webofscience import fetch_webofscience_papers


def test_sciencedirect_skips_on_github_actions_by_default(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("ENABLE_SCIENCEDIRECT", raising=False)
    monkeypatch.delenv("ENABLE_LOCAL_LIBRARY_SOURCES", raising=False)

    config = {"sources": {"sciencedirect": {"enabled": True, "queries": ["fluid dynamics"]}}}

    assert fetch_sciencedirect_papers(config) == []


def test_sciencedirect_keeps_partial_browser_results(monkeypatch):
    monkeypatch.setenv("ENABLE_SCIENCEDIRECT", "true")
    config = {
        "sources": {
            "sciencedirect": {
                "enabled": True,
                "queries": ["fluid dynamics", "turbulence"],
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "max_results_per_query": 5,
            }
        }
    }

    fake_paper = {
        "id": "10.1016/example",
        "title": "Physics-informed CFD flow prediction",
        "authors": "Ada Lovelace",
        "source": "sciencedirect",
        "published": "2026-06-05",
        "doi": "10.1016/example",
    }

    # 直接 mock _fetch_sciencedirect_with_browser，避免 CI 环境下 monkeypatch 内部导入失效
    with patch.object(sciencedirect, "_fetch_sciencedirect_with_browser", return_value=[fake_paper]):
        papers = fetch_sciencedirect_papers(config)

    assert len(papers) == 1
    assert papers[0]["source"] == "sciencedirect"
    assert papers[0]["published"] == "2026-06-05"
    assert papers[0]["doi"] == "10.1016/example"


def test_webofscience_skips_on_github_actions_by_default(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("ENABLE_WOS", raising=False)
    monkeypatch.delenv("ENABLE_LOCAL_LIBRARY_SOURCES", raising=False)

    config = {"sources": {"webofscience": {"enabled": True, "queries": ["fluid dynamics"]}}}

    assert fetch_webofscience_papers(config) == []


def test_webofscience_api_maps_records(monkeypatch):
    monkeypatch.setenv("ENABLE_WOS", "true")

    fake_paper = {
        "id": "10.1234/wos-example",
        "title": "Physics-informed neural networks for CFD",
        "authors": "Ada Lovelace",
        "source": "webofscience",
        "published": "2026-06-05",
        "doi": "10.1234/wos-example",
        "citation_count": 7,
        "external_ids": {"WebOfScience": "WOS:123"},
    }

    # 直接 mock _fetch_webofscience_api，避免 CI 环境下 monkeypatch 内部导入失效
    with patch.object(webofscience, "_fetch_webofscience_api", return_value=[fake_paper]):
        config = {
            "sources": {
                "webofscience": {
                    "enabled": True,
                    "api_key": "test-key",
                    "api_url": "https://api.example.test/wos",
                    "queries": ["fluid dynamics"],
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                }
            }
        }
        papers = fetch_webofscience_papers(config)

    assert len(papers) == 1
    assert papers[0]["source"] == "webofscience"
    assert papers[0]["external_ids"]["WebOfScience"] == "WOS:123"
    assert papers[0]["citation_count"] == 7
    assert papers[0]["doi"] == "10.1234/wos-example"
