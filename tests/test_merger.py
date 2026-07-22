"""merger.py 关键用例测试 — DOI/ArXiv/标题合并、来源优先级"""


from daily_paper.merge import (
    identity_keys,
    merge_paper_list,
    merge_two_papers,
    source_rank,
    wos_preprint_replacement_reason,
)


def _paper(title="Test", doi="", arxiv_id="", source="arxiv", **extra):
    """生成一条最小论文记录"""
    p = {"id": "test-001", "title": title, "published": "2026-01-01", "source": source}
    if doi:
        p["doi"] = doi
    if arxiv_id:
        p["arxiv_id"] = arxiv_id
    p.update(extra)
    return p


class TestIdentityKeys:
    """identity_keys 关键用例"""

    def test_doi_key(self):
        keys = identity_keys(_paper(doi="10.1234/test"))
        assert any(k.startswith("doi:") for k in keys)

    def test_arxiv_key(self):
        keys = identity_keys(_paper(arxiv_id="2601.12345"))
        assert any(k.startswith("arxiv:") for k in keys)

    def test_title_key(self):
        keys = identity_keys(_paper(title="A Study of Fluid Dynamics"))
        assert any(k.startswith("title:") for k in keys)

    def test_empty_paper(self):
        keys = identity_keys({"title": ""})
        # 应该不会崩溃
        assert isinstance(keys, list)


class TestSourceRank:
    """source_rank 来源优先级"""

    def test_semantic_scholar_higher_than_arxiv(self):
        ss = source_rank(_paper(source="semantic_scholar"))
        arxiv = source_rank(_paper(source="arxiv"))
        assert ss > arxiv

    def test_crossref_higher_than_arxiv(self):
        cr = source_rank(_paper(source="crossref"))
        arxiv = source_rank(_paper(source="arxiv"))
        assert cr > arxiv


class TestMergeTwoPapers:
    """merge_two_papers 合并逻辑"""

    def test_keeps_richer_metadata(self):
        a = _paper(title="Paper A", doi="10.1234/a", abstract="")
        b = _paper(title="Paper A", doi="10.1234/a", abstract="A detailed abstract " * 20)
        merged = merge_two_papers(a, b)
        assert merged["abstract"]  # 应保留非空摘要

    def test_prefers_higher_source_rank(self):
        a = _paper(title="Paper", source="semantic_scholar", doi="10.1/a")
        b = _paper(title="Paper", source="arxiv", doi="10.1/a", arxiv_id="2601.1")
        merged = merge_two_papers(a, b)
        # SS 来源排名更高，其字段应被优先保留
        assert merged["source"] == "semantic_scholar"

    def test_wos_formal_replaces_arxiv_preprint_and_preserves_preprint_links(self):
        preprint = _paper(
            title="Neural operators for turbulent flow prediction",
            arxiv_id="2501.12345",
            source="arxiv",
            published="2025-01-10",
            authors="Ada Lovelace; Grace Hopper",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            preprint_pdf_url="https://arxiv.org/pdf/2501.12345",
            publication_type="preprint",
            is_preprint=True,
        )
        formal = _paper(
            title="Neural operators for turbulent-flow prediction",
            doi="10.1234/formal",
            source="webofscience",
            published="2026-02-15",
            authors="Lovelace, Ada; Hopper, Grace",
            venue="Computers & Fluids",
            paper_url="https://www.webofscience.com/wos/woscc/full-record/WOS:1",
            publication_types=["journal-article"],
        )

        merged = merge_two_papers(preprint, formal)

        assert merged["source"] == "webofscience"
        assert merged["doi"] == "10.1234/formal"
        assert merged["published"] == "2026-02-15"
        assert merged["publication_type"] == "journal"
        assert merged["is_preprint"] is False
        assert merged["arxiv_id"] == "2501.12345"
        assert merged["preprint_pdf_url"] == "https://arxiv.org/pdf/2501.12345"
        assert merged["version_status"] == "wos_formal_replaces_arxiv_preprint"
        assert merged["replacement_match"] == "high_similarity_title_and_author"


class TestMergePaperList:
    """merge_paper_list 去重合并"""

    def test_doi_dedup(self):
        """两条 DOI 相同的论文合并为一条"""
        papers = [
            _paper(title="Paper A", doi="10.1234/same", source="crossref"),
            _paper(title="Paper A Alt", doi="10.1234/same", source="semantic_scholar"),
        ]
        result = merge_paper_list(papers)
        assert len(result) == 1

    def test_arxiv_dedup(self):
        """两条 ArXiv ID 相同的论文合并为一条"""
        papers = [
            _paper(title="Paper X", arxiv_id="2601.99999", source="arxiv"),
            _paper(title="Paper X v2", arxiv_id="2601.99999", source="arxiv"),
        ]
        result = merge_paper_list(papers)
        assert len(result) == 1

    def test_title_similarity_dedup(self):
        """标题相似度 >= 0.85 的论文合并为一条"""
        papers = [
            _paper(title="Deep learning for turbulence modeling in CFD simulations"),
            _paper(title="Deep Learning for Turbulence Modeling in CFD Simulations"),
        ]
        result = merge_paper_list(papers)
        assert len(result) == 1

    def test_different_papers_kept(self):
        """完全不同的论文不应被合并"""
        papers = [
            _paper(title="A Study of Heat Transfer"),
            _paper(title="Machine Learning for Natural Language Processing"),
        ]
        result = merge_paper_list(papers)
        assert len(result) == 2

    def test_same_title_with_disjoint_known_authors_is_not_merged(self):
        papers = [
            _paper(title="Data-driven CFD", source="arxiv", authors="Alice Example"),
            _paper(title="Data-driven CFD", source="webofscience", authors="Bob Different", doi="10.1234/other"),
        ]
        assert len(merge_paper_list(papers)) == 2

    def test_wos_title_only_match_requires_author_overlap(self):
        preprint = _paper(
            title="Physics-informed neural networks for fluid dynamics",
            source="arxiv",
            arxiv_id="2501.12345",
            authors="Alice Example",
            publication_type="preprint",
        )
        formal = _paper(
            title="Physics informed neural networks for fluid dynamics",
            source="webofscience",
            doi="10.1234/formal",
            authors="Bob Different",
            venue="Physics of Fluids",
        )
        assert wos_preprint_replacement_reason(preprint, formal) == ""
        assert len(merge_paper_list([preprint, formal])) == 2

    def test_wos_title_only_match_accepts_reversed_first_author_name(self):
        preprint = _paper(
            title="Neural operators for turbulent flow prediction",
            source="arxiv",
            arxiv_id="2501.12345",
            authors="Jian-Nan Chen; Xiao-Yan Cao",
            publication_type="preprint",
        )
        formal = _paper(
            title="Neural operators for turbulent-flow prediction",
            source="webofscience",
            doi="10.1234/formal",
            authors="Chen, Jian-Nan; Cao, Xiao-Yan",
            venue="Computers & Fluids",
        )
        assert wos_preprint_replacement_reason(preprint, formal) == "high_similarity_title_and_author"

    def test_wos_title_only_match_rejects_same_surname_with_different_initial(self):
        preprint = _paper(
            title="Neural operators for turbulent flow prediction",
            source="arxiv",
            arxiv_id="2501.12345",
            authors="Wei Wang",
            publication_type="preprint",
        )
        formal = _paper(
            title="Neural operators for turbulent-flow prediction",
            source="webofscience",
            doi="10.1234/formal",
            authors="Wang, Li",
            venue="Computers & Fluids",
        )
        assert wos_preprint_replacement_reason(preprint, formal) == ""
