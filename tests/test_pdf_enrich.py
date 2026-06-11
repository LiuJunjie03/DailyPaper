"""PDF 补全模块单元测试 — 纯逻辑测试，不启动浏览器"""

from unittest.mock import patch

from daily_paper.pdf_enrich import (
    _has_pdf,
    _target_url,
    _is_body_pdf,
    enrich_pdfs,
)


def _paper(**extra):
    """生成一条最小论文记录"""
    p = {"id": "test-001", "title": "Test Paper", "source": "test"}
    p.update(extra)
    return p


# ═══════════════════════════════════════════════════════════════
#  _has_pdf
# ═══════════════════════════════════════════════════════════════

def test_has_pdf_skips_when_pdf_url_exists():
    """已有 pdf_url → 跳过"""
    p = _paper(pdf_url="https://example.com/paper.pdf")
    assert _has_pdf(p, skip_if_any_pdf=True) is True


def test_has_pdf_skips_when_preprint_and_skip_any():
    """仅有 preprint_pdf_url + skip_if_any_pdf=True → 跳过"""
    p = _paper(preprint_pdf_url="https://arxiv.org/pdf/2601.00001")
    assert _has_pdf(p, skip_if_any_pdf=True) is True


def test_has_pdf_not_skips_when_only_preprint_and_skip_any_false():
    """仅有 preprint_pdf_url + skip_if_any_pdf=False → 不跳过"""
    p = _paper(preprint_pdf_url="https://arxiv.org/pdf/2601.00001")
    assert _has_pdf(p, skip_if_any_pdf=False) is False


def test_has_pdf_not_skips_when_no_pdf():
    """无 pdf_url 和 preprint_pdf_url → 不跳过"""
    p = _paper()
    assert _has_pdf(p, skip_if_any_pdf=True) is False


# ═══════════════════════════════════════════════════════════════
#  _target_url
# ═══════════════════════════════════════════════════════════════

def test_target_url_uses_paper_url_first():
    """paper_url 优先于 doi"""
    p = _paper(paper_url="https://example.com/article", doi="10.1234/test")
    assert _target_url(p) == "https://example.com/article"


def test_target_url_falls_back_to_doi():
    """无 paper_url 但有 doi → https://doi.org/{doi}"""
    p = _paper(doi="10.1234/test")
    assert _target_url(p) == "https://doi.org/10.1234/test"


def test_target_url_no_url_or_doi_returns_none():
    """无 paper_url 且无 doi → None"""
    p = _paper()
    assert _target_url(p) is None


# ═══════════════════════════════════════════════════════════════
#  _is_body_pdf
# ═══════════════════════════════════════════════════════════════

def test_is_body_pdf_accepts_stochastic():
    """stochastic 不应被 toc 等关键词误伤"""
    assert _is_body_pdf("https://example.com/stochastic-fluid-dynamics.pdf") is True


def test_is_body_pdf_accepts_discovery():
    """discovery 不应被 cover 等关键词误伤（子串误伤回归）"""
    assert _is_body_pdf("https://example.com/discovery-method.pdf") is True


def test_is_body_pdf_rejects_supplement():
    """supplement 应被过滤"""
    assert _is_body_pdf("https://example.com/paper-supplement.pdf") is False


def test_is_body_pdf_rejects_appendix():
    """appendix 应被过滤"""
    assert _is_body_pdf("https://example.com/appendix-a.pdf") is False


def test_is_body_pdf_rejects_toc():
    """目录 toc 应被过滤"""
    assert _is_body_pdf("https://example.com/toc.pdf") is False


def test_is_body_pdf_rejects_cover():
    """封面 cover 应被过滤"""
    assert _is_body_pdf("https://example.com/cover-page.pdf") is False


# ═══════════════════════════════════════════════════════════════
#  enrich_pdfs — mock 正式 PDF / arXiv PDF / 过滤链 / None
# ═══════════════════════════════════════════════════════════════

@patch("daily_paper.pdf_enrich.evaluate_in_chrome")
def test_finds_formal_pdf(mock_chrome):
    """找到正式 PDF → 写入 pdf_url + pdf_source"""
    mock_chrome.return_value = {
        "results": [{"href": "https://example.com/article.pdf", "type": "link"}]
    }
    p = _paper(paper_url="https://example.com/article")
    config = {"pdf_enrich": {"enabled": True, "max_papers": 10, "skip_if_any_pdf": True}}

    enrich_pdfs([p], config)

    assert p.get("pdf_url") == "https://example.com/article.pdf"
    assert p.get("pdf_source") == "browser_enrich"


@patch("daily_paper.pdf_enrich.evaluate_in_chrome")
def test_finds_arxiv_pdf(mock_chrome):
    """找到 arXiv PDF → 写入 preprint_pdf_url + pdf_source"""
    mock_chrome.return_value = {
        "results": [{"href": "https://arxiv.org/pdf/2601.00001", "type": "link"}]
    }
    p = _paper(paper_url="https://arxiv.org/abs/2601.00001")
    config = {"pdf_enrich": {"enabled": True, "max_papers": 10, "skip_if_any_pdf": True}}

    enrich_pdfs([p], config)

    assert p.get("preprint_pdf_url") == "https://arxiv.org/pdf/2601.00001.pdf"
    assert p.get("pdf_source") == "browser_enrich"


@patch("daily_paper.pdf_enrich.evaluate_in_chrome")
def test_skips_filtered_link_uses_next(mock_chrome):
    """非正文 PDF 被过滤后取下一个有效链接"""
    mock_chrome.return_value = {
        "results": [
            {"href": "https://example.com/supplement.pdf", "type": "link"},
            {"href": "https://example.com/paper.pdf", "type": "link"},
        ]
    }
    p = _paper(paper_url="https://example.com/article")
    config = {"pdf_enrich": {"enabled": True, "max_papers": 10, "skip_if_any_pdf": True}}

    enrich_pdfs([p], config)

    assert p.get("pdf_url") == "https://example.com/paper.pdf"
    assert p.get("pdf_source") == "browser_enrich"


@patch("daily_paper.pdf_enrich.evaluate_in_chrome")
def test_browser_none_does_not_count_success(mock_chrome):
    """evaluate_in_chrome 返回 None，已有 preprint，skip_if_any=False → 不计入成功"""
    mock_chrome.return_value = None

    p = _paper(
        paper_url="https://example.com/article",
        preprint_pdf_url="https://arxiv.org/pdf/2601.00001",
    )
    config = {"pdf_enrich": {"enabled": True, "max_papers": 10, "skip_if_any_pdf": False}}

    enrich_pdfs([p], config)

    # 不新增 pdf_url（浏览器 None）
    assert p.get("pdf_url") is None
    assert p.get("preprint_pdf_url") == "https://arxiv.org/pdf/2601.00001"
    assert p.get("pdf_source") is None
    mock_chrome.assert_called_once()


@patch("daily_paper.pdf_enrich.evaluate_in_chrome")
def test_script_contains_pdf_detection(mock_chrome):
    """注入 JS 脚本应包含关键检测片段"""
    mock_chrome.return_value = None

    p = _paper(paper_url="https://example.com/article")
    config = {"pdf_enrich": {"enabled": True, "max_papers": 10, "skip_if_any_pdf": True}}

    enrich_pdfs([p], config)

    # 捕获传给 evaluate_in_chrome 的 script 参数
    _args, _kwargs = mock_chrome.call_args
    script = _args[1] if len(_args) > 1 else ""

    assert "includes('.pdf')" in script, "meta PDF 检测应使用 includes('.pdf')"
    assert "new URL(l.href, location.href).href" in script, "相对 URL 归一化应使用 new URL"
    assert "location.href" in script, "相对 URL 应基于 location.href 解析"
