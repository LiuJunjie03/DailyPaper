"""
论文合并与去重逻辑。

从 PaperFetcher 类中提取的纯函数版本：
- identity_keys: 计算论文的唯一标识键
- source_rank: 数据源优先级排序
- merge_two_papers: 合并两篇论文
- merge_paper_list: 对论文列表执行去重合并
"""

import re
from typing import Dict, List, Optional, Callable

from common.text import normalize_title, normalize_doi, normalize_arxiv_id


def identity_keys(paper: Dict) -> List[str]:
    """计算论文的唯一标识键（DOI / ArXiv ID / 归一化标题）"""
    keys = []
    doi = normalize_doi(paper.get("doi", ""))
    arxiv_id = normalize_arxiv_id(paper.get("arxiv_id") or paper.get("id", ""))
    title = normalize_title(paper.get("title", ""))
    if doi:
        keys.append(f"doi:{doi}")
    if arxiv_id and re.match(r"^\d{4}\.\d{4,5}", arxiv_id):
        keys.append(f"arxiv:{arxiv_id}")
    if title:
        keys.append(f"title:{title}")
    return keys


def source_rank(paper: Dict) -> int:
    """数据源优先级排序分数"""
    rank = 0
    source = paper.get("source", "")
    if source == "semantic_scholar":
        rank += 30
    elif source == "crossref":
        rank += 25   # 正式出版元数据，质量高
    elif source == "openalex":
        rank += 20   # 元数据较全，但可能含预印本
    if paper.get("doi"):
        rank += 20
    if paper.get("venue") or paper.get("conference"):
        rank += 10
    if paper.get("citation_count") is not None:
        rank += 5
    return rank


def merge_two_papers(paper_a: Dict, paper_b: Dict, finalize_fn: Optional[Callable] = None) -> Dict:
    """合并两篇论文，保留更丰富的元数据。

    Args:
        paper_a: 第一篇论文
        paper_b: 第二篇论文
        finalize_fn: 可选的论文定稿回调函数。如果提供，合并结果会经由此函数处理；
                     如果不提供，跳过定稿（由调用方处理）。
    """
    # 高优先级作为 primary
    primary, secondary = (paper_b, paper_a) if source_rank(paper_b) >= source_rank(paper_a) else (paper_a, paper_b)
    merged = dict(secondary)
    merged.update({k: v for k, v in primary.items() if v not in (None, "", [], {})})

    for field in ["arxiv_url", "pdf_url", "preprint_pdf_url", "paper_url", "doi", "venue", "conference"]:
        if not merged.get(field):
            merged[field] = paper_a.get(field) or paper_b.get(field) or ""

    merged["citation_count"] = (
        paper_b.get("citation_count")
        if paper_b.get("citation_count") is not None
        else paper_a.get("citation_count")
    )
    merged["keywords"] = list(sorted(set(
        (paper_a.get("keywords") or []) + (paper_b.get("keywords") or [])
    )))
    merged["categories"] = sorted(set((paper_a.get("categories") or []) + (paper_b.get("categories") or [])))
    merged["sources"] = sorted(set(
        (paper_a.get("sources") or [paper_a.get("source", "unknown")])
        + (paper_b.get("sources") or [paper_b.get("source", "unknown")])
    ))
    merged["source"] = primary.get("source") or merged.get("source") or "unknown"

    if finalize_fn is not None:
        merged = finalize_fn(merged)

    return merged


def merge_paper_list(papers: List[Dict], finalize_fn: Optional[Callable] = None) -> List[Dict]:
    """对论文列表执行去重合并。

    Args:
        papers: 待合并的论文列表
        finalize_fn: 可选的论文定稿回调函数，会在每篇论文首次加入列表时调用。

    Returns:
        去重合并后的论文列表
    """
    merged = []
    key_to_index = {}
    for paper in papers:
        if finalize_fn is not None:
            paper = finalize_fn(paper)
        keys = identity_keys(paper)
        existing_index = next((key_to_index[k] for k in keys if k in key_to_index), None)
        if existing_index is None:
            key_to_index.update({k: len(merged) for k in keys})
            merged.append(paper)
            continue

        merged[existing_index] = merge_two_papers(merged[existing_index], paper, finalize_fn=finalize_fn)
        for key in identity_keys(merged[existing_index]):
            key_to_index[key] = existing_index
    return merged
