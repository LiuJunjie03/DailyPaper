"""DailyPaper 主入口：抓取、分类、存储论文

职责：编排各专门模块（classifier / enrich / merger / normalizer / store），
保持向后兼容的公共 API（normalize_title, is_relevant_paper, PaperFetcher 等）。
"""

import os
import re
import calendar
import logging
import argparse
from datetime import datetime, timezone
from typing import Dict, List

import yaml
import arxiv

# 从新模块重新导出，保持向后兼容
from common.text import normalize_title, normalize_doi as _normalize_doi, normalize_arxiv_id as _normalize_arxiv_id
from classifier import (
    term_in_text,
    is_relevant_paper,
    KEYWORD_CANONICAL,
    SUBDOMAIN_RULES,
    PARENT_TAGS,
    FLUID_RELATED_TERMS,
    FLUID_RELATED_TAGS,
    FLUID_RELATED_CATEGORIES,
    extract_paper_keywords as _extract_paper_keywords,
    write_classification_report,
)
from enrich import cascade_enrich_papers
from merger import merge_paper_list as _merge_paper_list
from normalizer import (
    finalize_paper as _finalize_paper,
    get_impact_factor as _get_impact_factor,
    IMPACT_FACTOR_TABLE,
)
from store import load_monthly_data, split_papers_by_month, save_monthly_data, build_month_index

# 向后兼容的 normalize_doi / normalize_arxiv_id（保留原始行为）
def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def normalize_arxiv_id(arxiv_id: str) -> str:
    arxiv_id = (arxiv_id or "").strip()
    arxiv_id = arxiv_id.rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE).lower()


# 配置日志（方便查看抓取过程）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PaperFetcher:
    """论文抓取编排器 — 委托给各专门模块"""

    IMPACT_FACTOR_TABLE = IMPACT_FACTOR_TABLE  # backward compat

    def __init__(self, config_path: str = "config.yaml"):
        """初始化：读取你的自定义yaml配置"""
        self.config = self._load_config(config_path)
        self._validate_config()
        self.arxiv_client = arxiv.Client()
        self.ss_api_key = (
            self.config.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        )

    def set_date_window(self, start_date: str = "", end_date: str = ""):
        """Apply a date window to sources that support month/range fetching."""
        if not start_date and not end_date:
            return
        for source_name in ("arxiv", "crossref", "openalex", "semantic_scholar", "wanfang", "cqvip"):
            source = self.config.get("sources", {}).setdefault(source_name, {})
            if start_date:
                source["start_date"] = start_date
            if end_date:
                source["end_date"] = end_date

    def _validate_config(self):
        """校验 config.yaml 关键字段是否存在"""
        sources = self.config.get("sources")
        if not sources or not isinstance(sources, dict):
            logger.warning("config.yaml 缺少 sources 配置，将不会抓取任何数据源")
            return

        for source_name in ["arxiv", "semantic_scholar", "google_scholar", "cnki", "wanfang", "cqvip"]:
            src = sources.get(source_name)
            if src and not isinstance(src, dict):
                logger.warning(f"config.yaml sources.{source_name} 格式错误（期望字典）")

        categories = self.config.get("categories")
        if not categories or not isinstance(categories, dict):
            logger.warning("config.yaml 缺少 categories 配置，论文分类将无法工作")

    def _load_config(self, config_path: str) -> Dict:
        """加载你的yaml配置，确保结构匹配"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在：{config_path}，请确认文件路径正确")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f"成功加载你的配置文件：{config_path}")
            return config
        except Exception as e:
            raise ValueError(f"配置文件解析失败：{e}")

    # ═══════════════════════════════════════════════════════════
    #  委托方法：供 fetcher 子模块通过 fetcher.xxx 调用
    # ═══════════════════════════════════════════════════════════

    def _finalize_paper(self, paper):
        return _finalize_paper(paper, self.config)

    def get_impact_factor(self, paper):
        return _get_impact_factor(paper, self.IMPACT_FACTOR_TABLE)

    def _flatten_queries(self, raw_queries):
        from common.queries import flatten_queries
        return flatten_queries(raw_queries)

    def extract_official_keywords(self, result):
        from classifier import extract_official_keywords
        return extract_official_keywords(result)

    def extract_paper_keywords(self, paper):
        return _extract_paper_keywords(paper, self.config)

    # ═══════════════════════════════════════════════════════════
    #  数据源抓取委托
    # ═══════════════════════════════════════════════════════════

    def fetch_arxiv_papers(self) -> List[Dict]:
        """从 ArXiv 抓取论文"""
        from fetchers.arxiv_fetcher import fetch_arxiv_papers as _fetch
        return _fetch(self)

    def fetch_crossref_papers(self) -> List[Dict]:
        """Crossref 数据源抓取（正式发表论文）"""
        from fetchers.crossref_fetcher import fetch_crossref_papers as _fetch
        return _fetch(self)

    def fetch_openalex_papers(self) -> List[Dict]:
        """OpenAlex 数据源抓取（开放学术图谱）"""
        from fetchers.openalex_fetcher import fetch_openalex_papers as _fetch
        return _fetch(self)

    def fetch_semantic_scholar_papers(self) -> List[Dict]:
        """用 Semantic Scholar 语义搜索替代关键词匹配"""
        from fetchers.semantic_scholar import fetch_semantic_scholar_papers as _fetch
        return _fetch(self)

    def fetch_google_scholar_papers(self) -> List[Dict]:
        """Google Scholar 数据源抓取"""
        from fetchers.google_scholar import fetch_google_scholar_papers as _fetch
        return _fetch(self)

    def fetch_cnki_papers(self) -> List[Dict]:
        """CNKI 数据源抓取"""
        from fetchers.cnki import fetch_cnki_papers as _fetch
        return _fetch(self)

    def fetch_wanfang_papers(self) -> List[Dict]:
        """Wanfang data source."""
        from fetchers.wanfang import fetch_wanfang_papers as _fetch
        return _fetch(self)

    def fetch_cqvip_papers(self) -> List[Dict]:
        """CQVIP data source."""
        from fetchers.cqvip import fetch_cqvip_papers as _fetch
        return _fetch(self)

    # ═══════════════════════════════════════════════════════════
    #  主编排
    # ═══════════════════════════════════════════════════════════

    def _dispatch_sources(self):
        """从所有已启用的数据源抓取论文，返回原始论文列表"""
        source_steps = [
            ("ArXiv", self.fetch_arxiv_papers),
            ("Crossref", self.fetch_crossref_papers),
            ("OpenAlex", self.fetch_openalex_papers),
            ("Semantic Scholar", self.fetch_semantic_scholar_papers),
            ("Google Scholar", self.fetch_google_scholar_papers),
            ("Wanfang", self.fetch_wanfang_papers),
            ("CQVIP", self.fetch_cqvip_papers),
            ("CNKI", self.fetch_cnki_papers),
        ]
        papers = []
        for name, fetch_fn in source_steps:
            try:
                fetched = fetch_fn()
            except Exception as e:
                logger.warning(f"{name} 抓取失败: {e}")
                fetched = []
            logger.info(f"{name}: {len(fetched)} 篇")
            papers.extend(fetched)
        return papers

    def save_papers(self):
        output_config = self.config.get("output", {})
        data_dir = output_config.get("data_dir", "data")
        os.makedirs(data_dir, exist_ok=True)

        # 从多个数据源抓取
        papers = self._dispatch_sources()

        _finalize = lambda p: _finalize_paper(p, self.config)
        papers = _merge_paper_list([p for p in papers if is_relevant_paper(p)], finalize_fn=_finalize)
        logger.info(f"抓取结果合并去重后: {len(papers)} 篇")

        # 级联补全元数据（Crossref → OpenAlex → Semantic Scholar → publisher meta）
        cascade_enrich_papers(papers, self.config)

        # 重新 merge（级联补全可能新增 DOI/arXiv ID）
        papers = _merge_paper_list(papers, finalize_fn=_finalize)

        # 与历史数据合并
        existing_data = load_monthly_data(data_dir)
        existing_papers = [p for ps in existing_data.values() for p in ps]
        papers = _merge_paper_list([
            p for p in existing_papers + papers
            if is_relevant_paper(p)
        ], finalize_fn=_finalize)
        logger.info(f"Merged with existing monthly data: {len(papers)} papers")

        if not papers:
            logger.warning("未抓取到任何相关论文，且没有可整理的历史数据！")
            return

        write_classification_report(papers, data_dir)

        # 确保所有论文都有 is_early_access 字段（兼容从旧 JSON 加载的历史数据）
        _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for paper in papers:
            if "is_early_access" not in paper:
                _pub = paper.get("published", "")
                paper["is_early_access"] = (
                    len(_pub) >= 10 and _pub > _today
                    and bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))
                )

        # 补全不完整的日期（只有年份的补充为 YYYY-01-01）
        for paper in papers:
            pub = paper.get("published", "")
            if pub and len(pub) == 4 and pub.isdigit():
                paper["published"] = f"{pub}-01-01"
                paper["date_status"] = paper.get("date_status") or "year_only"
            elif pub and len(pub) == 7:
                paper["published"] = f"{pub}-01"
                paper["date_status"] = paper.get("date_status") or "approximate"

        # 按月拆分 → 写入 JSON → 生成索引（委托 store.py）
        month_papers = split_papers_by_month(papers)
        save_monthly_data(month_papers, data_dir, docs_dir="")
        build_month_index(data_dir)


def _month_window(month: str):
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise ValueError("--month must use YYYY-MM format")
    year, month_num = [int(part) for part in month.split("-")]
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year:04d}-{month_num:02d}-01", f"{year:04d}-{month_num:02d}-{last_day:02d}"


def main():
    """主函数：一键抓取+分类+保存+同步"""
    parser = argparse.ArgumentParser(description="Fetch DailyPaper records from configured sources.")
    parser.add_argument("--month", help="Fetch a single month, e.g. 2026-01.")
    parser.add_argument("--start-date", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Inclusive end date, YYYY-MM-DD.")
    args = parser.parse_args()

    try:
        fetcher = PaperFetcher()
        if args.month:
            start_date, end_date = _month_window(args.month)
            fetcher.set_date_window(start_date, end_date)
            logger.info(f"按月抓取窗口: {start_date} 到 {end_date}")
        elif args.start_date or args.end_date:
            fetcher.set_date_window(args.start_date or "", args.end_date or "")
            logger.info(f"按日期抓取窗口: {args.start_date or 'open'} 到 {args.end_date or 'open'}")
        fetcher.save_papers()
        logger.info("\n✅ 全部完成！直接打开 docs/index.html 即可查看结果")
    except Exception as e:
        logger.error(f"运行失败：{e}", exc_info=True)

if __name__ == "__main__":
    main()
