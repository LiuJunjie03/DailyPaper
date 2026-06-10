"""
论文定稿逻辑：影响因子、发表类型、字段归一化、分类与关键词。

从 PaperFetcher 类中提取的纯函数版本：
- IMPACT_FACTOR_TABLE: 常见期刊/会议影响因子静态表
- get_impact_factor: 根据会议/期刊名获取影响因子
- publication_type: 判断论文发表类型
- finalize_paper: 论文定稿（字段归一化 + 分类 + 关键词提取）
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from daily_paper.text import normalize_doi, normalize_arxiv_id
from classifier import classify_paper, extract_paper_keywords, normalize_keywords

# 常见期刊/会议影响因子静态表（可自行扩充）
IMPACT_FACTOR_TABLE = {
    # 期刊
    'Nature': 64.8,
    'Science': 63.8,
    'PAMI': 24.3,
    'JMLR': 6.8,
    'TPAMI': 24.3,
    'IJCV': 19.5,
    'Journal of Computational Physics': 5.6,
    'Computers & Fluids': 3.7,
    'Journal of Fluid Mechanics': 4.0,
    'AIAA Journal': 2.2,
    'International Journal for Numerical Methods in Fluids': 2.1,
    'Physics of Fluids': 3.5,
    'Computational Mechanics': 3.2,
    'Journal of Machine Learning for Science and Technology': 2.5,
    'Neural Networks': 8.0,
    # 会议（无官方IF，给排序参考分值）
    'NeurIPS': 14.0,
    'ICML': 12.0,
    'ICLR': 10.0,
    'CVPR': 11.2,
    'ICCV': 10.5,
    'ECCV': 8.5,
    'ACL': 7.1,
    'EMNLP': 6.2,
    'NAACL': 5.5,
    'AAAI': 7.7,
    'IJCAI': 5.6,
    'KDD': 6.9,
    'IROS': 4.7,
    'ICRA': 4.3,
    'AIAA SciTech Forum': 3.0,
    'ASME Fluids Engineering Division Meeting': 2.5,
    'International Conference on Computational Fluid Dynamics': 3.5,
    'International Conference on Numerical Methods in Fluid Dynamics': 3.0,
    'International Symposium on Turbulence and Shear Flow Phenomena': 3.0,
    'Conference on Machine Learning for Fluid Dynamics': 4.0,
    'International Conference on Computational Mechanics': 3.0,
    'European Conference on Computational Fluid Dynamics': 3.0,
}


def get_impact_factor(paper: Dict, table: Dict) -> Optional[float]:
    """根据会议/期刊名获取影响因子

    Args:
        paper: 论文字典
        table: 影响因子表（期刊名 → 分值）
    """
    # 优先用 conference 字段，否则用 categories/venue
    name = paper.get('conference') or paper.get('venue')
    if not name:
        # 尝试从 categories 里找
        cats = paper.get('categories', [])
        for cat in cats:
            if cat in table:
                return table[cat]
        return None
    # 标准化名称
    for k in table:
        if k.lower() in name.lower():
            return table[k]
    return None


def publication_type(paper: Dict) -> str:
    """判断论文发表类型（journal / conference / preprint / unknown）"""
    publication_types = [str(t).lower() for t in paper.get("publication_types", []) or []]
    venue = paper.get("venue") or paper.get("conference") or ""
    if "journalarticle" in publication_types or paper.get("doi"):
        return "journal"
    if "conference" in publication_types:
        return "conference"
    if paper.get("arxiv_id"):
        return "preprint" if not venue else "conference"
    return "unknown"


def finalize_paper(paper: Dict, config: Dict, classifier_module=None) -> Dict:
    """论文定稿：字段归一化 + 分类 + 关键词提取

    Args:
        paper: 原始论文字典
        config: 项目配置字典（用于分类和关键词提取）
        classifier_module: 可选的分类器模块，需提供 classify_paper /
            extract_paper_keywords / normalize_keywords 三个函数。
            如果不提供，则回退到 PaperFetcher 实例方法。
    """
    # 获取分类/关键词函数
    if classifier_module is not None:
        _classify = classifier_module.classify_paper
        _extract_keywords = classifier_module.extract_paper_keywords
        _normalize_kw = classifier_module.normalize_keywords
    else:
        _classify = lambda p: classify_paper(p, config)
        _extract_keywords = lambda p: extract_paper_keywords(p, config)
        _normalize_kw = normalize_keywords

    paper["venue"] = paper.get("venue") or paper.get("conference") or ""
    paper["conference"] = paper.get("conference") or paper.get("venue") or ""
    paper["doi"] = normalize_doi(paper.get("doi", ""))
    raw_arxiv_id = paper.get("arxiv_id") or ""
    if not raw_arxiv_id and re.match(r"^\d{4}\.\d{4,5}", str(paper.get("id", ""))):
        raw_arxiv_id = paper.get("id", "")
    paper["arxiv_id"] = normalize_arxiv_id(raw_arxiv_id)
    if paper.get("arxiv_id") and not paper.get("arxiv_url"):
        paper["arxiv_url"] = f"https://arxiv.org/abs/{paper['arxiv_id']}"
    if paper.get("arxiv_id") and not paper.get("preprint_pdf_url"):
        paper["preprint_pdf_url"] = f"https://arxiv.org/pdf/{paper['arxiv_id']}"
    paper["paper_url"] = (
        paper.get("paper_url")
        or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")
        or paper.get("arxiv_url")
        or ""
    )
    paper["publication_type"] = paper.get("publication_type") or publication_type(paper)
    paper["is_preprint"] = paper["publication_type"] == "preprint"
    # 预出版检测：published 在未来且有 DOI/venue（已被接收但未正式见刊）
    _pub = paper.get("published", "")
    _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paper["is_early_access"] = (
        len(_pub) >= 10 and _pub > _today
        and bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))
    )
    if not paper["is_preprint"] and "arxiv.org" in str(paper.get("pdf_url", "")):
        paper["preprint_pdf_url"] = paper.get("preprint_pdf_url") or paper["pdf_url"]
        paper["pdf_url"] = ""
    if not paper.get("source"):
        if paper.get("semantic_scholar_id") or paper.get("doi"):
            paper["source"] = "semantic_scholar"
        elif paper.get("arxiv_url") or paper.get("arxiv_id"):
            paper["source"] = "arxiv"
        else:
            paper["source"] = "unknown"
    paper["impact_factor"] = paper.get("impact_factor") or get_impact_factor(paper, IMPACT_FACTOR_TABLE)
    # 日期来源追踪
    if "date_source" not in paper:
        src = paper.get("source", "")
        if src in ("arxiv", "crossref", "openalex", "semantic_scholar", "cnki", "google_scholar"):
            paper["date_source"] = src
        else:
            paper["date_source"] = ""
    if "date_status" not in paper:
        src = paper.get("source", "")
        paper["date_status"] = "reliable" if src in ("arxiv", "crossref", "semantic_scholar") else "approximate"
    paper["tags"] = _classify(paper)
    paper["primary_domain"] = paper["tags"][-1] if paper.get("tags") else ""
    official_keywords = paper.get("official_keywords") or []
    paper["custom_keywords"] = _extract_keywords(paper)
    paper["keywords"] = _normalize_kw(official_keywords + paper["custom_keywords"])
    return paper


def normalize_dates(papers: list) -> None:
    """补全不完整的日期字段（只有年份 → YYYY-01-01，只有年月 → YYYY-MM-01）。原地修改。"""
    for paper in papers:
        pub = paper.get("published", "")
        if pub and len(pub) == 4 and pub.isdigit():
            paper["published"] = f"{pub}-01-01"
            paper["date_status"] = paper.get("date_status") or "year_only"
        elif pub and len(pub) == 7:
            paper["published"] = f"{pub}-01"
            paper["date_status"] = paper.get("date_status") or "approximate"


def ensure_early_access(papers: list) -> None:
    """为缺少 is_early_access 的历史记录计算该字段。原地修改。"""
    _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for paper in papers:
        if "is_early_access" not in paper:
            _pub = paper.get("published", "")
            paper["is_early_access"] = (
                len(_pub) >= 10 and _pub > _today
                and bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))
            )
