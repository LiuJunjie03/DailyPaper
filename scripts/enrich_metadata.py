#!/usr/bin/env python3
"""统一元数据补全脚本 — 按优先级补全日期和摘要。

优先级（日期 & 摘要）：
  arXiv → CrossRef DOI → CrossRef 标题 → OpenAlex → Semantic Scholar → 出版商网页

用法：
  python scripts/enrich_metadata.py                       # 补全所有
  python scripts/enrich_metadata.py --only dates          # 仅日期
  python scripts/enrich_metadata.py --only abstracts      # 仅摘要
  python scripts/enrich_metadata.py --month 2026-01       # 单月
  python scripts/enrich_metadata.py --dry-run             # 预览
  python scripts/enrich_metadata.py --limit 20            # 限制篇数
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from daily_paper.enrich import request_json, normalize_title, title_matches, openalex_abstract

# ── 路径常量 ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
USER_AGENT = "DailyPaperBot/1.0 (mailto:research@dailyPaper.org)"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════
#  共享工具函数
# ═══════════════════════════════════════════════════════════

def safe_print(text: str):
    """安全打印（处理编码问题）"""
    sys.stdout.buffer.write(str(text).encode("utf-8", errors="replace") + b"\n")
    sys.stdout.flush()


def clean_text(text: str) -> str:
    """清理 HTML 实体和多余空白"""
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def complete_date(value: str) -> str:
    """返回完整的 YYYY-MM-DD 日期，不合法则返回空字符串"""
    value = str(value or "")
    # 补全只有年月的：2025-03 → 2025-03-01
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return f"{value}-01"
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""


# ═══════════════════════════════════════════════════════════
#  日期 Fetcher 函数（优先级从高到低）
# ═══════════════════════════════════════════════════════════

def _extract_arxiv_id(paper: Dict) -> str:
    """从论文记录中提取 arXiv ID"""
    aid = (paper.get("arxiv_id") or "").strip()
    if not aid:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})",
                          paper.get("arxiv_url") or paper.get("paper_url") or "")
        aid = match.group(1) if match else ""
    return aid.split("v")[0] if aid else ""


def fetch_arxiv_date(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 arXiv API 获取精确发布日期（权威来源）"""
    arxiv_id = _extract_arxiv_id(paper)
    if not arxiv_id:
        return None
    try:
        resp = requests.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            timeout=15, headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        match = re.search(r"<published>(\d{4}-\d{2}-\d{2})T", resp.text)
        if match:
            date = match.group(1)
            return date, {"date_source": "arxiv", "arxiv_id": arxiv_id}
    except requests.RequestException:
        pass
    return None


def _date_from_crossref_parts(value: Dict) -> str:
    """从 CrossRef date-parts 提取日期"""
    parts = (value or {}).get("date-parts") or []
    if not parts or not parts[0]:
        return ""
    dp = parts[0]
    y = dp[0] if len(dp) > 0 else None
    m = dp[1] if len(dp) > 1 else None
    d = dp[2] if len(dp) > 2 else None
    if not y:
        return ""
    if not m:
        return ""  # 只有年份，不比现有数据好
    if not d:
        d = 1
    return f"{y:04d}-{m:02d}-{d:02d}"


def fetch_crossref_date(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 CrossRef 获取发布日期。优先 DOI 直查，其次标题搜索。
    优先 published-online > published-print > created。"""
    doi = (paper.get("doi") or "").strip()
    results = []

    # DOI 直查（高优先级）
    if doi:
        data = request_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        if data and data.get("message"):
            results.append((data["message"], "crossref_doi"))

    # 标题搜索（次优先级）
    data = request_json(
        "https://api.crossref.org/works",
        params={"query.title": paper.get("title", ""), "rows": 3},
    )
    if data:
        for item in ((data.get("message") or {}).get("items") or []):
            results.append((item, "crossref_title"))

    for item, source in results:
        title = " ".join(item.get("title") or [])
        if title and not title_matches(paper.get("title", ""), title):
            continue
        # 按优先级取日期
        for field in ("published-online", "published-print", "created"):
            date = _date_from_crossref_parts(item.get(field) or {})
            if date:
                return date, {
                    "date_source": source,
                    "doi": item.get("DOI") or paper.get("doi", ""),
                }
    return None


def fetch_openalex_date(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 OpenAlex 获取发布日期"""
    data = request_json(
        "https://api.openalex.org/works",
        params={"search": paper.get("title", ""), "per-page": 3,
                "mailto": "research@dailyPaper.org"},
    )
    for item in (data or {}).get("results", []):
        if not title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        date = complete_date(item.get("publication_date") or "")
        if date:
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            return date, {
                "date_source": "openalex",
                "doi": doi or paper.get("doi", ""),
                "openalex_id": item.get("id", ""),
            }
    return None


def fetch_semantic_scholar_date(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 Semantic Scholar 获取发布日期"""
    data = request_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": paper.get("title", ""), "limit": 3,
                "fields": "paperId,title,publicationDate,externalIds"},
    )
    for item in (data or {}).get("data", []):
        if not title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        date = complete_date(item.get("publicationDate") or "")
        if date:
            ext = item.get("externalIds") or {}
            return date, {
                "date_source": "semantic_scholar",
                "semantic_scholar_id": item.get("paperId", ""),
                "doi": ext.get("DOI") or paper.get("doi", ""),
                "arxiv_id": ext.get("ArXiv") or paper.get("arxiv_id", ""),
            }
    return None


# 日期 fetcher 列表（按优先级）
DATE_FETCHERS = [
    fetch_arxiv_date,
    fetch_crossref_date,
    fetch_openalex_date,
    fetch_semantic_scholar_date,
]


# ═══════════════════════════════════════════════════════════
#  摘要 Fetcher 函数（优先级从高到低）
# ═══════════════════════════════════════════════════════════

def is_reliable_abstract(text: str) -> bool:
    """判断摘要是否可靠（长度、格式、内容质量）"""
    text = clean_text(text)
    if len(text) < 220:
        return False
    if text[:1].islower():
        return False
    if re.search(r"\s{2,}", text):
        return False
    if not text.endswith((".", "!", "?")):
        return False
    bad_prefixes = ("cookies", "enable javascript", "this page", "access denied")
    return not text.lower().startswith(bad_prefixes)


def fetch_arxiv_abstract(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 arXiv API 获取摘要（权威来源）"""
    arxiv_id = _extract_arxiv_id(paper)
    if not arxiv_id:
        return None
    try:
        resp = requests.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            timeout=20, headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "xml")
        entry = soup.find("entry")
        if not entry:
            return None
        title_tag = entry.find("title")
        summary_tag = entry.find("summary")
        title = clean_text(title_tag.get_text(" ") if title_tag else "")
        abstract = clean_text(summary_tag.get_text(" ") if summary_tag else "")
        if title_matches(paper.get("title", ""), title) and is_reliable_abstract(abstract):
            return abstract, {"abstract_source": "arxiv", "arxiv_id": arxiv_id}
    except requests.RequestException:
        pass
    return None


def fetch_semantic_scholar_abstract(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 Semantic Scholar 获取摘要"""
    data = request_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": paper.get("title", ""),
                "fields": "paperId,title,abstract,externalIds,publicationDate",
                "limit": 3},
    )
    for item in (data or {}).get("data", []):
        abstract = clean_text(item.get("abstract") or "")
        if title_matches(paper.get("title", ""), item.get("title", "")) and is_reliable_abstract(abstract):
            ext = item.get("externalIds") or {}
            return abstract, {
                "abstract_source": "semantic_scholar",
                "semantic_scholar_id": item.get("paperId", ""),
                "doi": ext.get("DOI") or paper.get("doi", ""),
                "arxiv_id": ext.get("ArXiv") or paper.get("arxiv_id", ""),
            }
    return None


def fetch_openalex_abstract(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 OpenAlex 获取摘要"""
    data = request_json(
        "https://api.openalex.org/works",
        params={"search": paper.get("title", ""), "per-page": 3,
                "mailto": "research@dailyPaper.org"},
    )
    for item in (data or {}).get("results", []):
        abstract = clean_text(openalex_abstract(item.get("abstract_inverted_index")))
        if title_matches(paper.get("title", ""), item.get("title", "")) and is_reliable_abstract(abstract):
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            return abstract, {
                "abstract_source": "openalex",
                "doi": doi or paper.get("doi", ""),
                "openalex_id": item.get("id", ""),
            }
    return None


def fetch_crossref_abstract(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从 CrossRef 获取摘要"""
    doi = (paper.get("doi") or "").strip()
    if doi:
        data = request_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        items = [((data or {}).get("message") or {})]
    else:
        data = request_json(
            "https://api.crossref.org/works",
            params={"query.title": paper.get("title", ""), "rows": 3},
        )
        items = ((data or {}).get("message") or {}).get("items", [])

    for item in items:
        title = " ".join(item.get("title") or [])
        abstract = clean_text(item.get("abstract") or "")
        if title_matches(paper.get("title", ""), title) and is_reliable_abstract(abstract):
            return abstract, {
                "abstract_source": "crossref",
                "doi": item.get("DOI") or paper.get("doi", ""),
            }
    return None


def fetch_publisher_meta(paper: Dict) -> Optional[Tuple[str, Dict]]:
    """从出版商网页 meta 标签获取摘要（最低优先级）"""
    url = paper.get("paper_url") or ""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        for tag_name, attrs in [
            ("meta", {"name": "citation_abstract"}),
            ("meta", {"name": "dc.description"}),
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
        ]:
            tag = soup.find(tag_name, attrs=attrs)
            abstract = clean_text(tag.get("content", "") if tag else "")
            if is_reliable_abstract(abstract):
                return abstract, {"abstract_source": "publisher_meta"}
    except requests.RequestException:
        pass
    return None


# 摘要 fetcher 列表（按优先级）
ABSTRACT_FETCHERS = [
    fetch_arxiv_abstract,
    fetch_semantic_scholar_abstract,
    fetch_openalex_abstract,
    fetch_crossref_abstract,
    fetch_publisher_meta,
]


# ═══════════════════════════════════════════════════════════
#  MetadataEnricher 类
# ═══════════════════════════════════════════════════════════

class MetadataEnricher:
    """统一元数据补全器"""

    def __init__(self, data_dir: Path = DATA_DIR, delay: float = 0.8):
        self.data_dir = data_dir
        self.delay = delay
        self.stats = {"date_attempted": 0, "date_enriched": 0,
                      "abstract_attempted": 0, "abstract_enriched": 0}

    # ── 判断是否需要补全 ──

    def needs_date_enrichment(self, paper: Dict) -> bool:
        """判断论文是否需要日期补全"""
        # 已有可靠来源的跳过
        if paper.get("date_status") == "reliable":
            return False
        pub = paper.get("published", "")
        # 无日期
        if not pub or pub in ("unknown", "none", ""):
            return True
        # 只有年份（4位数字）
        if re.fullmatch(r"\d{4}", pub):
            return True
        # YYYY-01-01 且来源不是 arXiv（arXiv 的 1 号是真实的）
        if pub.endswith("-01-01") and paper.get("date_source") not in ("arxiv", ""):
            # 检查是否已有来源确认
            if not paper.get("date_source"):
                return True
        return False

    def needs_abstract_enrichment(self, paper: Dict) -> bool:
        """判断论文是否需要摘要补全"""
        status = paper.get("abstract_status", "")
        if status == "unreliable_google_scholar_snippet":
            return True
        # 摘要字段为空
        if not (paper.get("abstract") or "").strip():
            return True
        return False

    # ── 核心补全逻辑 ──

    def enrich_date(self, paper: Dict) -> bool:
        """尝试从多个来源补全日期，返回是否成功"""
        for fetcher in DATE_FETCHERS:
            try:
                result = fetcher(paper)
            except Exception as exc:
                safe_print(f"  [warn] {fetcher.__name__} 失败: {exc}")
                result = None
            if self.delay:
                time.sleep(self.delay)
            if not result:
                continue
            new_date, metadata = result
            # 校验：不允许未来日期
            if new_date > TODAY:
                continue
            old_date = paper.get("published", "")
            paper["published"] = new_date
            # 日期可靠性判定
            source = metadata.get("date_source", "")
            if source in ("arxiv", "crossref_doi"):
                paper["date_status"] = "reliable"
            else:
                paper["date_status"] = "approximate"
            # 合并额外元数据
            for key, value in metadata.items():
                if value and key != "date_source":
                    if not paper.get(key):  # 不覆盖已有值
                        paper[key] = value
            paper["date_source"] = source
            paper["date_enriched_at"] = datetime.now(timezone.utc).isoformat()
            safe_print(f"  日期: {old_date} → {new_date} ({source})")
            return True
        return False

    def enrich_abstract(self, paper: Dict) -> bool:
        """尝试从多个来源补全摘要，返回是否成功"""
        for fetcher in ABSTRACT_FETCHERS:
            try:
                result = fetcher(paper)
            except Exception as exc:
                safe_print(f"  [warn] {fetcher.__name__} 失败: {exc}")
                result = None
            if self.delay:
                time.sleep(self.delay)
            if not result:
                continue
            abstract, metadata = result
            paper["abstract"] = abstract
            paper["abstract_status"] = "enriched"
            paper["abstract_enriched_at"] = datetime.now(timezone.utc).isoformat()
            # 合并额外元数据
            for key, value in metadata.items():
                if value and not paper.get(key):
                    paper[key] = value
            source = metadata.get("abstract_source", "unknown")
            safe_print(f"  摘要: ← {source} ({len(abstract)} 字符)")
            return True
        return False

    def enrich_paper(self, paper: Dict, only: str = "") -> bool:
        """对单篇论文执行补全。only 空字符串=全部, dates=仅日期, abstracts=仅摘要"""
        changed = False

        if only in ("", "dates") and self.needs_date_enrichment(paper):
            self.stats["date_attempted"] += 1
            if self.enrich_date(paper):
                self.stats["date_enriched"] += 1
                changed = True

        if only in ("", "abstracts") and self.needs_abstract_enrichment(paper):
            self.stats["abstract_attempted"] += 1
            if self.enrich_abstract(paper):
                self.stats["abstract_enriched"] += 1
                changed = True

        return changed

    # ── 批量执行 ──

    def run(self, months=None, dry_run=False, only="", limit=0):
        """批量处理月度数据文件"""
        for path in self._iter_files(months):
            papers = json.loads(path.read_text(encoding="utf-8"))
            changed = False
            for paper in papers:
                if limit and (self.stats["date_attempted"] + self.stats["abstract_attempted"]) >= limit:
                    break
                pid = paper.get("id", "")[:20]
                title = paper.get("title", "")[:60]
                if self.needs_date_enrichment(paper) or self.needs_abstract_enrichment(paper):
                    safe_print(f"\n[{pid}] {title}")
                    if self.enrich_paper(paper, only=only):
                        changed = True
            if changed and not dry_run:
                path.write_text(json.dumps(papers, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                safe_print(f"  已保存到 {path.name}")
            if limit and (self.stats["date_attempted"] + self.stats["abstract_attempted"]) >= limit:
                break

        safe_print(f"\n统计: {json.dumps(self.stats, ensure_ascii=False)}")
        if dry_run:
            safe_print("(dry-run 模式，未写入文件)")

    def _iter_files(self, months=None) -> Iterable[Path]:
        if months:
            for m in months:
                p = self.data_dir / f"{m}.json"
                if p.exists():
                    yield p
        else:
            yield from sorted(self.data_dir.glob("????-??.json"))


# ═══════════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--month", action="append", default=[], help="指定月份，如 2026-01")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入文件")
    parser.add_argument("--only", choices=["dates", "abstracts"], default="",
                        help="只补全日期或摘要")
    parser.add_argument("--delay", type=float, default=0.8, help="API 请求间隔（秒）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 篇（0=全部）")
    args = parser.parse_args()

    enricher = MetadataEnricher(data_dir=Path(args.data_dir), delay=args.delay)
    enricher.run(months=args.month, dry_run=args.dry_run,
                 only=args.only, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
