"""ArXiv 数据源"""
import re
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import arxiv

logger = logging.getLogger(__name__)


def extract_official_keywords(result) -> List[str]:
    """从 ArXiv 论文的评论/摘要中提取官方关键词"""
    """
    提取论文标注的「官方关键词」（从摘要/评论中匹配 Keywords: xxx 格式）
    匹配规则：支持 Keywords/Key words/关键词 等中英文标注格式
    """
    official_kw = []
    # 拼接可能包含关键词的文本：摘要 + 评论（ArXiv论文的comment字段可能包含期刊/关键词标注）
    text_parts = [
        result.summary.replace("\n", " ").strip(),  # 摘要
        result.comment if result.comment else ""    # 评论字段
    ]
    full_text = " ".join(text_parts).lower()

    # 正则匹配：匹配 "Keywords: xxx,xxx" 或 "Key words: xxx" 或 "关键词：xxx" 等格式
    kw_pattern = r'(?:key\s*words?|关键词)\s*:\s*([^.;\n]+)'
    matches = re.findall(kw_pattern, full_text, re.IGNORECASE)

    if matches:
        # 拆分关键词、去重、清理空格
        for match in matches:
            keywords = re.split(r'[,;]', match)
            keywords = [kw.strip() for kw in keywords if kw.strip()]
            official_kw.extend(keywords)

    # 最终处理：去重 + 转小写（统一格式）
    official_kw = list(set([kw.lower() for kw in official_kw]))
    return official_kw

def fetch_arxiv_papers(fetcher) -> List[Dict]:
    """
    严格按你的新版yaml配置抓取：指定分类、60天、1000篇
    """
    arxiv_config = fetcher.config.get("sources", {}).get("arxiv", {})  # fetcher.config已正确初始化
    if not arxiv_config.get("enabled", False):
        logger.warning("ArXiv数据源已禁用！")
        return []
    
    # 提取你的配置参数
    arxiv_categories = arxiv_config.get("categories", [])
    max_results = arxiv_config.get("max_results", 1000)
    days_back = arxiv_config.get("days_back", 60)
    
    # 构建ArXiv查询：分类用 OR，关键词用 OR，两者 AND 连接
    if arxiv_categories:
        cat_query = " OR ".join([f"cat:{cat}" for cat in arxiv_categories])
    else:
        cat_query = ""
    fluid_kw = "CFD OR fluid dynamics OR turbulence OR aerodynamics OR multiphase flow OR computational fluid dynamics"
    kw_query = f"({fluid_kw})"

    if cat_query:
        query = f"({cat_query}) AND {kw_query}"
    else:
        query = kw_query
    logger.info(f"ArXiv查询条件: {query}")
    
    # 时间范围
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    start_date_str = start_date.strftime("%Y-%m-%d")
    
    logger.info(f"开始抓取：近{days_back}天，最多{max_results}篇，分类：{arxiv_categories}")
    
    # 构建搜索（arxiv API 不支持 SubmissionDate 过滤，改为本地过滤）
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    
    papers_high_if = []
    papers_other = []
    for result in fetcher.arxiv_client.results(search):
        published = result.published
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published < start_date:
            continue
        
        # ========== 核心修改：构建paper字典时，新增官方/自定义关键词字段 ==========
        paper = {
            "id": result.entry_id.split("/")[-1],
            "title": result.title,
            "authors": ", ".join([author.name for author in result.authors]),
            "abstract": result.summary.replace("\n", " ").strip(),
            "published": published.strftime("%Y-%m-%d"),
            "paper_url": result.entry_id,
            "arxiv_id": result.entry_id.split("/")[-1],
            "arxiv_url": result.entry_id,
            "pdf_url": result.pdf_url,
            "categories": result.categories,
            "venue": "",
            "conference": "",
            "publication_types": ["Preprint"],
            "publication_type": "preprint",
            "is_preprint": True,
            "doi": "",
            "external_ids": {"ArXiv": result.entry_id.split("/")[-1]},
            "code_link": "",
            "tags": [],
            "source": "arxiv",
            # 官方关键词（从摘要/评论中提取）
            "official_keywords": fetcher.extract_official_keywords(result),
            # 自定义预设关键词（原有逻辑）
            "custom_keywords": [],
            # 兼容原有keywords字段（合并官方+自定义，去重）
            "keywords": []
        }
        
        if result.comment:
            venues = fetcher.config.get("venues", {})  # fetcher.config已正确初始化
            all_venues = venues.get("conferences", []) + venues.get("journals", [])
            for venue in all_venues:
                if venue.lower() in result.comment.lower():
                    paper["conference"] = venue
                    break
        
        # 填充分类标签
        paper = fetcher._finalize_paper(paper)
        # 填充自定义关键词
        paper["custom_keywords"] = fetcher.extract_paper_keywords(paper)
        # 合并官方+自定义关键词，去重（保持原有keywords字段兼容）
        paper["keywords"] = list(set(paper["official_keywords"] + paper["custom_keywords"]))
        
        # 补充影响因子
        paper["impact_factor"] = fetcher.get_impact_factor(paper)

        # 按影响因子分类
        if paper["tags"]:
            if paper["impact_factor"] and paper["impact_factor"] >= 3.0:
                papers_high_if.append(paper)
            else:
                papers_other.append(paper)

    # 批量获取引用数（替代逐篇查询，避免速率限制）
    all_collected = papers_high_if + papers_other
    if all_collected:
        logger.info(f"批量获取 {len(all_collected)} 篇 ArXiv 论文的引用数...")
        citation_map = fetcher.batch_get_citation_counts(all_collected)
        for p in all_collected:
            p["citation_count"] = citation_map.get(p["id"], None)

    # 优先返回高影响因子文献，数量不足时补充其他
    max_results = arxiv_config.get("max_results", 1000)
    selected = papers_high_if[:max_results]
    if len(selected) < max_results:
        selected += papers_other[:max_results-len(selected)]
    logger.info(f"抓取完成：高影响因子{len(papers_high_if)}篇，其他{len(papers_other)}篇，实际返回{len(selected)}篇")
    return selected