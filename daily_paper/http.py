"""HTTP 请求工具：统一重试、超时、User-Agent"""

import os
import time
from typing import Dict, Optional

import requests

# 统一 User-Agent（Crossref/OpenAlex polite pool 可通过 CROSSREF_MAILTO 环境变量设置邮箱）
_MAILTO = os.environ.get("CROSSREF_MAILTO", "")
USER_AGENT = f"DailyPaperBot/1.0 (mailto:{_MAILTO})" if _MAILTO else "DailyPaperBot/1.0"


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
