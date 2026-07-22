"""查询词解析工具"""

def flatten_queries(config_or_raw) -> list[str]:
    """将配置中的 queries 展开为字符串列表

    支持格式：
    - list: ["query1", "query2"]
    - dict: {"group1": ["q1", "q2"], "group2": "q3"}
    """
    # 调用方既可能传入整个源配置（含 ``queries``），也可能直接传入
    # 分组后的查询字典。只有前一种才应继续取 ``queries`` 键。
    raw_queries = (
        config_or_raw.get("queries", [])
        if isinstance(config_or_raw, dict) and "queries" in config_or_raw
        else config_or_raw
    )
    if isinstance(raw_queries, dict):
        queries = []
        for values in raw_queries.values():
            queries.extend(values if isinstance(values, list) else [values])
    else:
        queries = raw_queries or []
    return [str(q).strip() for q in queries if str(q).strip()]
