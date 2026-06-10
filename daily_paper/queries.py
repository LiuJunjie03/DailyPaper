"""查询词解析工具"""

from typing import List


def flatten_queries(config_or_raw) -> List[str]:
    """将配置中的 queries 展开为字符串列表

    支持格式：
    - list: ["query1", "query2"]
    - dict: {"group1": ["q1", "q2"], "group2": "q3"}
    """
    raw_queries = config_or_raw.get("queries", []) if isinstance(config_or_raw, dict) else config_or_raw
    if isinstance(raw_queries, dict):
        queries = []
        for values in raw_queries.values():
            queries.extend(values if isinstance(values, list) else [values])
    else:
        queries = raw_queries or []
    return [str(q).strip() for q in queries if str(q).strip()]
