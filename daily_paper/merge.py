"""
论文合并与去重逻辑。

从 PaperFetcher 类中提取的纯函数版本：
- identity_keys: 计算论文的唯一标识键
- source_rank: 数据源优先级排序
- merge_two_papers: 合并两篇论文
- merge_paper_list: 对论文列表执行去重合并
"""

import re
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

from daily_paper.text import normalize_arxiv_id, normalize_doi, normalize_title


def _author_tokens(paper: Dict) -> set[str]:
    """Return conservative, non-initial author tokens for version matching."""
    return {
        token
        for token in re.findall(r"[a-z]{3,}", str(paper.get("authors", "")).lower())
        if token not in {"and", "the"}
    }


def _authors_compatible(paper_a: Dict, paper_b: Dict) -> bool:
    """Do not title-merge records with known, disjoint author metadata."""
    authors_a = _author_tokens(paper_a)
    authors_b = _author_tokens(paper_b)
    return not authors_a or not authors_b or bool(authors_a & authors_b)


def _split_authors(authors: str) -> list[str]:
    """Split canonical ``;``-separated names, with a safe legacy fallback."""
    text = str(authors or "").strip()
    if not text:
        return []
    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()]
    # Legacy WOS strings were emitted as ``Surname, Given, Surname, Given``.
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 4 and len(parts) % 2 == 0 and all(" " not in part for part in parts[::2]):
        return [f"{parts[index]}, {parts[index + 1]}" for index in range(0, len(parts), 2)]
    return parts or [text]


def _author_signature(author: str) -> tuple[str, str]:
    """Return ``(surname, given-first-initial)`` for common WOS/arXiv forms."""
    text = str(author or "").strip()
    if "," in text:
        surname_part, given_part = text.split(",", 1)
    else:
        tokens = re.findall(r"[a-z]+", text.lower())
        if not tokens:
            return "", ""
        surname_part, given_part = tokens[-1], " ".join(tokens[:-1])
    surname_tokens = re.findall(r"[a-z]+", surname_part.lower())
    given_tokens = re.findall(r"[a-z]+", given_part.lower())
    surname = surname_tokens[-1] if surname_tokens else ""
    initial = given_tokens[0][0] if given_tokens else ""
    return surname, initial


def _wos_preprint_author_evidence(preprint: Dict, formal: Dict) -> bool:
    """Require first-author surname plus a second independent author signal."""
    preprint_authors = [_author_signature(author) for author in _split_authors(preprint.get("authors", ""))]
    formal_authors = [_author_signature(author) for author in _split_authors(formal.get("authors", ""))]
    preprint_authors = [author for author in preprint_authors if author[0]]
    formal_authors = [author for author in formal_authors if author[0]]
    if not preprint_authors or not formal_authors:
        return False

    preprint_first, formal_first = preprint_authors[0], formal_authors[0]
    if preprint_first[0] != formal_first[0]:
        return False
    if preprint_first[1] and formal_first[1] and preprint_first[1] == formal_first[1]:
        return True

    preprint_coauthors = {surname for surname, _ in preprint_authors[1:]}
    formal_coauthors = {surname for surname, _ in formal_authors[1:]}
    return bool(preprint_coauthors & formal_coauthors)


def _publication_year(paper: Dict) -> int | None:
    match = re.match(r"(19|20)\d{2}", str(paper.get("published", "")))
    return int(match.group(0)) if match else None


def _is_arxiv_preprint(paper: Dict) -> bool:
    return paper.get("source") == "arxiv" and (
        bool(paper.get("arxiv_id")) or paper.get("publication_type") in {"", "preprint", None}
    )


def _is_formal_wos_record(paper: Dict) -> bool:
    if paper.get("source") != "webofscience" or paper.get("publication_type") == "preprint":
        return False
    return bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))


def wos_preprint_replacement_reason(paper_a: Dict, paper_b: Dict) -> str:
    """Return a high-confidence WOS-to-arXiv replacement reason, else ``""``.

    WOS Core Collection records normally have no arXiv ID.  DOI equality is
    authoritative.  For records without a DOI on the arXiv side, accept a
    title-only bridge only when the first-author surname and an independent
    first-initial or coauthor signal agree; the fuzzy branch also requires a
    very high token and sequence similarity threshold.
    """
    if _is_arxiv_preprint(paper_a) and _is_formal_wos_record(paper_b):
        preprint, formal = paper_a, paper_b
    elif _is_arxiv_preprint(paper_b) and _is_formal_wos_record(paper_a):
        preprint, formal = paper_b, paper_a
    else:
        return ""

    preprint_doi = normalize_doi(preprint.get("doi", ""))
    formal_doi = normalize_doi(formal.get("doi", ""))
    if preprint_doi and formal_doi and preprint_doi == formal_doi:
        return "doi"

    preprint_title = normalize_title(preprint.get("title", ""))
    formal_title = normalize_title(formal.get("title", ""))
    if not preprint_title or not formal_title or not _wos_preprint_author_evidence(preprint, formal):
        return ""

    preprint_year = _publication_year(preprint)
    formal_year = _publication_year(formal)
    if preprint_year and formal_year and preprint_year > formal_year + 1:
        return ""
    if preprint_title == formal_title:
        return "normalized_title_and_author"

    sequence_ratio = SequenceMatcher(None, preprint_title, formal_title).ratio()
    preprint_tokens = set(re.findall(r"[a-z0-9]+", preprint_title))
    formal_tokens = set(re.findall(r"[a-z0-9]+", formal_title))
    union = preprint_tokens | formal_tokens
    token_jaccard = len(preprint_tokens & formal_tokens) / len(union) if union else 0.0
    if sequence_ratio >= 0.94 and token_jaccard >= 0.85:
        return "high_similarity_title_and_author"
    return ""


def _direct_identity_match(paper_a: Dict, paper_b: Dict) -> bool:
    """Match IDs exactly; title matches require compatible authors when known."""
    doi_a, doi_b = normalize_doi(paper_a.get("doi", "")), normalize_doi(paper_b.get("doi", ""))
    if doi_a and doi_a == doi_b:
        return True
    arxiv_a = normalize_arxiv_id(paper_a.get("arxiv_id") or paper_a.get("id", ""))
    arxiv_b = normalize_arxiv_id(paper_b.get("arxiv_id") or paper_b.get("id", ""))
    if arxiv_a and arxiv_a == arxiv_b and re.match(r"^\d{4}\.\d{4,5}", arxiv_a):
        return True
    title_a, title_b = normalize_title(paper_a.get("title", "")), normalize_title(paper_b.get("title", ""))
    return bool(title_a and title_a == title_b and _authors_compatible(paper_a, paper_b))


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
    elif source == "webofscience":
        rank += 35   # SCI/WoS 正式出版与引用元数据；优先替代 arXiv 预印本
    elif source == "crossref":
        rank += 25   # 正式出版元数据，质量高
    elif source == "sciencedirect":
        rank += 23   # 出版商页面，正式发表元数据
    elif source == "openalex":
        rank += 20   # 元数据较全，但可能含预印本
    elif source == "official_journal":
        rank += 24   # 期刊官网元数据与全文入口
    elif source == "cnki":
        rank += 22
    elif source in ("wanfang", "cqvip"):
        rank += 18
    elif source.startswith("manual_"):
        rank += 16
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
    replacement_reason = wos_preprint_replacement_reason(paper_a, paper_b)
    if replacement_reason:
        primary, secondary = (
            (paper_a, paper_b) if _is_formal_wos_record(paper_a) else (paper_b, paper_a)
        )
    else:
        # 高优先级作为 primary
        primary, secondary = (paper_b, paper_a) if source_rank(paper_b) >= source_rank(paper_a) else (paper_a, paper_b)
    merged = dict(secondary)
    # 注意：0 和 False 被视为有效值并保留（如 citation_count=0）。
    # 空字符串无法用于主动清空 secondary 字段，但当前数据流不需要此能力。
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

    if replacement_reason:
        # 主记录改为 WOS 正式版本，但保留 arXiv 的永久链接和预印本 PDF。
        merged["source"] = "webofscience"
        merged["version_status"] = "wos_formal_replaces_arxiv_preprint"
        merged["replacement_match"] = replacement_reason
        merged["preprint_published"] = secondary.get("published", "")
        has_conference_type = any(
            "conference" in str(item).lower()
            for item in primary.get("publication_types", [])
        )
        merged["publication_type"] = (
            primary.get("publication_type")
            or ("conference" if has_conference_type else "journal")
        )
        merged["is_preprint"] = False

    # 非 google_scholar 主来源不应保留 unreliable_google_scholar_snippet
    if (
        merged.get("source") != "google_scholar"
        and merged.get("abstract_status") == "unreliable_google_scholar_snippet"
    ):
        merged["abstract_status"] = ""

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
    for paper in papers:
        if finalize_fn is not None:
            paper = finalize_fn(paper)
        existing_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if _direct_identity_match(existing, paper) or wos_preprint_replacement_reason(existing, paper)
            ),
            None,
        )
        if existing_index is None:
            merged.append(paper)
            continue

        merged[existing_index] = merge_two_papers(merged[existing_index], paper, finalize_fn=finalize_fn)
    return merged
