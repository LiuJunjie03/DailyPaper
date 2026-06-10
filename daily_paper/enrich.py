"""
级联元数据补全模块。

从 fetch_papers.py 提取的独立 enrichment 逻辑，
按 Crossref -> OpenAlex -> Semantic Scholar -> publisher 顺序补全论文元数据。
"""

import json
import logging
import re
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_CASCADE_JSON_CACHE = {}


# ═══════════════════════════════════════════════════════════
#  级联补全工具函数
# ═══════════════════════════════════════════════════════════

def _cascade_request_json(url: str, params: Optional[Dict] = None, timeout: int = 20) -> Optional[Dict]:
    """级联补全专用 JSON 请求，429 自动重试"""
    cache_key = (url, tuple(sorted((params or {}).items())))
    if cache_key in _CASCADE_JSON_CACHE:
        return _CASCADE_JSON_CACHE[cache_key]
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": "DailyPaperBot/1.0 (mailto:research@dailyPaper.org)"})
            if resp.status_code == 200:
                data = resp.json()
                _CASCADE_JSON_CACHE[cache_key] = data
                return data
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def _cascade_normalize_title(title: str) -> str:
    """标题归一化（用于比较）"""
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _cascade_title_matches(expected: str, candidate: str, threshold: float = 0.85) -> bool:
    """判断两个标题是否匹配"""
    left = _cascade_normalize_title(expected)
    right = _cascade_normalize_title(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= threshold


def _cascade_crossref_date(item: Dict) -> str:
    """从 Crossref 工作记录提取日期（published-online > published-print > created）"""
    for field in ("published-online", "published-print", "created"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        dp = parts[0]
        y = dp[0] if len(dp) > 0 else None
        m = dp[1] if len(dp) > 1 else None
        d = dp[2] if len(dp) > 2 else None
        if not y or not m:
            continue
        if not d:
            d = 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    return ""


def _cascade_openalex_abstract(inverted_index: Optional[Dict]) -> str:
    """从 OpenAlex 的 inverted index 重建摘要文本"""
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def _is_reliable_abstract(text: str) -> bool:
    """判断摘要是否可靠"""
    if not text or len(text) < 220:
        return False
    if not text[0].isupper():
        return False
    if "  " in text:
        return False
    if text[-1] not in ".!?":
        return False
    bad_prefixes = ("cookies", "enable javascript", "we use cookies", "this site")
    if any(text.lower().startswith(p) for p in bad_prefixes):
        return False
    return True


# ═══════════════════════════════════════════════════════════
#  元数据完整性判断
# ═══════════════════════════════════════════════════════════

def _has_reliable_abstract(paper: Dict) -> bool:
    return bool((paper.get("abstract") or "").strip()) and paper.get("abstract_status") != "unreliable_google_scholar_snippet"


def _has_complete_date(paper: Dict) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(paper.get("published", ""))))


def _metadata_complete(paper: Dict) -> bool:
    return (
        bool(paper.get("doi") or paper.get("arxiv_id"))
        and _has_reliable_abstract(paper)
        and _has_complete_date(paper)
        and bool(paper.get("venue") or paper.get("conference") or paper.get("is_preprint"))
    )


# ═══════════════════════════════════════════════════════════
#  是否需要各数据源补全
# ═══════════════════════════════════════════════════════════

def _needs_crossref_enrichment(paper: Dict) -> bool:
    # ArXiv 无 DOI 的论文不适合通过 Crossref 补全
    if paper.get("source") == "arxiv" and not paper.get("doi"):
        return False
    # 元数据已完整的无需补全
    if _metadata_complete(paper):
        return False
    # 至少缺少一项关键元数据才需要 Crossref 补全
    return (
        not paper.get("doi")
        or not _has_complete_date(paper)
        or not paper.get("venue")
    )


def _needs_openalex_enrichment(paper: Dict) -> bool:
    return not _metadata_complete(paper) and (
        not _has_reliable_abstract(paper)
        or not _has_complete_date(paper)
        or not paper.get("doi")
        or paper.get("citation_count") is None
        or not paper.get("venue")
    )


def _needs_semantic_scholar_enrichment(paper: Dict) -> bool:
    return not _metadata_complete(paper) and (
        not _has_reliable_abstract(paper)
        or not paper.get("semantic_scholar_id")
        or paper.get("citation_count") is None
        or (not paper.get("doi") and not paper.get("arxiv_id"))
    )


def _needs_publisher_enrichment(paper: Dict) -> bool:
    return not _has_reliable_abstract(paper)


# ═══════════════════════════════════════════════════════════
#  各数据源补全实现
# ═══════════════════════════════════════════════════════════

def _enrich_from_crossref(paper: Dict) -> None:
    """从 Crossref 补全单篇论文的元数据"""
    doi = (paper.get("doi") or "").strip()
    results = []

    # DOI 直查
    if doi:
        data = _cascade_request_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        if data and data.get("message"):
            results.append(data["message"])

    # 标题搜索
    if not results:
        data = _cascade_request_json(
            "https://api.crossref.org/works",
            params={"query.title": paper.get("title", ""), "rows": 3},
        )
        if data:
            for item in ((data.get("message") or {}).get("items") or []):
                item_title = " ".join(item.get("title") or [])
                if _cascade_title_matches(paper.get("title", ""), item_title):
                    results.append(item)
                    break

    for item in results[:1]:
        # 补全 DOI
        if not paper.get("doi") and item.get("DOI"):
            paper["doi"] = item["DOI"].strip().lower()
        # 补全日期
        if paper.get("date_status") != "reliable":
            date = _cascade_crossref_date(item)
            if date:
                paper["published"] = date
                paper["date_source"] = "crossref"
                paper["date_status"] = "reliable"
        # 补全摘要
        if not paper.get("abstract", "").strip():
            abstract = item.get("abstract", "")
            if abstract:
                abstract = re.sub(r"<[^>]+>", " ", abstract)
                abstract = re.sub(r"\s+", " ", abstract).strip()
                if _is_reliable_abstract(abstract):
                    paper["abstract"] = abstract
                    paper["abstract_status"] = "enriched"
                    paper["abstract_source"] = "crossref"
        # 补全 venue
        if not paper.get("venue"):
            container = item.get("container-title") or []
            if container:
                paper["venue"] = container[0].strip()
                paper["conference"] = paper["conference"] or paper["venue"]
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("is-referenced-by-count")
            if count is not None:
                paper["citation_count"] = count


def _enrich_from_openalex(paper: Dict) -> None:
    """从 OpenAlex 补全单篇论文的元数据"""
    data = _cascade_request_json(
        "https://api.openalex.org/works",
        params={
            "search": paper.get("title", ""),
            "per_page": 3,
            "mailto": "research@dailyPaper.org",
        },
    )
    if not data:
        return

    for item in (data.get("results") or []):
        if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        # 补全 DOI
        if not paper.get("doi"):
            raw_doi = (item.get("doi") or "").replace("https://doi.org/", "")
            if raw_doi:
                paper["doi"] = raw_doi
        # 补全日期
        if paper.get("date_status") != "reliable":
            pub_date = item.get("publication_date") or ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                paper["published"] = pub_date
                paper["date_source"] = "openalex"
                paper["date_status"] = "approximate"
        # 补全摘要（从 inverted index 重建）
        if not paper.get("abstract", "").strip():
            abstract = _cascade_openalex_abstract(item.get("abstract_inverted_index"))
            if _is_reliable_abstract(abstract):
                paper["abstract"] = abstract
                paper["abstract_status"] = "enriched"
                paper["abstract_source"] = "openalex"
        # 补全 venue
        if not paper.get("venue"):
            loc = item.get("primary_location") or {}
            src = loc.get("source") or {}
            venue = src.get("display_name") or ""
            if venue:
                paper["venue"] = venue
                paper["conference"] = paper["conference"] or venue
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("cited_by_count")
            if count is not None:
                paper["citation_count"] = count
        break  # 只取第一个匹配


def _enrich_from_semantic_scholar(paper: Dict) -> None:
    """从 Semantic Scholar 补全单篇论文的元数据"""
    data = _cascade_request_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": paper.get("title", ""),
            "fields": "paperId,title,abstract,externalIds,publicationDate,citationCount,venue",
            "limit": 3,
        },
    )
    if not data:
        return

    for item in (data.get("data") or []):
        if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        # 补全 DOI / arXiv ID
        ext = item.get("externalIds") or {}
        if not paper.get("doi") and ext.get("DOI"):
            paper["doi"] = ext["DOI"]
        if not paper.get("arxiv_id") and ext.get("ArXiv"):
            paper["arxiv_id"] = ext["ArXiv"]
            paper["arxiv_url"] = f"https://arxiv.org/abs/{ext['ArXiv']}"
            paper["preprint_pdf_url"] = f"https://arxiv.org/pdf/{ext['ArXiv']}"
        # 补全日期
        if paper.get("date_status") != "reliable":
            pub_date = item.get("publicationDate") or ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                paper["published"] = pub_date
                paper["date_source"] = "semantic_scholar"
                paper["date_status"] = "approximate"
        # 补全摘要
        if not paper.get("abstract", "").strip():
            abstract = (item.get("abstract") or "").strip()
            if _is_reliable_abstract(abstract):
                paper["abstract"] = abstract
                paper["abstract_status"] = "enriched"
                paper["abstract_source"] = "semantic_scholar"
        # 补全 venue
        if not paper.get("venue"):
            venue = item.get("venue") or ""
            if venue:
                paper["venue"] = venue
                paper["conference"] = paper["conference"] or venue
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("citationCount")
            if count is not None:
                paper["citation_count"] = count
        # 补全 Semantic Scholar ID
        if not paper.get("semantic_scholar_id") and item.get("paperId"):
            paper["semantic_scholar_id"] = item["paperId"]
        break


def _enrich_from_publisher(paper: Dict) -> None:
    """从出版商网页 meta 标签补全摘要"""
    if paper.get("abstract", "").strip():
        return  # 已有摘要，跳过
    url = paper.get("paper_url") or paper.get("arxiv_url") or ""
    if not url:
        return
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "DailyPaperBot/1.0"})
        if resp.status_code != 200:
            return
        soup = BeautifulSoup(resp.text, "lxml")
        for tag_name in ("citation_abstract", "dc.description", "description", "og:description"):
            tag = soup.find("meta", attrs={"name": tag_name}) or soup.find("meta", attrs={"property": tag_name})
            if tag and tag.get("content"):
                abstract = re.sub(r"\s+", " ", tag["content"]).strip()
                if _is_reliable_abstract(abstract):
                    paper["abstract"] = abstract
                    paper["abstract_status"] = "enriched"
                    paper["abstract_source"] = "publisher_meta"
                    break
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  主入口：级联补全
# ═══════════════════════════════════════════════════════════

def cascade_enrich_papers(papers: List[Dict], config: Dict, delay: float = 0.15) -> None:
    """对论文列表进行级联元数据补全（Crossref -> OpenAlex -> Semantic Scholar -> publisher）。
    原地修改论文字典，不返回新列表。"""
    enriched_count = 0
    total = len(papers)

    for i, paper in enumerate(papers):
        needs_enrichment = (
            not paper.get("doi")
            or not paper.get("abstract", "").strip()
            or paper.get("date_status") not in ("reliable",)
            or not paper.get("venue")
        )
        if not needs_enrichment:
            continue

        title = paper.get("title", "")
        if not title:
            continue

        before = json.dumps({
            "doi": paper.get("doi"),
            "abstract": bool((paper.get("abstract") or "").strip()),
            "date_status": paper.get("date_status"),
            "venue": paper.get("venue"),
            "citation_count": paper.get("citation_count"),
        }, ensure_ascii=False, sort_keys=True)

        # 级联第1步：Crossref（正式出版元数据；有 DOI 时优先直查）
        if _needs_crossref_enrichment(paper):
            _enrich_from_crossref(paper)
            time.sleep(delay)

        # 级联第2步：OpenAlex（开放摘要/引用/venue 补充）
        if _needs_openalex_enrichment(paper):
            _enrich_from_openalex(paper)
            time.sleep(delay)

        # 级联第3步：Semantic Scholar（最后再用，降低 429 概率）
        if _needs_semantic_scholar_enrichment(paper):
            _enrich_from_semantic_scholar(paper)
            time.sleep(delay)

        # 级联第4步：publisher meta（抓取网页 meta 标签）
        if _needs_publisher_enrichment(paper):
            _enrich_from_publisher(paper)

        after = json.dumps({
            "doi": paper.get("doi"),
            "abstract": bool((paper.get("abstract") or "").strip()),
            "date_status": paper.get("date_status"),
            "venue": paper.get("venue"),
            "citation_count": paper.get("citation_count"),
        }, ensure_ascii=False, sort_keys=True)
        if after != before:
            enriched_count += 1
        if (i + 1) % 20 == 0:
            logger.info(f"级联补全进度: {i+1}/{total}")

    logger.info(f"级联补全完成: {enriched_count}/{total} 篇需要补全")


# ═══════════════════════════════════════════════════════════
#  公共接口 — 供独立补全脚本复用的共享工具函数
# ═══════════════════════════════════════════════════════════

request_json = _cascade_request_json
normalize_title = _cascade_normalize_title
title_matches = _cascade_title_matches
openalex_abstract = _cascade_openalex_abstract
is_reliable_abstract = _is_reliable_abstract
