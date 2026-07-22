"""DailyPaper 主入口：抓取、分类、存储论文

职责：编排各专门模块（classifier / enrich / merger / normalizer / store），
保持向后兼容的公共 API（normalize_title, is_relevant_paper, PaperFetcher 等）。
"""

import os
import re
import calendar
import logging
import argparse
from typing import Dict, List

import yaml
import arxiv

# 从 daily_paper 包导入核心模块
from daily_paper.text import normalize_title  # noqa: F401 — 向后兼容再导出
from daily_paper.classify import (
    is_relevant_paper,
    write_classification_report,
    term_in_text,                    # noqa: F401 — 向后兼容再导出
    KEYWORD_CANONICAL,               # noqa: F401 — 向后兼容再导出
    SUBDOMAIN_RULES,                 # noqa: F401 — 向后兼容再导出
    PARENT_TAGS,                     # noqa: F401 — 向后兼容再导出
    FLUID_RELATED_TERMS,             # noqa: F401 — 向后兼容再导出
    FLUID_RELATED_TAGS,              # noqa: F401 — 向后兼容再导出
    FLUID_RELATED_CATEGORIES,        # noqa: F401 — 向后兼容再导出
)
from daily_paper.enrich import cascade_enrich_papers
from daily_paper.merge import merge_paper_list as _merge_paper_list, wos_preprint_replacement_reason
from daily_paper.normalizer import (
    finalize_paper as _finalize_paper,
    normalize_dates,
    ensure_early_access,
)
from daily_paper.storage import load_monthly_data, split_papers_by_month, save_monthly_data, build_month_index

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

    def __init__(self, config_path: str = "config.yaml"):
        """初始化：读取你的自定义yaml配置"""
        self.config = self._load_config(config_path)
        self._validate_config()
        self.arxiv_client = arxiv.Client()
        self.ss_api_key = (
            self.config.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        )
        self._source_health = []  # 数据源健康报告

    def set_date_window(self, start_date: str = "", end_date: str = ""):
        """Apply a date window to sources that support month/range fetching."""
        if not start_date and not end_date:
            return
        for source_name in (
            "arxiv", "crossref", "openalex", "semantic_scholar",
            "wanfang", "cqvip", "sciencedirect", "webofscience",
        ):
            sources = self.config.setdefault("sources", {})
            source = sources.setdefault(source_name, {})
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

        for source_name in [
            "arxiv", "semantic_scholar", "google_scholar", "cnki",
            "wanfang", "cqvip", "crossref", "openalex",
            "sciencedirect", "webofscience",
        ]:
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
    #  数据源抓取委托
    # ═══════════════════════════════════════════════════════════

    def fetch_arxiv_papers(self) -> List[Dict]:
        """从 ArXiv 抓取论文"""
        from daily_paper.sources.arxiv_fetcher import fetch_arxiv_papers as _fetch
        return _fetch(self.config, ss_api_key=self.ss_api_key, arxiv_client=self.arxiv_client)

    def fetch_crossref_papers(self) -> List[Dict]:
        """Crossref 数据源抓取（正式发表论文）"""
        from daily_paper.sources.crossref_fetcher import fetch_crossref_papers as _fetch
        return _fetch(self.config)

    def fetch_openalex_papers(self) -> List[Dict]:
        """OpenAlex 数据源抓取（开放学术图谱）"""
        from daily_paper.sources.openalex_fetcher import fetch_openalex_papers as _fetch
        return _fetch(self.config)

    def fetch_semantic_scholar_papers(self) -> List[Dict]:
        """用 Semantic Scholar 语义搜索替代关键词匹配"""
        from daily_paper.sources.semantic_scholar import fetch_semantic_scholar_papers as _fetch
        return _fetch(self.config, ss_api_key=self.ss_api_key)

    def fetch_google_scholar_papers(self) -> List[Dict]:
        """Google Scholar 数据源抓取"""
        from daily_paper.sources.google_scholar import fetch_google_scholar_papers as _fetch
        return _fetch(self.config)

    def fetch_cnki_papers(self) -> List[Dict]:
        """CNKI 数据源抓取"""
        from daily_paper.sources.cnki import fetch_cnki_papers as _fetch
        return _fetch(self.config)

    def fetch_wanfang_papers(self) -> List[Dict]:
        """Wanfang data source."""
        from daily_paper.sources.wanfang import fetch_wanfang_papers as _fetch
        return _fetch(self.config)

    def fetch_cqvip_papers(self) -> List[Dict]:
        """CQVIP data source."""
        from daily_paper.sources.cqvip import fetch_cqvip_papers as _fetch
        return _fetch(self.config)

    def fetch_sciencedirect_papers(self) -> List[Dict]:
        """ScienceDirect (Elsevier) 数据源 — 需学校网络 + 浏览器"""
        from daily_paper.sources.sciencedirect import fetch_sciencedirect_papers as _fetch
        return _fetch(self.config)

    def fetch_webofscience_papers(self) -> List[Dict]:
        """Web of Science / SCI 数据源 — 需学校网络浏览器或 Clarivate API key"""
        from daily_paper.sources.webofscience import fetch_webofscience_papers as _fetch
        return _fetch(self.config)

    # ═══════════════════════════════════════════════════════════
    #  主编排
    # ═══════════════════════════════════════════════════════════

    def _dispatch_sources(self):
        """从所有已启用的数据源抓取论文，返回原始论文列表"""
        import time

        source_steps = [
            ("ArXiv", self.fetch_arxiv_papers),
            ("Crossref", self.fetch_crossref_papers),
            ("OpenAlex", self.fetch_openalex_papers),
            ("Semantic Scholar", self.fetch_semantic_scholar_papers),
            ("Google Scholar", self.fetch_google_scholar_papers),
            ("ScienceDirect", self.fetch_sciencedirect_papers),
            ("Web of Science", self.fetch_webofscience_papers),
            ("Wanfang", self.fetch_wanfang_papers),
            ("CQVIP", self.fetch_cqvip_papers),
            ("CNKI", self.fetch_cnki_papers),
        ]
        self._source_health = []
        papers = []
        for name, fetch_fn in source_steps:
            t0 = time.monotonic()
            try:
                fetched = fetch_fn()
                status = "ok"
                error = ""
            except Exception as e:
                logger.warning(f"{name} 抓取失败: {e}")
                fetched = []
                status = "error"
                error = str(e)[:120]
            elapsed = round(time.monotonic() - t0, 1)
            logger.info(f"{name}: {len(fetched)} 篇 ({elapsed}s)")
            self._source_health.append({
                "source": name,
                "status": status,
                "count": len(fetched),
                "elapsed_s": elapsed,
                "error": error,
            })
            papers.extend(fetched)
        return papers

    def _print_health_report(self):
        """打印数据源健康报告摘要"""
        if not self._source_health:
            return
        ok_count = sum(1 for h in self._source_health if h["status"] == "ok")
        err_count = sum(1 for h in self._source_health if h["status"] == "error")
        total_fetched = sum(h["count"] for h in self._source_health)
        total_time = sum(h["elapsed_s"] for h in self._source_health)

        logger.info("=" * 60)
        logger.info("Provider Health Report")
        logger.info("=" * 60)
        for h in self._source_health:
            line = f"  {h['source']:<20s} {h['status']:<6s} {h['count']:>4d} 篇  {h['elapsed_s']:>5.1f}s"
            if h["error"]:
                line += f"  ⚠ {h['error']}"
            logger.info(line)
        logger.info("-" * 60)
        logger.info(f"  合计: {ok_count} 正常 / {err_count} 失败 / {total_fetched} 篇 / {total_time:.1f}s")
        logger.info("=" * 60)

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

        # 记录新论文所涉及月份（含上月，处理跨月延迟收录）
        affected_months = set()
        for p in papers:
            pub = p.get("published", "")
            parts = pub.split("-")
            if len(parts) >= 2:
                m = f"{parts[0]}-{parts[1]}"
                affected_months.add(m)
            elif len(parts) == 1 and parts[0].isdigit():
                affected_months.add(f"{parts[0]}-unk")
            elif not pub:
                affected_months.add("unknown")
        # 扩展：每月的上月也加入（跨月收录场景）
        expanded = set(affected_months)
        for m in affected_months:
            if re.fullmatch(r"\d{4}-\d{2}", m):
                year, month_num = int(m[:4]), int(m[5:])
                if month_num == 1:
                    expanded.add(f"{year-1}-12")
                else:
                    expanded.add(f"{year}-{month_num-1:02d}")
        affected_months = expanded

        # WOS 正式版可能在多年后才补充收录；其 arXiv 预印本往往位于完全不同的
        # 月份文件。先在全库定位高置信版本匹配，才能在同一事务中删除旧预印本桶。
        wos_candidates = [paper for paper in papers if paper.get("source") == "webofscience"]
        if wos_candidates:
            historical_data = load_monthly_data(data_dir)
            replacement_months = {
                month
                for month, historical_papers in historical_data.items()
                if any(
                    wos_preprint_replacement_reason(historical, candidate)
                    for historical in historical_papers
                    for candidate in wos_candidates
                )
            }
            if replacement_months:
                affected_months.update(replacement_months)
                logger.info(
                    "WOS 正式版匹配到 %d 个含 arXiv 预印本的历史月份: %s",
                    len(replacement_months),
                    ", ".join(sorted(replacement_months)),
                )

        # 与历史数据合并（仅加载受影响月份，处理去重）
        existing_data = load_monthly_data(data_dir, months=affected_months)
        existing_papers = [p for ps in existing_data.values() for p in ps]
        papers = _merge_paper_list([
            p for p in existing_papers + papers
            if is_relevant_paper(p)
        ], finalize_fn=_finalize)
        logger.info(f"Merged with existing monthly data: {len(papers)} papers")
        logger.info(f"增量写入: 需重写 {len(affected_months)} 个月份文件")

        if not papers:
            logger.warning("未抓取到任何相关论文，且没有可整理的历史数据！")
            return

        write_classification_report(papers, data_dir)

        # 历史数据归一化（委托 normalizer.py）
        ensure_early_access(papers)
        normalize_dates(papers)

        # PDF 全文补全（机会性增强，需本地浏览器 + 学校网络）
        if self.config.get("pdf_enrich", {}).get("enabled", False):
            from daily_paper.pdf_enrich import enrich_pdfs
            enrich_pdfs(papers, self.config)
        else:
            logger.debug("PDF 补全未启用 (pdf_enrich.enabled=false)")

        # 按月拆分 → 增量写入 JSON → 生成索引（委托 store.py）
        month_papers = split_papers_by_month(papers)
        save_monthly_data(month_papers, data_dir, docs_dir="", only_months=affected_months)
        build_month_index(data_dir)

        self._print_health_report()


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
