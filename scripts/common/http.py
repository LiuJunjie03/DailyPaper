"""HTTP 请求工具：统一重试、超时、User-Agent"""

import time
from typing import Dict, Optional

import requests

# 统一 User-Agent（Crossref 和 OpenAlex 要求mailto，其他来源不限）
USER_AGENT = "DailyPaperBot/1.0 (mailto:research@dailyPaper.org)"


def request_json(url: str, params: Optional[Dict] = None, timeout: int = 20) -> Optional[Dict]:
    """通用 JSON GET 请求，429 自动重试（最多 3 次）"""
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": USER_AGENT})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(2)
    return None
