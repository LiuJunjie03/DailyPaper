"""merger.py 关键用例测试 — DOI/ArXiv/标题合并、来源优先级"""


from daily_paper.merge import identity_keys, source_rank, merge_two_papers, merge_paper_list


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
