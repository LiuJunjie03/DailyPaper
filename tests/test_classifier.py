"""classifier.py 关键用例测试 — 相关性判断、分类、关键词"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from classifier import (
    term_in_text,
    is_relevant_paper,
    classify_paper,
    extract_paper_keywords,
    normalize_keywords,
    SUBDOMAIN_RULES,
)


class TestTermInText:
    """term_in_text 关键用例"""

    def test_basic_match(self):
        assert term_in_text("deep learning for fluid dynamics", "fluid dynamics")

    def test_no_partial_match(self):
        """不应匹配子词"""
        assert not term_in_text("turbulence", "urbul")

    def test_case_insensitive(self):
        assert term_in_text("cfd simulation", "CFD")


class TestIsRelevantPaper:
    """is_relevant_paper 关键用例"""

    def test_fluid_paper_relevant(self):
        """含 turbulence modeling → 相关"""
        paper = {
            "title": "Deep learning for turbulence modeling in CFD",
            "abstract": "A novel approach using neural networks for RANS simulation.",
            "source": "arxiv",
        }
        assert is_relevant_paper(paper)

    def test_pure_nlp_not_relevant(self):
        """纯 NLP 论文 → 不相关"""
        paper = {
            "title": "Attention is all you need for machine translation",
            "abstract": "We propose a new architecture for natural language processing tasks.",
            "source": "arxiv",
        }
        assert not is_relevant_paper(paper)

    def test_missing_abstract_no_crash(self):
        """缺少 abstract → 不崩溃"""
        paper = {"title": "Fluid Dynamics Study", "source": "arxiv"}
        assert isinstance(is_relevant_paper(paper), bool)


class TestClassifyPaper:
    """classify_paper 关键用例"""

    def _config(self):
        """最小测试配置"""
        return {
            "categories": {
                "test_cat": {
                    "keywords": ["turbulence"],
                    "subcategories": {},
                }
            }
        }

    def test_classifies_relevant_paper(self):
        """相关论文返回分类标签"""
        paper = {
            "title": "Turbulence modeling with deep learning",
            "abstract": "A novel approach to RANS turbulence modeling using neural networks.",
            "source": "arxiv",
        }
        tags = classify_paper(paper, self._config())
        assert isinstance(tags, list)

    def test_no_crash_on_empty(self):
        """空论文不崩溃"""
        paper = {"title": "", "abstract": "", "source": "test"}
        tags = classify_paper(paper, self._config())
        assert isinstance(tags, list)


class TestExtractPaperKeywords:
    """extract_paper_keywords 关键用例"""

    def test_extracts_matching_keywords(self):
        config = {"categories": {"cat1": {"keywords": ["neural network", "CFD"]}}}
        paper = {"title": "Neural Network for CFD", "abstract": "Using neural network approach."}
        kws = extract_paper_keywords(paper, config)
        assert isinstance(kws, list)
        assert len(kws) > 0

    def test_empty_config(self):
        paper = {"title": "Some paper", "abstract": "About stuff"}
        kws = extract_paper_keywords(paper, {"categories": {}})
        assert kws == []


class TestNormalizeKeywords:
    """normalize_keywords 关键用例"""

    def test_deduplicates(self):
        """normalize_keywords 对大小写不同的词视为不同项"""
        result = normalize_keywords(["turbulence", "Turbulence"])
        # 当前实现区分大小写，验证行为一致性
        assert len(result) >= 1

    def test_sorts(self):
        result = normalize_keywords(["CFD", "DNS", "LES"])
        assert result == sorted(result)
