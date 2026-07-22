"""Public official-journal current-issue collector for Chinese intelligent CFD."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from daily_paper.classify import is_intelligent_cfd_paper
from daily_paper.dates import in_date_window
from daily_paper.sources.chinese_html import build_paper, request_html
from daily_paper.text import clean_text, normalize_title

logger = logging.getLogger(__name__)


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_issue_links(html: str, base_url: str, profile: dict) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    include = re.compile(profile.get("article_link_pattern") or r"/(?:cn/)?article/(?:doi|id)/|/CN/10\.", re.I)
    exclude = re.compile(profile.get("exclude_link_pattern") or r"(?:pdf|preview|viewType=|citedby|javascript:)", re.I)
    records = []
    seen = set()
    for link in soup.select(profile.get("article_link_selector") or "a[href]"):
        href = link.get("href", "")
        title = clean_text(link.get("title") or link.get_text(" "))
        absolute = _canonical_url(urljoin(base_url, href))
        if not include.search(href) or exclude.search(href) or not (4 <= len(title) <= 160):
            continue
        key = absolute
        if key in seen:
            continue
        seen.add(key)
        records.append({"title": title, "paper_url": absolute, "venue": profile.get("name", "")})
    return records


def fetch_official_journal_papers(config: dict) -> list[dict]:
    source_config = config.get("sources", {}).get("official_chinese_journals", {})
    if not source_config.get("enabled", False):
        return []
    days_back = int(source_config.get("days_back", 180))
    from_date = source_config.get("start_date") or (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    until_date = source_config.get("end_date", "")
    max_per_journal = int(source_config.get("max_results_per_journal", 40))
    detail_delay = float(source_config.get("detail_delay", 0.2))
    papers = []
    seen_titles = set()
    for profile in source_config.get("journals", []):
        if not profile.get("enabled", True) or profile.get("mode", "official_page") != "official_page":
            continue
        current_url = profile.get("current_url", "")
        html = request_html(current_url)
        if not html:
            logger.warning("期刊官网不可用: %s", profile.get("name", current_url))
            continue
        records = parse_issue_links(html, current_url, profile)[:max_per_journal]
        journal_count = 0
        for record in records:
            title_key = normalize_title(record.get("title", ""))
            if not title_key or title_key in seen_titles:
                continue
            record["venue"] = profile.get("name", "")
            paper = build_paper(
                config,
                "official_journal",
                profile.get("name", "中文期刊官网"),
                "journal",
                record,
                {"enrich_details": True, "detail_delay": detail_delay},
            )
            if not paper:
                continue
            paper["journal_priority"] = int(profile.get("priority", 2))
            paper["journal_profile"] = profile.get("name", "")
            paper["access_url"] = paper.get("pdf_url") or paper.get("paper_url") or ""
            paper["fulltext_status"] = "link_available" if paper.get("pdf_url") else "journal_page"
            if not in_date_window(paper.get("published", ""), from_date, until_date):
                continue
            if not is_intelligent_cfd_paper(paper):
                continue
            seen_titles.add(title_key)
            papers.append(paper)
            journal_count += 1
        logger.info("期刊官网 %s: %s 篇智能 CFD 论文", profile.get("name"), journal_count)
        time.sleep(float(source_config.get("journal_delay", 0.3)))
    return papers
