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
    calls = []

    def fake_evaluate(url, _script, _source_name, _config, _source_config):
        calls.append(url)
        if len(calls) == 1:
            return {
                "results": [
                    {
                        "title": "Physics-informed CFD flow prediction",
                        "href": "https://www.sciencedirect.com/science/article/pii/example",
                        "authors": "Ada Lovelace",
                        "journal": "Journal of Computational Physics",
                        "date": "5 June 2026",
                        "doi": "10.1016/example",
                        "abstract": "A physics-informed model for computational fluid dynamics.",
                    },
                    {
                        "title": "Old CFD flow prediction",
                        "date": "5 May 2026",
                    },
                ]
            }
        return None

    monkeypatch.setattr(sciencedirect, "evaluate_in_chrome", fake_evaluate)
    monkeypatch.setattr(sciencedirect.time, "sleep", lambda _seconds: None)
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

    papers = fetch_sciencedirect_papers(config)

    assert len(papers) == 1
    assert papers[0]["source"] == "sciencedirect"
    assert papers[0]["published"] == "2026-06-05"
    assert papers[0]["doi"] == "10.1016/example"
    assert "date=2026" in calls[0]


def test_webofscience_skips_on_github_actions_by_default(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("ENABLE_WOS", raising=False)
    monkeypatch.delenv("ENABLE_LOCAL_LIBRARY_SOURCES", raising=False)

    config = {"sources": {"webofscience": {"enabled": True, "queries": ["fluid dynamics"]}}}

    assert fetch_webofscience_papers(config) == []


def test_webofscience_api_maps_records(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "hits": [
                    {
                        "uid": "WOS:123",
                        "title": "Physics-informed neural networks for CFD",
                        "authors": [{"displayName": "Ada Lovelace"}],
                        "sourceTitle": "Physics of Fluids",
                        "publishedDate": "2026-06-05",
                        "doi": "10.1234/wos-example",
                        "timesCited": 7,
                        "keywords": ["CFD", "PINN"],
                    },
                    {
                        "uid": "WOS:old",
                        "title": "Old CFD paper",
                        "publishedDate": "2026-05-05",
                    },
                ]
            }

    def fake_get(url, params=None, headers=None, timeout=30):
        assert url == "https://api.example.test/wos"
        assert params["q"] == "fluid dynamics"
        assert headers["X-ApiKey"] == "test-key"
        return FakeResponse()

    monkeypatch.setattr(webofscience.requests, "get", fake_get)
    monkeypatch.setattr(webofscience.time, "sleep", lambda _seconds: None)
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
