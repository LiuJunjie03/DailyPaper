"""PDF 全文补全模块 — 通过浏览器抓取出版商网页，尝试提取可下载的 PDF 链接。

依赖学校图书馆网络 / VPN 访问付费全文页面。
使用 Chrome DevTools Protocol 自动化（复用项目已有的浏览器框架）。
"""

import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from daily_paper.sources.browser import evaluate_in_chrome

logger = logging.getLogger(__name__)

# ── 非正文 PDF 关键词过滤 ──────────────────────────────────
_SKIP_PDF_KEYWORDS = (
    "supplement", "appendix", "cover", "toc", "table of contents",
    "license", "rights", "citation", "references", "editorial",
    "correction", "front matter", "back matter", "index",
)


def _is_body_pdf(url: str) -> bool:
    """判断 PDF 链接是否指向正文全文（而非附录/封面/目录等）"""
    lower_url = url.lower()
    # 按单词边界匹配，避免子串误伤（如 toc 误伤 stochastic）
    for kw in _SKIP_PDF_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lower_url):
            return False
    return True


def _has_pdf(paper: Dict, skip_if_any_pdf: bool) -> bool:
    """检查论文是否已有 PDF（受配置驱动）

    Args:
        paper: 论文字典
        skip_if_any_pdf: True=已有任一 PDF 跳过；False=只跳过正式 pdf_url

    Returns:
        True 表示已有 PDF，应跳过
    """
    if paper.get("pdf_url"):
        logger.debug("跳过 PDF 补全: 已有 pdf_url (%s)", paper["pdf_url"][:60])
        return True
    if skip_if_any_pdf and paper.get("preprint_pdf_url"):
        logger.debug("跳过 PDF 补全: skip_if_any_pdf=True 且已有 preprint_pdf_url")
        return True
    return False


def _target_url(paper: Dict) -> Optional[str]:
    """获取要访问的目标 URL（优先 paper_url，其次从 DOI 拼）"""
    url = (paper.get("paper_url") or "").strip()
    if url:
        return url
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    return None


def _browser_fetch_pdf(paper: Dict, config: Dict, pdf_config: Dict) -> bool:
    """通过浏览器访问论文页面，尝试提取 PDF 链接

    Args:
        paper: 论文字典（原地修改）
        config: 全局配置
        pdf_config: pdf_enrich 配置段

    Returns:
        True 当找到并写入新 PDF，否则 False
    """
    url = _target_url(paper)
    if not url:
        logger.info("  → 跳过 PDF 补全: 无 paper_url 和 doi")
        return False

    # — JS 脚本：等待页面加载 → 提取 PDF 链接 —
    script = """
async () => {
  // 等待动态内容加载
  await new Promise(r => setTimeout(r, 1500));

  // 收集所有可能的 PDF 链接
  const links = [];

  // 1. meta 标签（citation_pdf_url 最权威）
  for (const name of ['citation_pdf_url', 'dc.identifier', 'citation_fulltext_url']) {
    const meta = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
    if (meta && meta.content) {
      const href = meta.content.trim();
      if (href.toLowerCase().includes('.pdf') || href.includes('/pdf/')) {
        links.push({ href, type: 'meta' });
      }
    }
  }

  // 2. 所有 <a> 标签
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.getAttribute('href') || '';
    const text = (a.textContent || '').trim().toLowerCase();
    // 含 .pdf 或 /pdf/ 的链接
    if (href.toLowerCase().includes('.pdf') || href.includes('/pdf/')) {
      links.push({ href, type: 'link', text: text.slice(0, 80) });
    }
  });

  // 3. 归一化 + 过滤
  const results = links.map(l => ({
    href: new URL(l.href, location.href).href,
    type: l.type,
    text: l.text || '',
  }));

  return { url, resultCount: results.length, results };
}
"""

    try:
        logger.info("  → PDF 补全浏览器访问: %s", url[:80])
        data = evaluate_in_chrome(url, script, "PDF Enricher", config, pdf_config)
    except Exception as e:
        logger.warning("  → PDF 补全浏览器异常: %s (%s)", url[:60], e)
        return False

    if data is None:
        logger.info("  → PDF 补全: evaluate_in_chrome 返回 None（Chrome 未运行？），跳过")
        return False

    results = data.get("results", [])
    if not results:
        logger.info("  → PDF 补全: 页面未找到 PDF 链接 (%s)", url[:60])
        return False

    # 按优先级选第一个非正文 PDF 链接
    for item in results:
        href = item.get("href", "")
        if not href:
            continue
        if not _is_body_pdf(href):
            logger.debug("  → 过滤非正文 PDF: %s", href[:80])
            continue

        # 判断是 arXiv 预印本还是正式 PDF
        if "arxiv.org/pdf/" in href.lower() or "arxiv.org/abs/" in href.lower():
            # 归一化：去除 query/fragment，确保 .pdf 后缀
            parsed = urlparse(href)
            path = re.sub(r"/abs/", "/pdf/", parsed.path)
            if not path.endswith(".pdf"):
                path += ".pdf"
            normalized = urlunparse(parsed._replace(path=path, query="", fragment=""))
            paper["preprint_pdf_url"] = normalized
            paper["pdf_url"] = paper.get("pdf_url") or ""
            paper["pdf_source"] = "browser_enrich"
            logger.info("  → PDF 补全: 找到 arXiv 预印本 → %s", normalized[:80])
        elif href.lower().endswith(".pdf") or "/pdf/" in href.lower() or "download" in href.lower():
            paper["pdf_url"] = href
            paper["pdf_source"] = "browser_enrich"
            logger.info("  → PDF 补全: 找到正式 PDF → %s", href[:80])
        else:
            # 可能是需要登录的链接，但仍是可用链接
            paper["pdf_url"] = href
            paper["pdf_source"] = "browser_enrich"
            logger.info("  → PDF 补全: 找到 PDF 链接（可能需认证）→ %s", href[:80])
        return True  # 只取第一个有效 PDF

    logger.debug("  → PDF 补全: 全部链接被过滤（无正文 PDF）(%s)", url[:60])
    return False


def enrich_pdfs(papers: List[Dict], config: Dict) -> None:
    """对论文列表进行 PDF 全文补全（机会性增强，失败即跳过）

    仅在 config.pdf_enrich.enabled: true 时执行。
    遍历无 PDF 的论文，通过浏览器访问其出版页面尝试提取 PDF 链接。

    Args:
        papers: 论文列表（原地修改）
        config: 全局配置
    """
    pdf_config = config.get("pdf_enrich", {})
    if not pdf_config.get("enabled", False):
        logger.info("PDF 补全未启用 (pdf_enrich.enabled=false)")
        return

    max_papers = int(pdf_config.get("max_papers", 20))
    delay = float(pdf_config.get("delay_seconds", 1.5))
    skip_if_any = bool(pdf_config.get("skip_if_any_pdf", True))

    candidates = []
    for p in papers:
        if not _has_pdf(p, skip_if_any) and _target_url(p):
            candidates.append(p)

    if not candidates:
        logger.info("PDF 补全: 所有论文已有 PDF 或无可访问 URL")
        return

    total = min(len(candidates), max_papers)
    logger.info("PDF 补全: 共 %d 篇待补全，本次处理 %d 篇", len(candidates), total)

    success = 0
    for i, paper in enumerate(candidates[:total]):
        if _browser_fetch_pdf(paper, config, pdf_config):
            success += 1
        if i < total - 1:
            time.sleep(delay)
        if (i + 1) % 10 == 0:
            logger.info("PDF 补全进度: %d/%d", i + 1, total)

    logger.info("PDF 补全完成: 成功 %d/%d 篇", success, total)
