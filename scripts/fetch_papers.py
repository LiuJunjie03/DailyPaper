"""DailyPaper 主入口：抓取、分类、存储论文

职责：编排各专门模块（classifier / enrich / merger / normalizer / store），
保持向后兼容的公共 API（normalize_title, is_relevant_paper, PaperFetcher 等）。
"""

import os
import json
import re
import time
import logging
import argparse
import calendar
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
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
    classify_paper as _classify_paper,
    extract_paper_keywords as _extract_paper_keywords,
    normalize_keywords as _normalize_keywords,
    extract_official_keywords,
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
        return extract_official_keywords(result)

    def extract_paper_keywords(self, paper):
        return _extract_paper_keywords(paper, self.config)

    def classify_paper(self, paper):
        return _classify_paper(paper, self.config)

    def _normalize_keywords(self, keywords):
        return _normalize_keywords(keywords)

    # ═══════════════════════════════════════════════════════════
    #  向后兼容：保留部分内部方法供 fetcher 子模块调用
    # ═══════════════════════════════════════════════════════════

    def _paper_text(self, paper: Dict) -> str:
        parts = [
            paper.get("title", ""),
            paper.get("abstract", ""),
            " ".join(str(cat) for cat in paper.get("categories", []) or []),
            paper.get("conference", ""),
            paper.get("venue", ""),
        ]
        return " ".join(parts).lower()

    def _term_in_text(self, text: str, term: str) -> bool:
        return term_in_text(text, term)

    def _contains_any(self, text: str, terms: List[str]) -> bool:
        return any(self._term_in_text(text, term) for term in terms)

    def _score_subdomains(self, paper: Dict) -> Dict[str, Dict]:
        text = self._paper_text(paper)
        scores = {}
        has_fluid_context = self._contains_any(text, FLUID_RELATED_TERMS) or any(
            str(cat).lower() in FLUID_RELATED_CATEGORIES
            for cat in paper.get("categories", []) or []
        )
        if not has_fluid_context:
            return scores

        for label, rule in SUBDOMAIN_RULES.items():
            strong_hits = [term for term in rule["strong"] if self._term_in_text(text, term)]
            context_hits = [term for term in rule["context"] if self._term_in_text(text, term)]
            negative_hits = [term for term in rule.get("negative", []) if self._term_in_text(text, term)]
            score = len(strong_hits) * 3 + len(context_hits) - len(negative_hits) * 4

            # 智能CFD 子类要求至少有一个 context 匹配（流体/CFD 场景词），
            # 防止仅凭 ML 术语就误分类。
            if "智能CFD" in label and not context_hits:
                score -= 3
            if strong_hits and score >= 3:
                scores[label] = {
                    "score": score,
                    "strong_hits": strong_hits[:8],
                    "context_hits": context_hits[:8],
                    "negative_hits": negative_hits[:5],
                }
        return scores

    def _publication_type(self, paper: Dict) -> str:
        publication_types = [str(t).lower() for t in paper.get("publication_types", []) or []]
        venue = paper.get("venue") or paper.get("conference") or ""
        if "journalarticle" in publication_types or paper.get("doi"):
            return "journal"
        if "conference" in publication_types:
            return "conference"
        if paper.get("arxiv_id"):
            return "preprint" if not venue else "conference"
        return "unknown"

    def _identity_keys(self, paper: Dict) -> List[str]:
        from merger import identity_keys
        return identity_keys(paper)

    def _source_rank(self, paper: Dict) -> int:
        from merger import source_rank
        return source_rank(paper)

    def _merge_two_papers(self, old: Dict, new: Dict) -> Dict:
        from merger import merge_two_papers
        return merge_two_papers(old, new, finalize_fn=lambda p: self._finalize_paper(p))

    def _merge_paper_list(self, papers: List[Dict]) -> List[Dict]:
        return _merge_paper_list(papers, finalize_fn=lambda p: self._finalize_paper(p))

    def write_classification_report(self, papers: List[Dict], data_dir: str):
        write_classification_report(papers, data_dir)

    def get_citation_count(self, title, authors=None, year=None):
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

    def batch_get_citation_counts(self, papers: List[Dict], batch_size: int = 20) -> Dict[str, Optional[int]]:
        """
        批量获取引用数：使用 Semantic Scholar /paper/batch 接口，
        通过 ArXiv ID 批量查询，避免逐篇请求导致速率限制。
        返回 {paper['id']: citation_count} 字典。
        """
        result_map = {}

        # 收集有 ArXiv ID 的论文
        id_pairs = []  # [(paper_id, arxiv_id), ...]
        for p in papers:
            aid = p.get("arxiv_id", "") or ""
            # 兼容：部分论文的 id 字段本身就是 arxiv_id
            if not aid and re.match(r"^\d{4}\.\d{4,5}", str(p.get("id", ""))):
                aid = p.get("id", "")
            if aid:
                # 标准化 ArXiv ID（去除版本号后缀）
                normalized = re.sub(r"v\d+$", "", aid)
                id_pairs.append((p["id"], normalized))

        if not id_pairs:
            return result_map

        headers = {}
        if self.ss_api_key:
            headers["x-api-key"] = self.ss_api_key

        total_batches = (len(id_pairs) + batch_size - 1) // batch_size
        consecutive_failures = 0
        max_consecutive_failures = 3  # 连续失败 3 次则放弃剩余批次

        # 首次请求前等待，确保 Semantic Scholar 限速窗口冷却
        logger.info(f"等待 API 冷却...")
        time.sleep(3)

        # 分批请求
        for i in range(0, len(id_pairs), batch_size):
            batch = id_pairs[i:i + batch_size]
            ss_ids = [f"ArXiv:{arxiv_id}" for _, arxiv_id in batch]
            batch_num = i // batch_size + 1

            url = "https://api.semanticscholar.org/graph/v1/paper/batch"
            params = {"fields": "title,citationCount"}

            try:
                resp = requests.post(url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30)

                # 遇到限速：最多重试 2 次，每次等待递增
                retry_count = 0
                while resp.status_code == 429 and retry_count < 2:
                    retry_count += 1
                    wait = 30 * retry_count  # 30s, 60s
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

                    # 连续失败过多，放弃剩余批次避免无谓等待
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

            # 批次间延迟（API Key 限制 1 req/sec，留足余量）
            if i + batch_size < len(id_pairs):
                time.sleep(3)

        success_count = sum(1 for v in result_map.values() if v is not None)
        logger.info(f"批量引用查询完成: {len(result_map)} 篇，其中 {success_count} 篇有引用数据 ({success_count*100//max(len(result_map),1)}%)")
        return result_map

    # ═══════════════════════════════════════════════════════════
    #  级联补全（委托 enrich 模块）
    # ═══════════════════════════════════════════════════════════

    def _cascade_enrich_papers(self, papers: List[Dict]) -> None:
        cascade_enrich_papers(papers, self.config)

    def _has_reliable_abstract(self, paper: Dict) -> bool:
        return bool((paper.get("abstract") or "").strip()) and paper.get("abstract_status") != "unreliable_google_scholar_snippet"

    def _has_complete_date(self, paper: Dict) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(paper.get("published", ""))))

    def _metadata_complete(self, paper: Dict) -> bool:
        return (
            bool(paper.get("doi") or paper.get("arxiv_id"))
            and self._has_reliable_abstract(paper)
            and self._has_complete_date(paper)
            and bool(paper.get("venue") or paper.get("conference") or paper.get("is_preprint"))
        )

    def _needs_crossref_enrichment(self, paper: Dict) -> bool:
        if paper.get("source") == "arxiv" and not paper.get("doi"):
            return False
        if self._metadata_complete(paper):
            return False
        return (
            not paper.get("doi")
            or not self._has_complete_date(paper)
            or not paper.get("venue")
        )

    def _needs_openalex_enrichment(self, paper: Dict) -> bool:
        return not self._metadata_complete(paper) and (
            not self._has_reliable_abstract(paper)
            or not self._has_complete_date(paper)
            or not paper.get("doi")
            or paper.get("citation_count") is None
            or not paper.get("venue")
        )

    def _needs_semantic_scholar_enrichment(self, paper: Dict) -> bool:
        return not self._metadata_complete(paper) and (
            not self._has_reliable_abstract(paper)
            or not paper.get("semantic_scholar_id")
            or paper.get("citation_count") is None
            or (not paper.get("doi") and not paper.get("arxiv_id"))
        )

    def _needs_publisher_enrichment(self, paper: Dict) -> bool:
        return not self._has_reliable_abstract(paper)

    def _enrich_from_crossref(self, paper: Dict) -> None:
        from enrich import _enrich_from_crossref
        _enrich_from_crossref(paper)

    def _enrich_from_openalex(self, paper: Dict) -> None:
        from enrich import _enrich_from_openalex
        _enrich_from_openalex(paper)

    def _enrich_from_semantic_scholar(self, paper: Dict) -> None:
        from enrich import _enrich_from_semantic_scholar
        _enrich_from_semantic_scholar(paper)

    def _enrich_from_publisher(self, paper: Dict) -> None:
        from enrich import _enrich_from_publisher
        _enrich_from_publisher(paper)

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

    def save_papers(self):
        output_config = self.config.get("output", {})
        data_dir = output_config.get("data_dir", "data")
        os.makedirs(data_dir, exist_ok=True)
        docs_dir = output_config.get("docs_dir", "docs")
        os.makedirs(docs_dir, exist_ok=True)

        # 从多个数据源抓取
        papers = []

        try:
            arxiv_papers = self.fetch_arxiv_papers()
        except Exception as e:
            logger.warning(f"ArXiv 补充源抓取失败，继续使用 Semantic Scholar: {e}")
            arxiv_papers = []
        logger.info(f"ArXiv: {len(arxiv_papers)} 篇")
        papers.extend(arxiv_papers)

        try:
            crossref_papers = self.fetch_crossref_papers()
        except Exception as e:
            logger.warning(f"Crossref 抓取失败: {e}")
            crossref_papers = []
        logger.info(f"Crossref: {len(crossref_papers)} 篇")
        papers.extend(crossref_papers)

        try:
            openalex_papers = self.fetch_openalex_papers()
        except Exception as e:
            logger.warning(f"OpenAlex 抓取失败: {e}")
            openalex_papers = []
        logger.info(f"OpenAlex: {len(openalex_papers)} 篇")
        papers.extend(openalex_papers)

        try:
            ss_papers = self.fetch_semantic_scholar_papers()
        except Exception as e:
            logger.warning(f"Semantic Scholar 抓取失败: {e}")
            ss_papers = []
        logger.info(f"Semantic Scholar: {len(ss_papers)} 篇")
        papers.extend(ss_papers)

        try:
            gs_papers = self.fetch_google_scholar_papers()
        except Exception as e:
            logger.warning(f"Google Scholar 抓取失败: {e}")
            gs_papers = []
        logger.info(f"Google Scholar: {len(gs_papers)} 篇")
        papers.extend(gs_papers)

        try:
            wanfang_papers = self.fetch_wanfang_papers()
        except Exception as e:
            logger.warning(f"Wanfang fetch failed: {e}")
            wanfang_papers = []
        logger.info(f"Wanfang: {len(wanfang_papers)} papers")
        papers.extend(wanfang_papers)

        try:
            cqvip_papers = self.fetch_cqvip_papers()
        except Exception as e:
            logger.warning(f"CQVIP fetch failed: {e}")
            cqvip_papers = []
        logger.info(f"CQVIP: {len(cqvip_papers)} papers")
        papers.extend(cqvip_papers)

        try:
            cnki_papers = self.fetch_cnki_papers()
        except Exception as e:
            logger.warning(f"CNKI 抓取失败: {e}")
            cnki_papers = []
        logger.info(f"CNKI: {len(cnki_papers)} 篇")
        papers.extend(cnki_papers)

        papers = self._merge_paper_list([p for p in papers if is_relevant_paper(p)])
        logger.info(f"抓取结果合并去重后: {len(papers)} 篇")

        # 级联补全元数据（Crossref → OpenAlex → Semantic Scholar → publisher meta）
        self._cascade_enrich_papers(papers)

        # 重新 merge（级联补全可能新增 DOI/arXiv ID）
        papers = self._merge_paper_list(papers)

        # ========== 新增：按月份拆分数据（和main.js加载逻辑对齐） ==========
        existing_papers = []
        for filename in os.listdir(data_dir):
            if not re.fullmatch(r"\d{4}-\d{2}\.json", filename):
                continue
            path = os.path.join(data_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_papers.extend(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to read existing monthly data: {path}, {e}")

        papers = self._merge_paper_list([
            p for p in existing_papers + papers
            if is_relevant_paper(p)
        ])
        logger.info(f"Merged with existing monthly data: {len(papers)} papers")

        if not papers:
            logger.warning("未抓取到任何相关论文，且没有可整理的历史数据！")
            return

        self.write_classification_report(papers, data_dir)

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
                # 只有 YYYY-MM，补充为该月1号
                paper["published"] = f"{pub}-01"
                paper["date_status"] = paper.get("date_status") or "approximate"

        month_papers = {}
        for paper in papers:
            pub = paper.get("published", "")
            parts = pub.split("-")
            if len(parts) >= 2:
                month = f"{parts[0]}-{parts[1]}"
            elif len(parts) == 1 and parts[0].isdigit():
                month = f"{parts[0]}-01"  # 只有年份时归到1月
            else:
                month = "unknown"
            if month not in month_papers:
                month_papers[month] = []
            month_papers[month].append(paper)

        # 生成月份索引文件（data/index.json）
        index_data = []
        for month in sorted(month_papers.keys(), reverse=True):
            month_items = month_papers[month]
            index_data.append({
                "month": month,
                "count": len(month_items),
                "published_count": sum(1 for p in month_items if not p.get("is_preprint")),
                "preprint_count": sum(1 for p in month_items if p.get("is_preprint")),
                "early_access_count": sum(1 for p in month_items if p.get("is_early_access")),
            })
        with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        logger.info(f"月份索引已保存到：{os.path.join(data_dir, 'index.json')}")

        # 保存各月份数据（如data/2026-01.json）—— 已包含official_keywords/custom_keywords
        for month, papers in month_papers.items():
            month_path = os.path.join(data_dir, f"{month}.json")
            with open(month_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            logger.info(f"月份数据已保存到：{month_path}")


def _month_window(month: str) -> Tuple[str, str]:
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
        fetcher = PaperFetcher()  # 实例化时调用__init__，正确初始化self.config
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
