"""论文数据 schema 定义与校验

兼容现有 dict 格式，不改变任何数据结构。
字段定义参考 DATA_SCHEMA.md。
"""

from typing import List, Optional, TypedDict


class PaperRecord(TypedDict, total=False):
    """论文记录类型定义（与现有 dict 完全兼容，零迁移成本）

    所有字段标记为 Optional（total=False），不会强制校验。
    仅用于 IDE 类型提示和文档目的。
    """
    # 必填字段（实际数据中应有值）
    id: str
    title: str
    authors: str               # 逗号分隔字符串
    published: str             # YYYY-MM-DD 或 YYYY-MM 或 unknown
    source: str                # arxiv / crossref / openalex / semantic_scholar / google_scholar / cnki / wanfang / cqvip / sciencedirect / webofscience

    # URL
    paper_url: str
    arxiv_url: str
    pdf_url: str
    preprint_pdf_url: str

    # 标识符
    doi: str
    arxiv_id: str
    semantic_scholar_id: str

    # 分类
    tags: List[str]
    keywords: List[str]
    primary_domain: str

    # 元数据
    abstract: str
    venue: str
    citation_count: int
    impact_factor: Optional[float]

    # 状态
    is_preprint: bool
    publication_type: str      # preprint / journal / conference / unknown
    is_early_access: bool
    version_status: str        # wos_formal_replaces_arxiv_preprint 等版本生命周期状态
    replacement_match: str     # doi / normalized_title_and_author / high_similarity_title_and_author
    preprint_published: str    # 被替换 arXiv 预印本的首次发布日期
    abstract_status: str
    abstract_source: str
    date_source: str
    date_status: str

    # 来源信息
    sources: List[str]
    categories: List[str]

    # 评分详情
    classification_score: dict

    # 别名字段（已废弃但保留兼容）
    conference: str            # 等同于 venue
    custom_keywords: List[str] # 与 keywords 近乎同步
    official_keywords: List[str]
    code_link: str
    external_ids: dict
    scholar_snippet: str
    publication_types: List[str]

    # 历史兼容（旧数据中存在）
    openalex_id: str
    abstract_enriched_at: str
    publication_date_source: str  # 旧名，等同于 date_source


# 必填字段列表（校验用）
REQUIRED_FIELDS = ["id", "title", "authors", "published", "source"]

# 已知别名字段映射
FIELD_ALIASES = {
    "conference": "venue",
    "custom_keywords": "keywords",
    "publication_date_source": "date_source",
}


def validate_paper(record: dict) -> List[str]:
    """校验论文记录，返回警告列表（空列表表示无问题）

    不抛异常，不修改记录，仅做诊断。
    """
    warnings = []

    # 必填字段检查
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if not value:
            warnings.append(f"缺少必填字段: {field}")

    # 类型检查
    if record.get("citation_count") is not None:
        if not isinstance(record["citation_count"], (int, float)):
            warnings.append(f"citation_count 类型错误: 期望 int/float, 实际 {type(record['citation_count']).__name__}")

    if record.get("tags") is not None:
        if not isinstance(record["tags"], list):
            warnings.append(f"tags 类型错误: 期望 list, 实际 {type(record['tags']).__name__}")

    if record.get("keywords") is not None:
        if not isinstance(record["keywords"], list):
            warnings.append(f"keywords 类型错误: 期望 list, 实际 {type(record['keywords']).__name__}")

    # 日期格式检查
    published = record.get("published", "")
    if published and published != "unknown":
        import re
        if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", published):
            warnings.append(f"published 格式异常: '{published}' (期望 YYYY-MM-DD 或 YYYY-MM)")

    # URL 安全检查
    for url_field in ("paper_url", "pdf_url", "arxiv_url"):
        url = record.get(url_field, "")
        if url and not url.startswith(("http://", "https://")):
            warnings.append(f"{url_field} 非 HTTP(S) URL: '{url[:50]}'")

    return warnings
