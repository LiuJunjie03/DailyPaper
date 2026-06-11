"""文本归一化与清洗工具"""


import re
from html import unescape


def normalize_title(title: str) -> str:
    """折叠空白、转小写、去首尾空白"""
    return re.sub(r"\s+", " ", (title or "").lower().strip())


def normalize_doi(doi: str) -> str:
    """去除 DOI URL 前缀，转小写"""
    if not doi:
        return ""
    doi = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def normalize_arxiv_id(arxiv_id: str) -> str:
    """去除 ArXiv URL 前缀和版本后缀"""
    if not arxiv_id:
        return ""
    arxiv_id = str(arxiv_id).strip()
    # 取路径最后一段
    if "/" in arxiv_id:
        arxiv_id = arxiv_id.rsplit("/", 1)[-1]
    # 去版本号
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
    return arxiv_id


def term_in_text(text: str, term: str) -> bool:
    """在文本中搜索术语（带词边界，大小写不敏感）"""
    if not term or not text:
        return False
    pattern = r"\b" + re.escape(term) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def clean_text(text: str) -> str:
    """清理文本：移除 HTML 标签、折叠空白、解码 HTML 实体"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()
