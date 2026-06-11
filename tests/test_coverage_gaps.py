"""补充测试 — citation batch 重试/熔断、cascade 并发降级、merger 去重边界、classifier negative 排除"""

from unittest.mock import patch, MagicMock

from daily_paper.sources._citation_batch import batch_get_citation_counts
from daily_paper.merge import merge_paper_list
from daily_paper.classify import classify_paper


def _paper(title="Test", doi="", arxiv_id="", source="arxiv", **extra):
    """生成一条最小论文记录"""
    p = {"id": "test-001", "title": title, "published": "2026-01-01", "source": source}
    if doi:
        p["doi"] = doi
    if arxiv_id:
        p["arxiv_id"] = arxiv_id
    p.update(extra)
    return p


# ═══════════════════════════════════════════════════════════════
#  1. batch_get_citation_counts — HTTP 429 重试
# ═══════════════════════════════════════════════════════════════

class TestCitationBatch429Retry:
    """429 重试逻辑：首次 429，重试后 200"""

    @patch("daily_paper.sources._citation_batch.time.sleep")
    @patch("daily_paper.sources._citation_batch.requests.post")
    def test_retries_on_429_then_succeeds(self, mock_post, mock_sleep):
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = [{"citationCount": 42, "title": "test"}]

        mock_post.side_effect = [resp_429, resp_200]

        papers = [{"id": "2601.00001", "arxiv_id": "2601.00001"}]
        result = batch_get_citation_counts(papers, batch_size=20)

        assert result["2601.00001"] == 42
        assert mock_post.call_count == 2  # 初始 + 1 次重试
        # 验证退避等待（3s 初始冷却 + 30s 重试等待）
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 30 in sleep_calls  # 重试退避


# ═══════════════════════════════════════════════════════════════
#  2. batch_get_citation_counts — 熔断器
# ═══════════════════════════════════════════════════════════════

class TestCitationBatchCircuitBreaker:
    """连续 3 批次失败后跳过剩余论文"""

    @patch("daily_paper.sources._citation_batch.time.sleep")
    @patch("daily_paper.sources._citation_batch.requests.post")
    def test_circuit_breaker_after_3_failures(self, mock_post, mock_sleep):
        resp_500 = MagicMock()
        resp_500.status_code = 500
        mock_post.return_value = resp_500

        # 80 篇论文，batch_size=20 → 4 批。前 3 批失败后第 4 批应被跳过
        papers = [{"id": f"2601.{i:05d}", "arxiv_id": f"2601.{i:05d}"} for i in range(80)]
        result = batch_get_citation_counts(papers, batch_size=20)

        # 所有论文都应有结果（成功的或 None）
        assert len(result) == 80
        # 前 3 批 (60 篇) 经历了请求，第 4 批被熔断跳过
        assert mock_post.call_count == 3  # 只发了 3 次请求
        # 全部应该是 None（没有成功的引用数据）
        assert all(v is None for v in result.values())


# ═══════════════════════════════════════════════════════════════
#  3. cascade_enrich_papers — 并发降级到串行
# ═══════════════════════════════════════════════════════════════

class TestCascadeEnrichFallback:
    """全部补全 API 失败时，降级到串行重试且不崩溃"""

    @patch("daily_paper.enrich._enrich_from_publisher")
    @patch("daily_paper.enrich._enrich_from_semantic_scholar")
    @patch("daily_paper.enrich._enrich_from_openalex")
    @patch("daily_paper.enrich._enrich_from_crossref")
    def test_all_apis_fail_no_crash(self, mock_cr, mock_oa, mock_ss, mock_pub):
        # 所有补全函数都抛异常
        mock_cr.side_effect = RuntimeError("Crossref down")
        mock_oa.side_effect = RuntimeError("OpenAlex down")
        mock_ss.side_effect = RuntimeError("S2 down")
        mock_pub.side_effect = RuntimeError("Publisher down")

        from daily_paper.enrich import cascade_enrich_papers

        # 论文需要补全（无 abstract、无 doi）
        papers = [{
            "id": "test-001",
            "title": "Test Paper",
            "abstract": "",
            "doi": "",
            "source": "arxiv",
        }]
        config = {"sources": {}}

        # 不应抛异常
        cascade_enrich_papers(papers, config, max_workers=2)

        # 论文仍存在，未被删除
        assert len(papers) == 1
        # abstract 仍为空（补全全失败）
        assert papers[0]["abstract"] == ""


# ═══════════════════════════════════════════════════════════════
#  4. merge_paper_list — 去重边界情况
# ═══════════════════════════════════════════════════════════════

class TestMergeBoundaryCases:
    """去重边界：仅 ArXiv ID 不同 / 仅标题差异"""

    def test_same_doi_different_arxiv_id_merges(self):
        """DOI 相同但 ArXiv ID 不同 → 应合并"""
        a = _paper(title="Deep Learning for CFD", doi="10.1234/test", arxiv_id="2601.00001", source="arxiv")
        b = _paper(title="Deep Learning for CFD", doi="10.1234/test", arxiv_id="2601.00002", source="semantic_scholar")
        result = merge_paper_list([a, b])
        assert len(result) == 1, "DOI 相同应合并为一条"

    def test_same_arxiv_id_different_doi_merges(self):
        """ArXiv ID 相同但 DOI 不同 → 应合并"""
        a = _paper(title="Deep Learning for CFD", doi="", arxiv_id="2601.00001", source="arxiv")
        b = _paper(title="Deep Learning for CFD", doi="10.1234/test", arxiv_id="2601.00001", source="crossref")
        result = merge_paper_list([a, b])
        assert len(result) == 1, "ArXiv ID 相同应合并为一条"

    def test_similar_title_no_shared_id_kept_separate(self):
        """标题高度相似但无共同 ID → merge_paper_list 不做标题合并，保持独立"""
        a = _paper(title="Physics-informed neural networks for fluid dynamics", source="arxiv")
        b = _paper(title="Physics-informed neural networks for fluid dynamics simulation", source="crossref")
        result = merge_paper_list([a, b])
        # merge_paper_list 仅按 identity_keys (DOI/ArXiv ID) 去重，不做标题相似度匹配
        assert len(result) == 2, "无共同 ID 时标题相似也不会合并"

    def test_no_shared_identity_kept_separate(self):
        """无共同 DOI/ArXiv ID 且标题不相似 → 保持独立"""
        a = _paper(title="Machine learning for turbulence modeling", source="arxiv")
        b = _paper(title="Deep reinforcement learning for flow control", source="semantic_scholar")
        result = merge_paper_list([a, b])
        assert len(result) == 2, "完全不同的论文应保持独立"


# ═══════════════════════════════════════════════════════════════
#  5. classify_paper — negative 排除关键词
# ═══════════════════════════════════════════════════════════════

class TestClassifyNegativeTerms:
    """negative 排除关键词：命中 negative 词的论文分类分数应降低

    classify_paper 在 config.categories 为空时只填 classification_score 不返回 tags，
    所以这里通过检查 paper['classification_score'] 来验证。
    """

    def test_negative_terms_reduce_classification(self):
        """命中 negative 的论文，该子领域分数应被扣减到低于阈值"""
        config = {"categories": {}}
        # 包含 strong 关键词但也包含 negative 词
        paper = {
            "title": "Turbulence modeling with deep learning for CFD",
            "abstract": "This paper presents a turbulence modeling approach for CFD. "
                        "We also apply language model techniques for text analysis.",
        }
        classify_paper(paper, config)
        scores = paper.get("classification_score", {})
        key = "流体力学 / 智能CFD / 湍流建模与闭合"
        # negative "language model" 命中，扣 4 分；score 应低于 3（阈值）所以不会出现
        assert key not in scores or scores[key]["score"] < 3

    def test_no_negative_terms_keeps_classification(self):
        """不命中 negative 的论文，该子领域分数应足够高"""
        config = {"categories": {}}
        paper = {
            "title": "Turbulence modeling with deep learning for CFD",
            "abstract": "This paper presents a turbulence modeling approach for CFD simulation "
                        "using RANS closure with neural networks.",
        }
        classify_paper(paper, config)
        scores = paper.get("classification_score", {})
        key = "流体力学 / 智能CFD / 湍流建模与闭合"
        assert key in scores
        assert scores[key]["score"] >= 3
        assert scores[key]["negative_hits"] == []
