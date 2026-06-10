"""
论文数据的文件 I/O 操作。

从 PaperFetcher.save_papers() 中提取的纯 I/O 函数：
- load_monthly_data: 加载所有 YYYY-MM.json 文件
- split_papers_by_month: 按发表月份拆分论文
- save_monthly_data: 写入月度 JSON 文件
- build_month_index: 生成月份索引文件 index.json
"""

import json
import logging
import os
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


def load_monthly_data(data_dir: str) -> Dict[str, List[Dict]]:
    """加载目录下所有 YYYY-MM.json 文件，返回 {月份: [论文列表]}

    Args:
        data_dir: 数据目录路径（如 data/）

    Returns:
        按月份分组的论文字典
    """
    month_data: Dict[str, List[Dict]] = {}
    for filename in os.listdir(data_dir):
        if not re.fullmatch(r"\d{4}-\d{2}\.json", filename):
            continue
        month = filename.replace(".json", "")
        path = os.path.join(data_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                month_data[month] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read monthly data: {path}, {e}")
    return month_data


def split_papers_by_month(papers: List[Dict]) -> Dict[str, List[Dict]]:
    """按论文的 published 字段拆分到月份桶中

    Args:
        papers: 论文列表

    Returns:
        {月份字符串: [论文列表]} 字典，月份格式为 YYYY-MM
    """
    month_papers: Dict[str, List[Dict]] = {}
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
    return month_papers


def save_monthly_data(month_papers: Dict[str, List[Dict]], data_dir: str, docs_dir: str) -> None:
    """写入月度 JSON 文件到 data_dir 和 docs_dir

    Args:
        month_papers: {月份: [论文列表]} 字典
        data_dir: 数据目录路径（如 data/）
        docs_dir: 文档目录路径（如 docs/），可为空字符串跳过
    """
    os.makedirs(data_dir, exist_ok=True)
    for month, papers in month_papers.items():
        month_path = os.path.join(data_dir, f"{month}.json")
        with open(month_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info(f"月份数据已保存到：{month_path}")

    # 同步到 docs 目录
    if docs_dir:
        docs_data_dir = os.path.join(docs_dir, "data")
        os.makedirs(docs_data_dir, exist_ok=True)
        for month, papers in month_papers.items():
            month_path = os.path.join(docs_data_dir, f"{month}.json")
            with open(month_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)


def build_month_index(data_dir: str) -> None:
    """生成月份索引文件 data_dir/index.json

    读取目录下所有 YYYY-MM.json 文件，统计每月份论文数并写入索引。

    Args:
        data_dir: 数据目录路径（如 data/）
    """
    month_papers = load_monthly_data(data_dir)
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
    index_path = os.path.join(data_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    logger.info(f"月份索引已保存到：{index_path}")
