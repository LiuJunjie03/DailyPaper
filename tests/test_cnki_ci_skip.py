import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from daily_paper.sources.cnki import fetch_cnki_papers


def test_cnki_skips_on_github_actions_without_explicit_enable(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("ENABLE_CNKI", raising=False)

    assert fetch_cnki_papers({"sources": {"cnki": {"enabled": True, "queries": ["test"]}}}) == []


def test_cnki_skip_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("ENABLE_CNKI", "false")

    assert fetch_cnki_papers({"sources": {"cnki": {"enabled": True, "queries": ["test"]}}}) == []
