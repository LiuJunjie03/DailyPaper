"""enrich.py 关键用例测试 — 补全逻辑、摘要判断、OpenAlex 重建"""


from daily_paper.enrich import (
    _is_reliable_abstract,
    _cascade_normalize_title,
    _cascade_title_matches,
    _cascade_openalex_abstract,
    _metadata_complete,
    _needs_crossref_enrichment,
)


class TestIsReliableAbstract:
    """_is_reliable_abstract 关键用例"""

    def test_short_abstract_unreliable(self):
        """< 220 字符摘要 → 不可靠"""
        assert not _is_reliable_abstract("A" * 100)

    def test_valid_abstract_reliable(self):
        """正常摘要 → 可靠"""
        text = (
            "This paper presents a novel approach to turbulence modeling "
            "using deep neural networks. We demonstrate significant improvements "
            "in prediction accuracy across multiple benchmark datasets. "
            "Our method achieves state-of-the-art performance."
        )
        assert _is_reliable_abstract(text)

    def test_cookie_banner_unreliable(self):
        """cookie 横幅 → 不可靠"""
        text = (
            "Cookies help us deliver our services. By using our site, "
            "you acknowledge that you have read and understand our policy. "
            "This site uses cookies for analytics."
        )
        assert not _is_reliable_abstract(text)

    def test_lowercase_start_unreliable(self):
        """小写开头 → 不可靠"""
        text = "a" * 250 + "."
        assert not _is_reliable_abstract(text)


class TestNormalizeTitle:
    """_cascade_normalize_title"""

    def test_lowercases(self):
        assert "deep" in _cascade_normalize_title("Deep Learning")

    def test_strips_punctuation(self):
        result = _cascade_normalize_title("A Study of (CFD) & ML")
        assert "(" not in result
        assert "&" not in result


class TestTitleMatches:
    """_cascade_title_matches"""

    def test_exact_match(self):
        assert _cascade_title_matches("Fluid Dynamics", "Fluid Dynamics")

    def test_case_insensitive(self):
        assert _cascade_title_matches("fluid dynamics", "FLUID DYNAMICS")

    def test_similar_titles(self):
        """相似度 >= 0.85 匹配"""
        assert _cascade_title_matches(
            "Deep learning for turbulence modeling",
            "Deep Learning for Turbulence Modeling",
        )

    def test_very_different_no_match(self):
        assert not _cascade_title_matches(
            "Fluid dynamics simulation",
            "Natural language processing for chatbots",
        )


class TestOpenalexAbstract:
    """_cascade_openalex_abstract 倒排索引重建"""

    def test_reconstructs_text(self):
        inv = {"Hello": [0], "world": [1]}
        assert _cascade_openalex_abstract(inv) == "Hello world"

    def test_empty_index(self):
        assert _cascade_openalex_abstract(None) == ""
        assert _cascade_openalex_abstract({}) == ""


class TestMetadataComplete:
    """_metadata_complete 判断"""

    def test_complete_paper(self):
        paper = {
            "doi": "10.1234/test",
            "abstract": "A" * 300,
            "published": "2026-01-15",
            "venue": "Journal of Testing",
        }
        assert _metadata_complete(paper)

    def test_incomplete_paper(self):
        paper = {"doi": "10.1234/test"}
        assert not _metadata_complete(paper)


class TestNeedsCrossrefEnrichment:
    """_needs_crossref_enrichment"""

    def test_arxiv_without_doi_skipped(self):
        """ArXiv 无 DOI → 不需要 Crossref 补全"""
        paper = {"source": "arxiv", "doi": "", "published": "", "venue": ""}
        assert not _needs_crossref_enrichment(paper)

    def test_complete_paper_skipped(self):
        """元数据完整 → 不需要补全"""
        paper = {
            "doi": "10.1/test",
            "abstract": "A" * 300,
            "published": "2026-01-15",
            "venue": "Test Journal",
        }
        assert not _needs_crossref_enrichment(paper)
