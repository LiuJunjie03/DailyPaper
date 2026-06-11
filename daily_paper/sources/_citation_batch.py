"""批量引用计数查询 — 通过 Semantic Scholar /paper/batch 接口批量获取 ArXiv 论文引用数。

被 arxiv_fetcher 和 semantic_scholar 共用，避免代码重复。
"""

import logging
import re
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def batch_get_citation_counts(
    papers: List[Dict],
    ss_api_key: str = "",
    batch_size: int = 20,
) -> Dict[str, Optional[int]]:
    """批量获取引用数：使用 Semantic Scholar /paper/batch 接口，
    通过 ArXiv ID 批量查询，避免逐篇请求导致速率限制。
    返回 {paper['id']: citation_count} 字典。
    """
    result_map: Dict[str, Optional[int]] = {}

    # 收集有 ArXiv ID 的论文
    id_pairs: list = []  # [(paper_id, arxiv_id), ...]
    for p in papers:
        aid = p.get("arxiv_id", "") or ""
        # 兼容：部分论文的 id 字段本身就是 arxiv_id
        if not aid and re.match(r"^\d{4}\.\d{4,5}", str(p.get("id", ""))):
            aid = p.get("id", "")
        if aid:
            normalized = re.sub(r"v\d+$", "", aid)
            id_pairs.append((p["id"], normalized))

    if not id_pairs:
        return result_map

    headers = {}
    if ss_api_key:
        headers["x-api-key"] = ss_api_key

    total_batches = (len(id_pairs) + batch_size - 1) // batch_size
    consecutive_failures = 0
    max_consecutive_failures = 3

    logger.info("等待 API 冷却...")
    time.sleep(3)

    for i in range(0, len(id_pairs), batch_size):
        batch = id_pairs[i : i + batch_size]
        ss_ids = [f"ArXiv:{arxiv_id}" for _, arxiv_id in batch]
        batch_num = i // batch_size + 1

        url = "https://api.semanticscholar.org/graph/v1/paper/batch"
        params = {"fields": "title,citationCount"}

        try:
            resp = requests.post(
                url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30
            )

            retry_count = 0
            while resp.status_code == 429 and retry_count < 2:
                retry_count += 1
                wait = 30 * retry_count
                logger.warning(
                    f"批量 API 限速 (批次 {batch_num}/{total_batches})，等待 {wait} 秒后重试..."
                )
                time.sleep(wait)
                resp = requests.post(
                    url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30
                )

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
                logger.info(
                    f"批量引用: 批次 {batch_num}/{total_batches} 完成 "
                    f"({matched}/{len(batch)} 篇命中)"
                )
            else:
                consecutive_failures += 1
                logger.warning(
                    f"批量 API 返回 {resp.status_code} (批次 {batch_num}/{total_batches})"
                )
                for paper_id, _ in batch:
                    result_map[paper_id] = None

                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询"
                    )
                    for paper_id, _ in id_pairs[i + batch_size :]:
                        result_map[paper_id] = None
                    break

        except Exception as e:
            consecutive_failures += 1
            logger.warning(f"批量 API 请求失败: {e}")
            for paper_id, _ in batch:
                result_map[paper_id] = None

            if consecutive_failures >= max_consecutive_failures:
                logger.warning(
                    f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询"
                )
                for paper_id, _ in id_pairs[i + batch_size :]:
                    result_map[paper_id] = None
                break

        if i + batch_size < len(id_pairs):
            time.sleep(3)

    success_count = sum(1 for v in result_map.values() if v is not None)
    logger.info(
        f"批量引用查询完成: {len(result_map)} 篇，"
        f"其中 {success_count} 篇有引用数据 "
        f"({success_count * 100 // max(len(result_map), 1)}%)"
    )
    return result_map
