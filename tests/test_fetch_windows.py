import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_papers import _month_window
from daily_paper.sources import crossref_fetcher, semantic_scholar


def test_month_window_uses_last_day():
    assert _month_window("2024-02") == ("2024-02-01", "2024-02-29")
    assert _month_window("2026-01") == ("2026-01-01", "2026-01-31")


def test_crossref_filters_results_to_configured_month(monkeypatch):
    def fake_request_json(_url, params=None, timeout=20):
        assert "from-pub-date:2026-01-01" in params["filter"]
        assert "until-pub-date:2026-01-31" in params["filter"]
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/march",
                        "title": ["March fluid paper"],
                        "published-online": {"date-parts": [[2026, 3, 31]]},
                        "container-title": ["Journal"],
                        "author": [],
                        "type": "journal-article",
                    },
                    {
                        "DOI": "10.1000/january",
                        "title": ["January fluid paper"],
                        "published-online": {"date-parts": [[2026, 1, 30]]},
                        "container-title": ["Journal"],
                        "author": [],
                        "type": "journal-article",
                    },
                ]
            }
        }

    monkeypatch.setattr(crossref_fetcher, "request_json", fake_request_json)
    config = {
        "sources": {
            "crossref": {
                "enabled": True,
                "queries": ["fluid"],
                "max_results_per_query": 2,
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            }
        }
    }

    papers = crossref_fetcher.fetch_crossref_papers(config)

    assert [paper["doi"] for paper in papers] == ["10.1000/january"]
    assert papers[0]["published"] == "2026-01-30"


def test_semantic_scholar_disabled_reads_config_without_name_error():
    config = {"sources": {"semantic_scholar": {"enabled": False}}}

    assert semantic_scholar.fetch_semantic_scholar_papers(config) == []
