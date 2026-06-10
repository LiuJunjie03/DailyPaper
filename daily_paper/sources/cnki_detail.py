"""CNKI detail-page metadata extraction.

This module brings the CNKI paper-detail workflow into the project codebase.
It extracts full metadata from a CNKI detail page when search results only
provide title/source/date level information.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.text import clean_text

logger = logging.getLogger(__name__)


def _clean_title(text: str) -> str:
    text = clean_text(text)
    return re.sub(r"\s*(附视频|网络首发)\s*$", "", text).strip()


def _links_text(parent) -> List[str]:
    if not parent:
        return []
    return [clean_text(a.get_text(" ")) for a in parent.select("a") if clean_text(a.get_text(" "))]


def parse_cnki_detail_html(html: str) -> Dict:
    """Parse a CNKI detail page into normalized metadata."""
    soup = BeautifulSoup(html or "", "lxml")
    brief = soup.select_one(".brief") or soup

    author_sections = brief.select("h3.author")
    author_links = _links_text(author_sections[0]) if author_sections else []
    authors = []
    for item in author_links:
        name = re.sub(r"\d+$", "", item).strip()
        if name:
            authors.append(name)

    affiliations = _links_text(author_sections[1]) if len(author_sections) > 1 else []
    affiliations = [re.sub(r"^\d+\.\s*", "", item).strip() for item in affiliations]

    keywords = _links_text(soup.select_one("p.keywords"))
    keywords = [kw.rstrip(";；").strip() for kw in keywords if kw.rstrip(";；").strip()]

    title_el = brief.select_one("h1")
    abstract_el = soup.select_one(".abstract-text")
    journal_el = soup.select_one(".doc-top a")
    pub_el = soup.select_one(".head-time")
    fund_el = soup.select_one("p.funds")
    classification_el = soup.select_one(".clc-code")
    toc_el = soup.select_one(".catalog-list, .catalog-listDiv")

    citation_info = {}
    for li in soup.select("ul.module-tab.tpl_lieteratures li"):
        key = li.get("data-id") or clean_text(li.get_text(" "))
        text = clean_text(li.get_text(" "))
        match = re.search(r"\d+", text)
        if key:
            citation_info[key] = {
                "label": re.sub(r"\d+", "", text).strip(),
                "count": int(match.group(0)) if match else 0,
            }

    return {
        "title": _clean_title(title_el.get_text(" ") if title_el else ""),
        "authors": authors,
        "affiliations": affiliations,
        "abstract": clean_text(abstract_el.get_text(" ") if abstract_el else ""),
        "keywords": keywords,
        "fund": clean_text(fund_el.get_text(" ") if fund_el else ""),
        "classification": clean_text(classification_el.get_text(" ") if classification_el else ""),
        "journal": clean_text(journal_el.get_text(" ") if journal_el else ""),
        "pubInfo": clean_text(pub_el.get_text(" ") if pub_el else ""),
        "isOnlineFirst": bool(brief.select_one(".icon-shoufa")),
        "toc": clean_text(toc_el.get_text(" ") if toc_el else ""),
        "citationInfo": citation_info,
    }


def cnki_detail_script() -> str:
    """JavaScript equivalent used by the browser backend."""
    return r"""
async () => {
  for (let i = 0; i < 30; i++) {
    if (document.querySelector('.brief') || document.querySelector('.abstract-text')) break;
    if (document.body.innerText.includes('滑块验证') || document.body.innerText.includes('完成验证')) {
      return { error: 'captcha', message: 'CNKI requires slider verification.' };
    }
    await new Promise(r => setTimeout(r, 500));
  }
  const clean = text => (text || '').replace(/\s+/g, ' ').trim();
  const brief = document.querySelector('.brief') || document;
  if (!brief) return { error: 'missing_detail' };
  const linkTexts = root => Array.from((root || document.createElement('div')).querySelectorAll('a'))
    .map(a => clean(a.innerText)).filter(Boolean);
  const authorSections = Array.from(brief.querySelectorAll('h3.author'));
  const authors = linkTexts(authorSections[0]).map(x => x.replace(/\d+$/, '').trim()).filter(Boolean);
  const affiliations = linkTexts(authorSections[1]).map(x => x.replace(/^\d+\.\s*/, '').trim()).filter(Boolean);
  const keywords = linkTexts(document.querySelector('p.keywords')).map(x => x.replace(/[;；]$/, '').trim()).filter(Boolean);
  const citationInfo = {};
  document.querySelectorAll('ul.module-tab.tpl_lieteratures li').forEach(li => {
    const key = li.getAttribute('data-id') || clean(li.innerText);
    const text = clean(li.innerText);
    const match = text.match(/\d+/);
    citationInfo[key] = {
      label: text.replace(/\d+/, '').trim(),
      count: match ? Number(match[0]) : 0
    };
  });
  const title = clean(brief.querySelector('h1')?.innerText || '').replace(/\s*(附视频|网络首发)\s*$/, '');
  return {
    title,
    authors,
    affiliations,
    abstract: clean(document.querySelector('.abstract-text')?.innerText || ''),
    keywords,
    fund: clean(document.querySelector('p.funds')?.innerText || ''),
    classification: clean(document.querySelector('.clc-code')?.innerText || ''),
    journal: clean(document.querySelector('.doc-top a')?.innerText || ''),
    pubInfo: clean(document.querySelector('.head-time')?.innerText || ''),
    isOnlineFirst: !!brief.querySelector('.icon-shoufa'),
    toc: clean(document.querySelector('.catalog-list, .catalog-listDiv')?.innerText || ''),
    citationInfo
  };
}
"""


def fetch_cnki_detail_with_browser(fetcher, url: str, source_config: Dict) -> Optional[Dict]:
    if not url:
        return None
    if source_config.get("_browser_detail_unavailable"):
        return None
    data = evaluate_in_chrome(url, cnki_detail_script(), "CNKI detail", fetcher.config, source_config)
    if not data or data.get("error"):
        if data and data.get("error") == "captcha":
            logger.warning("CNKI detail CAPTCHA required; skipping detail enrichment.")
        if data is None:
            source_config["_browser_detail_unavailable"] = True
        return None
    return data


def fetch_cnki_detail_with_requests(url: str, session: Optional[requests.Session] = None) -> Optional[Dict]:
    if not url or not url.startswith(("http://", "https://")):
        return None
    sess = session or requests.Session()
    try:
        response = sess.get(
            url,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        if response.status_code != 200:
            return None
        detail = parse_cnki_detail_html(response.text)
        return detail if any(detail.get(k) for k in ("abstract", "keywords", "journal")) else None
    except requests.RequestException:
        return None


def apply_cnki_detail(paper: Dict, detail: Dict) -> Dict:
    """Merge extracted CNKI detail metadata into a paper record."""
    if not detail:
        return paper

    if detail.get("title") and not paper.get("title"):
        paper["title"] = detail["title"]
    if detail.get("authors"):
        paper["authors"] = "; ".join(detail["authors"])
    if detail.get("abstract"):
        paper["abstract"] = detail["abstract"]
        paper["abstract_source"] = "cnki_detail"
        paper["abstract_status"] = "enriched"
        paper["abstract_enriched_at"] = datetime.now(timezone.utc).isoformat()
    if detail.get("keywords"):
        existing = paper.get("official_keywords") or paper.get("keywords") or []
        paper["official_keywords"] = sorted(set(existing + detail["keywords"]))
    if detail.get("journal"):
        paper["venue"] = paper.get("venue") or detail["journal"]
        paper["conference"] = paper.get("conference") or detail["journal"]

    cnki_meta = paper.get("cnki_detail") or {}
    for key in ["affiliations", "fund", "classification", "pubInfo", "isOnlineFirst", "toc", "citationInfo"]:
        if detail.get(key) not in (None, "", [], {}):
            cnki_meta[key] = detail[key]
    if cnki_meta:
        paper["cnki_detail"] = cnki_meta

    return paper


def enrich_cnki_paper(fetcher, paper: Dict, source_config: Dict, session: Optional[requests.Session] = None) -> Dict:
    """Try browser detail extraction first, then static HTML fallback."""
    url = paper.get("paper_url") or ""
    detail = fetch_cnki_detail_with_browser(fetcher, url, source_config)
    if not detail:
        detail = fetch_cnki_detail_with_requests(url, session=session)
    if source_config.get("detail_delay"):
        time.sleep(float(source_config.get("detail_delay", 0)))
    return apply_cnki_detail(paper, detail or {})
