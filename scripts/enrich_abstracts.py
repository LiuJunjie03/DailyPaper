#!/usr/bin/env python3
"""Enrich unreliable Google Scholar snippets and CNKI records with real abstracts.

The script scans monthly data files and tries trusted sources in this order:
CNKI detail pages for CNKI records; otherwise arXiv, Semantic Scholar,
OpenAlex, Crossref, then publisher metadata.
"""

import argparse
import json
import re
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import requests
import yaml
from bs4 import BeautifulSoup

from fetchers.cnki_detail import enrich_cnki_paper


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config.yaml"
USER_AGENT = "DailyPaper abstract enricher (mailto:example@example.com)"


def normalize_title(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def title_matches(expected: str, candidate: str, threshold: float = 0.88) -> bool:
    left = normalize_title(expected)
    right = normalize_title(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= threshold


def clean_abstract(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_reliable_abstract(text: str) -> bool:
    text = clean_abstract(text)
    if len(text) < 220:
        return False
    if text[:1].islower():
        return False
    if re.search(r"\s{2,}", text):
        return False
    if not text.endswith((".", "!", "?")):
        return False
    bad_prefixes = ("cookies", "enable javascript", "this page", "access denied")
    return not text.lower().startswith(bad_prefixes)


def request_json(url: str, params: Optional[Dict] = None, timeout: int = 20) -> Optional[Dict]:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        return None
    return None


def complete_date(value: str) -> str:
    value = str(value or "")
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""


def fetch_arxiv(paper: Dict) -> Optional[Tuple[str, Dict]]:
    arxiv_id = (paper.get("arxiv_id") or "").strip()
    if not arxiv_id:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", paper.get("arxiv_url") or paper.get("paper_url") or "")
        arxiv_id = match.group(1).replace(".pdf", "") if match else ""
    if not arxiv_id:
        return None

    try:
        response = requests.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "xml")
        entry = soup.find("entry")
        if not entry:
            return None
        title_tag = entry.find("title")
        summary_tag = entry.find("summary")
        title = clean_abstract(title_tag.get_text(" ") if title_tag else "")
        abstract = clean_abstract(summary_tag.get_text(" ") if summary_tag else "")
        if title_matches(paper.get("title", ""), title) and is_reliable_abstract(abstract):
            return abstract, {"abstract_source": "arxiv", "arxiv_id": arxiv_id}
    except requests.RequestException:
        return None
    return None


def fetch_semantic_scholar(paper: Dict) -> Optional[Tuple[str, Dict]]:
    data = request_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": paper.get("title", ""),
            "fields": "paperId,title,abstract,externalIds,url,openAccessPdf,publicationDate",
            "limit": 3,
        },
    )
    for item in (data or {}).get("data", []):
        abstract = clean_abstract(item.get("abstract") or "")
        if title_matches(paper.get("title", ""), item.get("title", "")) and is_reliable_abstract(abstract):
            ext = item.get("externalIds") or {}
            return abstract, {
                "abstract_source": "semantic_scholar",
                "semantic_scholar_id": item.get("paperId", ""),
                "doi": ext.get("DOI") or paper.get("doi", ""),
                "arxiv_id": ext.get("ArXiv") or paper.get("arxiv_id", ""),
                "published": complete_date(item.get("publicationDate", "")) or paper.get("published", ""),
            }
    return None


def openalex_abstract(inverted_index: Optional[Dict]) -> str:
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def fetch_openalex(paper: Dict) -> Optional[Tuple[str, Dict]]:
    data = request_json(
        "https://api.openalex.org/works",
        params={"search": paper.get("title", ""), "per-page": 3},
    )
    for item in (data or {}).get("results", []):
        abstract = clean_abstract(openalex_abstract(item.get("abstract_inverted_index")))
        if title_matches(paper.get("title", ""), item.get("title", "")) and is_reliable_abstract(abstract):
            return abstract, {
                "abstract_source": "openalex",
                "doi": (item.get("doi") or "").replace("https://doi.org/", "") or paper.get("doi", ""),
                "openalex_id": item.get("id", ""),
                "published": complete_date(item.get("publication_date", "")) or paper.get("published", ""),
            }
    return None


def fetch_crossref(paper: Dict) -> Optional[Tuple[str, Dict]]:
    doi = (paper.get("doi") or "").strip()
    if doi:
        data = request_json(f"https://api.crossref.org/works/{doi}")
        items = [((data or {}).get("message") or {})]
    else:
        data = request_json(
            "https://api.crossref.org/works",
            params={"query.title": paper.get("title", ""), "rows": 3},
        )
        items = ((data or {}).get("message") or {}).get("items", [])

    for item in items:
        title = " ".join(item.get("title") or [])
        abstract = clean_abstract(item.get("abstract") or "")
        if title_matches(paper.get("title", ""), title) and is_reliable_abstract(abstract):
            return abstract, {
                "abstract_source": "crossref",
                "doi": item.get("DOI") or paper.get("doi", ""),
            }
    return None


def fetch_publisher_meta(paper: Dict) -> Optional[Tuple[str, Dict]]:
    url = paper.get("paper_url") or ""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "lxml")
        selectors = [
            ("meta", {"name": "citation_abstract"}),
            ("meta", {"name": "dc.description"}),
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
        ]
        for tag_name, attrs in selectors:
            tag = soup.find(tag_name, attrs=attrs)
            abstract = clean_abstract(tag.get("content", "") if tag else "")
            if is_reliable_abstract(abstract):
                return abstract, {"abstract_source": "publisher_meta"}
    except requests.RequestException:
        return None
    return None


FETCHERS = [
    fetch_arxiv,
    fetch_semantic_scholar,
    fetch_openalex,
    fetch_crossref,
    fetch_publisher_meta,
]


def safe_print(text: str):
    sys.stdout.buffer.write(str(text).encode("utf-8", errors="replace") + b"\n")
    sys.stdout.flush()


def iter_month_files(data_dir: Path) -> Iterable[Path]:
    return sorted(data_dir.glob("????-??.json"))


def load_config(path: Path) -> Dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def needs_enrichment(paper: Dict, include_cnki: bool = True) -> bool:
    if paper.get("abstract_status") == "unreliable_google_scholar_snippet":
        return True
    if include_cnki and paper.get("source") == "cnki" and not (paper.get("abstract") or "").strip():
        return bool(paper.get("paper_url"))
    return False


def enrich_paper(
    paper: Dict,
    delay: float,
    cnki_fetcher=None,
    cnki_config: Optional[Dict] = None,
    cnki_session: Optional[requests.Session] = None,
) -> Optional[Dict]:
    if paper.get("source") == "cnki" and cnki_fetcher and cnki_config:
        before = (paper.get("abstract") or "").strip()
        updated = enrich_cnki_paper(cnki_fetcher, paper, cnki_config, session=cnki_session)
        after = (updated.get("abstract") or "").strip()
        if after and after != before:
            return updated
        return None

    for fetcher in FETCHERS:
        try:
            result = fetcher(paper)
        except Exception as exc:
            safe_print(f"[warn] {fetcher.__name__} failed for {paper.get('title')}: {exc}")
            result = None
        if delay:
            time.sleep(delay)
        if not result:
            continue
        abstract, metadata = result
        paper["abstract"] = abstract
        paper["abstract_status"] = "enriched"
        paper["abstract_enriched_at"] = datetime.now(timezone.utc).isoformat()
        for key, value in metadata.items():
            if value:
                paper[key] = value
        return paper
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to attempt; 0 means all.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--no-cnki", action="store_true", help="Skip CNKI detail-page enrichment.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    config = load_config(Path(args.config))
    cnki_config = (config.get("sources", {}) or {}).get("cnki", {})
    cnki_fetcher = SimpleNamespace(config=config) if cnki_config and not args.no_cnki else None
    cnki_session = requests.Session() if cnki_fetcher else None
    attempted = enriched = 0

    for path in iter_month_files(data_dir):
        papers = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for paper in papers:
            if not needs_enrichment(paper, include_cnki=not args.no_cnki):
                continue
            if args.limit and attempted >= args.limit:
                break
            attempted += 1
            updated = enrich_paper(
                paper,
                args.delay,
                cnki_fetcher=cnki_fetcher,
                cnki_config=cnki_config,
                cnki_session=cnki_session,
            )
            if updated:
                enriched += 1
                changed = True
                safe_print(f"[ok] {paper.get('title')} <- {paper.get('abstract_source')}")
            else:
                safe_print(f"[missing] {paper.get('title')}")
        if changed and not args.dry_run:
            path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.limit and attempted >= args.limit:
            break

    safe_print(json.dumps({"attempted": attempted, "enriched": enriched, "dry_run": args.dry_run}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
