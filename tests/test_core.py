# DailyPaper 核心逻辑单元测试
# 运行方式：pytest tests/ -v

import sys
from pathlib import Path

# 将 scripts/ 加入模块搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_papers import (
    normalize_title,
    normalize_doi,
    normalize_arxiv_id,
    term_in_text,
    is_relevant_paper,
    FLUID_RELATED_TERMS,
    FLUID_RELATED_TAGS,
    FLUID_RELATED_CATEGORIES,
    KEYWORD_CANONICAL,
    SUBDOMAIN_RULES,
    PARENT_TAGS,
)


# ========== normalize_title ==========

class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("  Hello   World  ") == "hello world"

    def test_empty(self):
        assert normalize_title("") == ""
        assert normalize_title(None) == ""

    def test_multiple_spaces(self):
        assert normalize_title("a   b    c") == "a b c"


# ========== normalize_doi ==========

class TestNormalizeDOI:
    def test_plain_doi(self):
        assert normalize_doi("10.1145/3708319") == "10.1145/3708319"

    def test_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1145/3708319") == "10.1145/3708319"
        assert normalize_doi("http://dx.doi.org/10.1145/3708319") == "10.1145/3708319"

    def test_empty(self):
        assert normalize_doi("") == ""
        assert normalize_doi(None) == ""

    def test_case_insensitive(self):
        assert normalize_doi("10.1145/ABC") == "10.1145/abc"


# ========== normalize_arxiv_id ==========

class TestNormalizeArxivId:
    def test_basic(self):
        assert normalize_arxiv_id("2305.02943") == "2305.02943"

    def test_url(self):
        assert normalize_arxiv_id("https://arxiv.org/abs/2305.02943") == "2305.02943"

    def test_version(self):
        assert normalize_arxiv_id("2305.02943v2") == "2305.02943"
        assert normalize_arxiv_id("2305.02943V3") == "2305.02943"

    def test_empty(self):
        assert normalize_arxiv_id("") == ""
        assert normalize_arxiv_id(None) == ""


# ========== term_in_text ==========

class TestTermInText:
    def test_basic_match(self):
        assert term_in_text("turbulence modeling", "turbulence") is True

    def test_word_boundary(self):
        # "rans" 不应匹配 "ransomware"
        assert term_in_text("ransomware attack", "rans") is False

    def test_case_insensitive(self):
        # term_in_text 对 term 做 .lower()，但 text 需要调用方先 .lower()
        assert term_in_text("CFD simulation".lower(), "cfd") is True
        # 大写 text 不会匹配小写 term（正则 lookbehind 只匹配 [a-z0-9]）
        assert term_in_text("CFD simulation", "cfd") is False

    def test_multi_word(self):
        assert term_in_text("computational fluid dynamics", "fluid dynamics") is True

    def test_empty_term(self):
        assert term_in_text("some text", "") is False
        assert term_in_text("some text", None) is False

    def test_empty_text(self):
        assert term_in_text("", "cfd") is False


# ========== is_relevant_paper ==========

class TestIsRelevantPaper:
    def test_tag_match(self):
        assert is_relevant_paper({"tags": ["流体力学"]}) is True
        assert is_relevant_paper({"tags": ["多相流"]}) is True

    def test_tag_prefix(self):
        assert is_relevant_paper({"tags": ["流体力学 / 智能CFD"]}) is True

    def test_category_match(self):
        assert is_relevant_paper({"tags": [], "categories": ["physics.flu-dyn"]}) is True

    def test_keyword_match(self):
        assert is_relevant_paper({
            "tags": [], "categories": [],
            "title": "CFD simulation of turbulent flow",
            "abstract": ""
        }) is True

    def test_keyword_no_false_positive(self):
        # "rans" in "ransomware" should not match
        assert is_relevant_paper({
            "tags": [], "categories": [],
            "title": "Ransomware detection using machine learning",
            "abstract": ""
        }) is False

    def test_irrelevant_paper(self):
        assert is_relevant_paper({
            "tags": [], "categories": [],
            "title": "Deep learning for natural language processing",
            "abstract": "We propose a new transformer architecture."
        }) is False


# ========== KEYWORD_CANONICAL ==========

class TestKeywordCanonical:
    def test_entries_are_lowercase(self):
        for key in KEYWORD_CANONICAL:
            assert key == key.lower(), f"Key '{key}' is not lowercase"

    def test_no_empty_values(self):
        for key, val in KEYWORD_CANONICAL.items():
            assert val.strip(), f"Empty value for key '{key}'"


# ========== SUBDOMAIN_RULES ==========

class TestSubdomainRules:
    def test_all_rules_have_strong(self):
        for name, rule in SUBDOMAIN_RULES.items():
            assert "strong" in rule, f"'{name}' missing 'strong' keywords"

    def test_all_subdomains_in_parent_tags(self):
        for name in SUBDOMAIN_RULES:
            assert name in PARENT_TAGS, f"'{name}' not in PARENT_TAGS"

    def test_parent_tags_values_are_lists(self):
        for name, parents in PARENT_TAGS.items():
            assert isinstance(parents, list), f"PARENT_TAGS['{name}'] is not a list"


# ========== 常量完整性 ==========

class TestConstants:
    def test_fluid_terms_not_empty(self):
        assert len(FLUID_RELATED_TERMS) > 0

    def test_fluid_tags_not_empty(self):
        assert len(FLUID_RELATED_TAGS) > 0

    def test_fluid_categories_not_empty(self):
        assert len(FLUID_RELATED_CATEGORIES) > 0
