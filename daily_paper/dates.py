"""日期解析与校验工具"""

import re


def validate_date(value: str) -> str:
    """检查字符串是否为完整的 YYYY-MM-DD 格式，不是则返回空字符串"""
    value = str(value or "")
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""


def parse_date(value: str) -> str:
    """将宽松日期格式（含中文、斜杠、点号）解析为 YYYY-MM-DD"""
    from daily_paper.text import clean_text
    value = clean_text(value)
    # 完整日期：2024年3月15日 / 2024/3/15 / 2024.3.15
    match = re.search(r"((?:19|20)\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", value)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3) or 1)
        return f"{year:04d}-{month:02d}-{day:02d}"
    # 仅年份
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else ""


def in_date_window(published: str, from_date: str, until_date: str) -> bool:
    """判断论文发表日期是否在指定窗口内，不完整日期默认通过"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published or ""):
        return True
    if from_date and published < from_date:
        return False
    if until_date and published > until_date:
        return False
    return True
