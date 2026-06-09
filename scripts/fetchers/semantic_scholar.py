"""Semantic Scholar 数据源"""
import requests
import time
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def _complete_date(value: str) -> str:
    value = str(value or "")
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""


def get_citation_count(title, authors=None, year=None):
    """通过 Semantic Scholar API 获取引用次数（单篇查询，保留兼容）"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": title,
        "fields": "title,authors,year,citationCount",
        "limit": 1
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                paper = data["data"][0]
                return paper.get("citationCount", 0)
    except Exception as e:
        logger.warning(f"Semantic Scholar API 查询失败: {e}")
    return None


def batch_get_citation_counts(papers: List[Dict], ss_api_key: str = "", batch_size: int = 20) -> Dict[str, Optional[int]]:
    """批量获取引用数：使用 Semantic Scholar /paper/batch 接口"""
    result_map = {}

    id_pairs = []
    for p in papers:
        aid = p.get("arxiv_id", "") or ""
        if not aid and re.match(r"^\d{4}\.\d{4,5}", str(p.get("id", ""))):
            aid = p.get("id", "")
        if aid:
            normalized = re.sub(r"v\d+$", "", aid)
            id_pairs.append((p["id"], normalized))

    if not id_pairs:
        return result_map

    headers = {}
    if ss_api_key:
        headers["x-api-key"] = ss_api_key

    total_batches = (len(id_pairs) + batch_size - 1) // batch_size
    consecutive_failures = 0
    max_consecutive_failures = 3

    logger.info(f"等待 API 冷却...")
    time.sleep(3)

    for i in range(0, len(id_pairs), batch_size):
        batch = id_pairs[i:i + batch_size]
        ss_ids = [f"ArXiv:{arxiv_id}" for _, arxiv_id in batch]
        batch_num = i // batch_size + 1

        url = "https://api.semanticscholar.org/graph/v1/paper/batch"
        params = {"fields": "title,citationCount"}

        try:
            resp = requests.post(url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30)
            retry_count = 0
            while resp.status_code == 429 and retry_count < 2:
                retry_count += 1
                wait = 30 * retry_count
                logger.warning(f"批量 API 限速 (批次 {batch_num}/{total_batches})，等待 {wait} 秒后重试...")
                time.sleep(wait)
                resp = requests.post(url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30)

            if resp.status_code == 200:
                consecutive_failures = 0
                data = resp.json()
                matched = 0
                for (paper_id, _), item in zip(batch, data):
                    if item and item.get("citationCount") is not None:
                        result_map[paper_id] = item["citationCount"]
                        matched += 1
                    else:
                        result_map[paper_id] = None
                logger.info(f"批量引用: 批次 {batch_num}/{total_batches} 完成 ({matched}/{len(batch)} 篇命中)")
            else:
                consecutive_failures += 1
                logger.warning(f"批量 API 返回 {resp.status_code} (批次 {batch_num}/{total_batches})")
                for paper_id, _ in batch:
                    result_map[paper_id] = None
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询")
                    for paper_id, _ in id_pairs[i + batch_size:]:
                        result_map[paper_id] = None
                    break
        except Exception as e:
            consecutive_failures += 1
            logger.warning(f"批量 API 请求失败: {e}")
            for paper_id, _ in batch:
                result_map[paper_id] = None
            if consecutive_failures >= max_consecutive_failures:
                logger.warning(f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询")
                for paper_id, _ in id_pairs[i + batch_size:]:
                    result_map[paper_id] = None
                break

        if i + batch_size < len(id_pairs):
            time.sleep(3)

    success_count = sum(1 for v in result_map.values() if v is not None)
    logger.info(f"批量引用查询完成: {len(result_map)} 篇，其中 {success_count} 篇有引用数据 ({success_count*100//max(len(result_map),1)}%)")
    return result_map


def fetch_semantic_scholar_papers(fetcher) -> List[Dict]:
    """用 Semantic Scholar 语义搜索替代关键词匹配"""
    ss_config = fetcher.config.get("sources", {}).get("semantic_scholar", {})
    if not ss_config.get("enabled", False):
        logger.info("Semantic Scholar 数据源已禁用")
        return []

    raw_queries = ss_config.get("queries", [])
    if isinstance(raw_queries, dict):
        queries = []
        for values in raw_queries.values():
            queries.extend(values if isinstance(values, list) else [values])
    else:
        queries = raw_queries
    max_per_query = ss_config.get("max_results_per_query", 100)
    days_back = ss_config.get("days_back", 180)

    configured_start = _complete_date(ss_config.get("start_date", ""))
    configured_end = _complete_date(ss_config.get("end_date", ""))
    start_date = (
        datetime.strptime(configured_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if configured_start else datetime.now(timezone.utc) - timedelta(days=days_back)
    )
    end_date = (
        datetime.strptime(configured_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if configured_end else None
    )
    year_from = start_date.year
    year_filter = f"{year_from}-{end_date.year}" if end_date else f"{year_from}-"

    all_papers = []
    seen_ids = set()

    for query in queries:
        logger.info(f"Semantic Scholar 搜索: {query}")
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "fields": "paperId,url,title,abstract,authors,year,citationCount,venue,publicationVenue,publicationDate,publicationTypes,externalIds,openAccessPdf,fieldsOfStudy,journal",
            "limit": max_per_query,
            "year": year_filter
        }

        try:
            headers = {}
            if fetcher.ss_api_key:
                headers["x-api-key"] = fetcher.ss_api_key
            resp = None
            for attempt in range(3):
                try:
                    resp = requests.get(url, params=params, headers=headers, timeout=30)
                    if resp.status_code == 429:
                        wait_seconds = 30 + attempt * 10
                        logger.warning(f"Semantic Scholar API 限速，等待{wait_seconds}秒...")
                        time.sleep(wait_seconds)
                        continue
                    break
                except requests.RequestException as e:
                    wait_seconds = 5 * (attempt + 1)
                    logger.warning(f"Semantic Scholar 网络请求失败，{wait_seconds}秒后重试: {e}")
                    time.sleep(wait_seconds)

            if resp is None:
                logger.warning("Semantic Scholar API 请求失败，跳过本查询")
                continue

            if resp.status_code != 200:
                logger.warning(f"Semantic Scholar API 返回 {resp.status_code}")
                continue

            data = resp.json()
            results = data.get("data", [])

            for item in results:
                ext_ids = item.get("externalIds") or {}
                paper_id = (
                    ext_ids.get("DOI")
                    or ext_ids.get("ArXiv")
                    or item.get("paperId", "")
                )

                if paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)

                pub_date = item.get("publicationDate")
                if pub_date:
                    try:
                        dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if dt < start_date or (end_date and dt > end_date):
                            continue
                        published = pub_date
                    except ValueError:
                        published = str(item.get("year", "2025"))
                else:
                    published = str(item.get("year", "2025"))

                abstract = item.get("abstract") or ""
                title = item.get("title") or ""
                if not title:
                    continue

                arxiv_id = ext_ids.get("ArXiv")
                doi = ext_ids.get("DOI") or ""
                pdf_url = ""
                preprint_pdf_url = ""
                arxiv_url = ""
                oa_pdf = item.get("openAccessPdf") or {}
                if arxiv_id:
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                    preprint_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                if oa_pdf and oa_pdf.get("url"):
                    pdf_url = oa_pdf["url"]

                authors_list = item.get("authors", [])
                authors_str = ", ".join(a.get("name", "") for a in authors_list if a.get("name"))
                publication_types = item.get("publicationTypes") or []
                journal = item.get("journal") or {}
                venue = (
                    item.get("venue")
                    or (item.get("publicationVenue") or {}).get("name")
                    or journal.get("name")
                    or ""
                )
                paper_url = (
                    item.get("url")
                    or (f"https://doi.org/{normalize_doi(doi)}" if doi else "")
                    or arxiv_url
                    or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}"
                )

                paper = {
                    "id": paper_id,
                    "title": title,
                    "authors": authors_str,
                    "abstract": abstract,
                    "published": published,
                    "paper_url": paper_url,
                    "arxiv_id": arxiv_id or "",
                    "arxiv_url": arxiv_url,
                    "pdf_url": pdf_url,
                    "preprint_pdf_url": preprint_pdf_url,
                    "categories": item.get("fieldsOfStudy") or [],
                    "venue": venue,
                    "conference": venue,
                    "publication_types": publication_types,
                    "publication_type": "",
                    "doi": doi,
                    "external_ids": ext_ids,
                    "semantic_scholar_id": item.get("paperId", ""),
                    "code_link": "",
                    "tags": [],
                    "keywords": [],
                    "citation_count": item.get("citationCount"),
                    "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                    "source": "semantic_scholar"
                }

                paper = fetcher._finalize_paper(paper)
                all_papers.append(paper)

            logger.info(f"  → 获取 {len(results)} 篇，累计 {len(all_papers)} 篇")

            # 避免触发限速
            time.sleep(3)

        except Exception as e:
            logger.warning(f"Semantic Scholar 查询失败 ({query}): {e}")
            continue

    logger.info(f"Semantic Scholar 共获取 {len(all_papers)} 篇去重论文")
    return all_papers
