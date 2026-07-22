"""Chinese intelligent-CFD collection, discovery tracking and reporting."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from daily_paper.classify import is_intelligent_cfd_paper
from daily_paper.merge import identity_keys, merge_two_papers
from daily_paper.normalizer import finalize_paper
from daily_paper.storage import build_month_index, load_monthly_data, save_monthly_data, split_papers_by_month

SHANGHAI = ZoneInfo("Asia/Shanghai")


def discovery_now() -> tuple[str, str]:
    now = datetime.now(SHANGHAI)
    return now.date().isoformat(), now.isoformat(timespec="seconds")


def relevance_score(paper: dict) -> int:
    """Transparent 0-100 score; classification remains the admission gate."""
    score = 45
    details = paper.get("classification_score") or {}
    if details:
        score += min(25, max(int(item.get("score", 0)) for item in details.values()) * 3)
    if paper.get("abstract"):
        score += 8
    if paper.get("official_keywords") or paper.get("keywords"):
        score += 5
    if paper.get("doi"):
        score += 4
    if paper.get("pdf_url") or paper.get("access_url"):
        score += 3
    score += min(10, int(paper.get("journal_priority", 0)) * 2)
    return max(0, min(100, score))


def _key_set(papers: Iterable[dict]) -> set[str]:
    return {key for paper in papers for key in identity_keys(paper)}


def prepare_candidates(candidates: list[dict], existing: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    day, timestamp = discovery_now()
    existing_keys = _key_set(existing)
    prepared = []
    new_papers = []
    for raw in candidates:
        paper = finalize_paper(raw, config)
        if not is_intelligent_cfd_paper(paper):
            continue
        is_new = not any(key in existing_keys for key in identity_keys(paper))
        if is_new:
            paper["first_seen"] = day
            paper["first_seen_at"] = timestamp
        else:
            # Empty values do not overwrite historical discovery metadata during merge.
            paper["first_seen"] = ""
            paper["first_seen_at"] = ""
        paper["last_seen_at"] = timestamp
        paper["relevance_score"] = relevance_score(paper)
        paper["zotero_lookup_url"] = (
            f"https://doi.org/{paper['doi']}" if paper.get("doi") else paper.get("paper_url", "")
        )
        prepared.append(paper)
        if is_new:
            new_papers.append(paper)
            existing_keys.update(identity_keys(paper))
    return prepared, new_papers


def merge_and_save(existing: list[dict], candidates: list[dict], data_dir: Path) -> list[dict]:
    """Update only touched records/months; never re-deduplicate the historical archive."""
    month_papers = load_monthly_data(str(data_dir))
    key_locations = {}
    for month, papers in month_papers.items():
        for index, paper in enumerate(papers):
            for key in identity_keys(paper):
                key_locations.setdefault(key, (month, index))

    touched_months = set()
    for candidate in candidates:
        location = next((key_locations[key] for key in identity_keys(candidate) if key in key_locations), None)
        if location:
            month, index = location
            month_papers[month][index] = merge_two_papers(month_papers[month][index], candidate)
            touched_months.add(month)
            continue
        buckets = split_papers_by_month([candidate])
        month, papers = next(iter(buckets.items()))
        target = month_papers.setdefault(month, [])
        index = len(target)
        target.extend(papers)
        touched_months.add(month)
        for key in identity_keys(candidate):
            key_locations[key] = (month, index)

    if touched_months:
        save_monthly_data(month_papers, str(data_dir), docs_dir="", only_months=touched_months)
    build_month_index(str(data_dir))
    return [paper for papers in month_papers.values() for paper in papers]


def render_daily_report(
    new_papers: list[dict],
    all_candidates: list[dict],
    source_counts: dict[str, int],
    output_path: Path,
) -> None:
    day, timestamp = discovery_now()
    ranked = sorted(new_papers, key=lambda item: (-int(item.get("relevance_score", 0)), item.get("title", "")))
    lines = [
        f"# 中文智能 CFD 文献日报：{day}",
        "",
        f"- 本次运行：{timestamp}",
        f"- 首次发现：{len(ranked)} 篇",
        f"- 本次有效候选：{len(all_candidates)} 篇",
        "- 日期口径：`first_seen` 是系统首次发现日期；`published` 是来源标注的出版/网络发表日期。",
        "- 全文策略：仓库只保存链接和元数据，不保存或公开机构权限 PDF。",
        "",
        "## 来源状态",
        "",
    ]
    for source, count in sorted(source_counts.items()):
        lines.append(f"- {source}: {count} 篇")
    lines.extend(["", "## 今日首次发现", ""])
    if not ranked:
        lines.append("本次没有首次发现的相关论文。期刊非每日出版，这是正常状态。")
    for index, paper in enumerate(ranked, 1):
        title = paper.get("title", "未命名")
        page_url = paper.get("paper_url") or paper.get("zotero_lookup_url") or ""
        title_md = f"[{title}]({page_url})" if page_url else title
        fulltext = paper.get("access_url") or paper.get("pdf_url") or page_url
        zotero = paper.get("zotero_lookup_url") or page_url
        lines.extend([
            f"### {index}. {title_md}",
            "",
            f"- 作者：{paper.get('authors') or '待补全'}",
            f"- 期刊：{paper.get('venue') or '待补全'}",
            f"- 来源发表日期：{paper.get('published') or 'unknown'}",
            f"- 首次发现日期：{paper.get('first_seen') or day}",
            f"- 相关性评分：{paper.get('relevance_score', 0)}/100",
            f"- DOI：{paper.get('doi') or '无'}",
            f"- 关键词：{'、'.join(paper.get('keywords') or []) or '待补全'}",
            f"- 全文入口：{f'[打开]({fulltext})' if fulltext else '需在机构数据库中人工检索'}",
            f"- Zotero 识别入口：{f'[打开]({zotero})' if zotero else '无'}",
            f"- 摘要：{paper.get('abstract') or '待补全'}",
            "",
        ])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_run_json(
    new_papers: list[dict], all_candidates: list[dict], source_counts: dict[str, int], output_path: Path
) -> None:
    day, timestamp = discovery_now()
    payload = {
        "run_date": day,
        "run_at": timestamp,
        "new_count": len(new_papers),
        "candidate_count": len(all_candidates),
        "source_counts": source_counts,
        "new_ids": [paper.get("id") for paper in new_papers],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_existing(data_dir: Path) -> list[dict]:
    data_dir.mkdir(parents=True, exist_ok=True)
    return [paper for papers in load_monthly_data(str(data_dir)).values() for paper in papers]
