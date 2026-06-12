"""
级联元数据补全模块。

从 fetch_papers.py 提取的独立 enrichment 逻辑，
按 Crossref -> OpenAlex -> Semantic Scholar -> publisher 顺序补全论文元数据。
"""

import concurrent.futures
import json
import logging
import re
import threading
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_CASCADE_JSON_CACHE = {}
_CACHE_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════
#  级联补全工具函数
# ═══════════════════════════════════════════════════════════

def _cascade_request_json(url: str, params: Optional[Dict] = None, timeout: int = 20) -> Optional[Dict]:
    """级联补全专用 JSON 请求，429 自动重试"""
    cache_key = (url, tuple(sorted((params or {}).items())))
    with _CACHE_LOCK:
        if cache_key in _CASCADE_JSON_CACHE:
            return _CASCADE_JSON_CACHE[cache_key]
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": "DailyPaperBot/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                with _CACHE_LOCK:
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
    """判断摘要是否可靠 — 统一版本，合并所有 legacy 变体的最佳实践"""
    # 先清理 HTML 标签和空白
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) < 220:
        return False
    if not text[0].isupper():
        return False
    if text[-1] not in ".!?":
        return False
    bad_prefixes = (
        "cookies", "enable javascript", "we use cookies",
        "this site", "this page", "access denied",
    )
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

def _enrich_from_crossref(paper: Dict) -> Dict:
    """从 Crossref 补全单篇论文的元数据，返回 patch dict 而不原地修改"""
    patch = {}
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
            patch["doi"] = item["DOI"].strip().lower()
        # 补全日期
        if paper.get("date_status") != "reliable":
            date = _cascade_crossref_date(item)
            if date:
                patch["published"] = date
                patch["date_source"] = "crossref"
                patch["date_status"] = "reliable"
        # 补全摘要
        if not paper.get("abstract", "").strip():
            abstract = item.get("abstract", "")
            if abstract:
                abstract = re.sub(r"<[^>]+>", " ", abstract)
                abstract = re.sub(r"\s+", " ", abstract).strip()
                if _is_reliable_abstract(abstract):
                    patch["abstract"] = abstract
                    patch["abstract_status"] = "enriched"
                    patch["abstract_source"] = "crossref"
        # 补全 venue
        if not paper.get("venue"):
            container = item.get("container-title") or []
            if container:
                patch["venue"] = container[0].strip()
                patch["conference"] = paper.get("conference") or patch["venue"]
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("is-referenced-by-count")
            if count is not None:
                patch["citation_count"] = count
    return patch


def _enrich_from_openalex(paper: Dict) -> Dict:
    """从 OpenAlex 补全单篇论文的元数据，返回 patch dict 而不原地修改"""
    patch = {}
    data = _cascade_request_json(
        "https://api.openalex.org/works",
        params={
            "search": paper.get("title", ""),
            "per_page": 3,
            "mailto": "",  # 使用 CROSSREF_MAILTO 环境变量
        },
    )
    if not data:
        return patch

    for item in (data.get("results") or []):
        if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        # 补全 DOI
        if not paper.get("doi"):
            raw_doi = (item.get("doi") or "").replace("https://doi.org/", "")
            if raw_doi:
                patch["doi"] = raw_doi
        # 补全日期
        if paper.get("date_status") != "reliable":
            pub_date = item.get("publication_date") or ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                patch["published"] = pub_date
                patch["date_source"] = "openalex"
                patch["date_status"] = "approximate"
        # 补全摘要（从 inverted index 重建）
        if not paper.get("abstract", "").strip():
            abstract = _cascade_openalex_abstract(item.get("abstract_inverted_index"))
            if _is_reliable_abstract(abstract):
                patch["abstract"] = abstract
                patch["abstract_status"] = "enriched"
                patch["abstract_source"] = "openalex"
        # 补全 venue
        if not paper.get("venue"):
            loc = item.get("primary_location") or {}
            src = loc.get("source") or {}
            venue = src.get("display_name") or ""
            if venue:
                patch["venue"] = venue
                patch["conference"] = paper.get("conference") or venue
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("cited_by_count")
            if count is not None:
                patch["citation_count"] = count
        break  # 只取第一个匹配
    return patch


def _enrich_from_semantic_scholar(paper: Dict) -> Dict:
    """从 Semantic Scholar 补全单篇论文的元数据，返回 patch dict 而不原地修改"""
    data = _cascade_request_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": paper.get("title", ""),
            "fields": "paperId,title,abstract,externalIds,publicationDate,citationCount,venue",
            "limit": 3,
        },
    )
    if not data:
        return {}

    patch = {}
    for item in (data.get("data") or []):
        if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        # 补全 DOI / arXiv ID
        ext = item.get("externalIds") or {}
        if not paper.get("doi") and ext.get("DOI"):
            patch["doi"] = ext["DOI"]
        if not paper.get("arxiv_id") and ext.get("ArXiv"):
            patch["arxiv_id"] = ext["ArXiv"]
            patch["arxiv_url"] = f"https://arxiv.org/abs/{ext['ArXiv']}"
            patch["preprint_pdf_url"] = f"https://arxiv.org/pdf/{ext['ArXiv']}"
        # 补全日期
        if paper.get("date_status") != "reliable":
            pub_date = item.get("publicationDate") or ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                patch["published"] = pub_date
                patch["date_source"] = "semantic_scholar"
                patch["date_status"] = "approximate"
        # 补全摘要
        if not paper.get("abstract", "").strip():
            abstract = (item.get("abstract") or "").strip()
            if _is_reliable_abstract(abstract):
                patch["abstract"] = abstract
                patch["abstract_status"] = "enriched"
                patch["abstract_source"] = "semantic_scholar"
        # 补全 venue
        if not paper.get("venue"):
            venue = item.get("venue") or ""
            if venue:
                patch["venue"] = venue
                patch["conference"] = paper.get("conference") or venue
        # 补全引用数
        if paper.get("citation_count") is None:
            count = item.get("citationCount")
            if count is not None:
                patch["citation_count"] = count
        # 补全 Semantic Scholar ID
        if not paper.get("semantic_scholar_id") and item.get("paperId"):
            patch["semantic_scholar_id"] = item["paperId"]
        break
    return patch


def _enrich_from_publisher(paper: Dict) -> Dict:
    """从出版商网页 meta 标签补全摘要，返回 patch dict 而不原地修改"""
    if paper.get("abstract", "").strip():
        return {}  # 已有摘要，跳过
    url = paper.get("paper_url") or paper.get("arxiv_url") or ""
    if not url:
        return {}
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "DailyPaperBot/1.0"})
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "lxml")
        for tag_name in ("citation_abstract", "dc.description", "description", "og:description"):
            tag = soup.find("meta", attrs={"name": tag_name}) or soup.find("meta", attrs={"property": tag_name})
            if tag and tag.get("content"):
                abstract = re.sub(r"\s+", " ", tag["content"]).strip()
                if _is_reliable_abstract(abstract):
                    return {
                        "abstract": abstract,
                        "abstract_status": "enriched",
                        "abstract_source": "publisher_meta",
                    }
    except Exception:
        pass
    return {}


# ═══════════════════════════════════════════════════════════
#  主入口：级联补全
# ═══════════════════════════════════════════════════════════

# 全局限流信号量（限制同时进行的 API 请求总数）
_API_SEMAPHORE = threading.Semaphore(8)


def _safe_enrich_from(func, paper: Dict) -> Dict:
    """在信号量保护下执行单个补全函数，异常时记录日志不传播，返回 patch dict"""
    with _API_SEMAPHORE:
        try:
            return func(paper)
        except Exception:
            logger.warning(
                "级联补全子任务异常: func=%s paper=%s",
                getattr(func, "__name__", func),
                paper.get("title", "")[:80],
                exc_info=True,
            )
            return {}


# date_status 优先级：reliable > approximate
_DATE_STATUS_PRIORITY = {"reliable": 2, "approximate": 1}
_DATE_FIELDS = {"published", "date_source", "date_status"}
_EMPTY = (None, "", [], {})


def _merge_patch(paper: Dict, patch: Dict) -> None:
    """将单个 patch 合并到 paper，保证已有字段不被低优先级数据覆盖。

    规则：
    - paper 中已空的字段：直接从 patch 填充
    - paper 中已有值的非日期字段：不覆盖
    - 日期组字段（published/date_source/date_status）：允许高优先级覆盖低优先级
      （如 Crossref 的 reliable 可覆盖 OpenAlex 的 approximate，反之不行）
    """
    patch_prio = _DATE_STATUS_PRIORITY.get(patch.get("date_status", ""), 0)
    paper_prio = _DATE_STATUS_PRIORITY.get(paper.get("date_status", ""), 0)
    date_upgrade = patch_prio > paper_prio

    for k, v in patch.items():
        if v in _EMPTY:
            continue
        existing = paper.get(k)
        if existing not in _EMPTY:
            # 已有值：只允许日期组优先级升级覆盖
            if date_upgrade and k in _DATE_FIELDS:
                paper[k] = v
            continue
        paper[k] = v


def cascade_enrich_papers(papers: List[Dict], config: Dict, delay: float = 0.15, max_workers: int = 4) -> None:
    """对论文列表进行并发级联元数据补全。

    每篇论文的 4 个数据源补全（Crossref/OpenAlex/Semantic Scholar/publisher）
    在线程池内并发执行，因为各源之间无数据依赖。
    原地修改论文字典，不返回新列表。

    Args:
        papers: 论文列表
        config: 全局配置字典（暂未使用，保留兼容）
        delay: 每篇论文处理后的延迟（秒），默认 0.15
        max_workers: 每篇论文最大并发数，默认 4
    """
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

        # 收集本论文需要执行的补全任务
        tasks = []
        if _needs_crossref_enrichment(paper):
            tasks.append((_enrich_from_crossref, paper))
        if _needs_openalex_enrichment(paper):
            tasks.append((_enrich_from_openalex, paper))
        if _needs_semantic_scholar_enrichment(paper):
            tasks.append((_enrich_from_semantic_scholar, paper))
        if _needs_publisher_enrichment(paper):
            tasks.append((_enrich_from_publisher, paper))

        # 并发执行本论文的所有补全任务。
        # 每个任务返回 patch dict（不原地修改 paper），主线程收集后顺序合并，
        # 消除并发写同一 paper dict 的竞态风险。
        if tasks:
            patches = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks), max_workers)) as executor:
                futures = [
                    executor.submit(_safe_enrich_from, func, p)
                    for func, p in tasks
                ]
                for f in futures:
                    try:
                        patches.append(f.result())
                    except Exception:
                        logger.warning(
                            "级联补全线程池异常，降级为串行: paper=%s",
                            paper.get("title", "")[:80],
                            exc_info=True,
                        )
                        # 串行降级逐个重试
                        for func, p in tasks:
                            try:
                                patches.append(func(p))
                            except Exception:
                                logger.warning(
                                    "串行降级仍失败: func=%s paper=%s",
                                    getattr(func, "__name__", func),
                                    paper.get("title", "")[:80],
                                    exc_info=True,
                                )

            # 主线程按优先级合并所有 patch 到 paper（可靠数据不被低优先级覆盖）
            for patch in patches:
                _merge_patch(paper, patch)

        time.sleep(delay)

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
