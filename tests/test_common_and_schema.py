"""Phase 1+2 测试：common 模块 + schema 校验"""


from daily_paper.text import normalize_title, normalize_doi, normalize_arxiv_id, term_in_text, clean_text
from daily_paper.dates import validate_date, parse_date, in_date_window
from daily_paper.queries import flatten_queries
from daily_paper.schema import validate_paper


# ============================================================
# common/text.py
# ============================================================

class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("  Hello   World  ") == "hello world"

    def test_empty(self):
        assert normalize_title("") == ""
        assert normalize_title(None) == ""

    def test_multiple_spaces(self):
        assert normalize_title("a\t\nb") == "a b"


class TestNormalizeDOI:
    def test_plain_doi(self):
        assert normalize_doi("10.1000/xyz123") == "10.1000/xyz123"

    def test_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1000/xyz123") == "10.1000/xyz123"
        assert normalize_doi("http://doi.org/10.1000/xyz123") == "10.1000/xyz123"

    def test_empty(self):
        assert normalize_doi("") == ""
        assert normalize_doi(None) == ""


class TestNormalizeArxivId:
    def test_basic(self):
        assert normalize_arxiv_id("2605.25679") == "2605.25679"

    def test_url(self):
        assert normalize_arxiv_id("http://arxiv.org/abs/2605.25679") == "2605.25679"

    def test_version(self):
        assert normalize_arxiv_id("2605.25679v1") == "2605.25679"

    def test_empty(self):
        assert normalize_arxiv_id("") == ""
        assert normalize_arxiv_id(None) == ""


class TestTermInText:
    def test_basic_match(self):
        assert term_in_text("CFD simulation", "CFD") is True

    def test_word_boundary(self):
        assert term_in_text("verification", "ratio") is False

    def test_case_insensitive(self):
        assert term_in_text("TURBULENCE model", "turbulence") is True

    def test_empty(self):
        assert term_in_text("some text", "") is False
        assert term_in_text("", "CFD") is False


class TestCleanText:
    def test_basic(self):
        assert clean_text("  hello   world  ") == "hello world"

    def test_html_entities(self):
        assert clean_text("a &amp; b") == "a & b"

    def test_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""


# ============================================================
# common/dates.py
# ============================================================

class TestValidateDate:
    def test_valid(self):
        assert validate_date("2026-05-28") == "2026-05-28"

    def test_incomplete(self):
        assert validate_date("2026-05") == ""
        assert validate_date("2026") == ""

    def test_empty(self):
        assert validate_date("") == ""
        assert validate_date(None) == ""


class TestParseDate:
    def test_iso(self):
        assert parse_date("2024-03-15") == "2024-03-15"

    def test_chinese(self):
        assert parse_date("2024年3月15日") == "2024-03-15"

    def test_slash(self):
        assert parse_date("2024/3/15") == "2024-03-15"

    def test_year_only(self):
        result = parse_date("2024")
        assert result == "2024" or result.startswith("2024")


class TestInDateWindow:
    def test_in_range(self):
        assert in_date_window("2026-05-15", "2026-01-01", "2026-12-31") is True

    def test_before(self):
        assert in_date_window("2025-12-31", "2026-01-01", "2026-12-31") is False

    def test_after(self):
        assert in_date_window("2027-01-01", "2026-01-01", "2026-12-31") is False

    def test_incomplete_date_passes(self):
        assert in_date_window("2026-05", "2026-01-01", "2026-12-31") is True


# ============================================================
# common/queries.py
# ============================================================

class TestFlattenQueries:
    def test_list(self):
        assert flatten_queries(["q1", "q2"]) == ["q1", "q2"]

    def test_dict(self):
        config = {"queries": {"g1": ["q1", "q2"], "g2": "q3"}}
        assert flatten_queries(config) == ["q1", "q2", "q3"]

    def test_strips_whitespace(self):
        assert flatten_queries(["  q1  ", " q2 "]) == ["q1", "q2"]

    def test_raw_list(self):
        raw = ["a", "b", "c"]
        assert flatten_queries(raw) == ["a", "b", "c"]


# ============================================================
# common/schema.py
# ============================================================

class TestValidatePaper:
    def test_valid_paper(self):
        paper = {
            "id": "test-001",
            "title": "Test Paper",
            "authors": "Alice, Bob",
            "published": "2026-05-01",
            "source": "arxiv",
        }
        assert validate_paper(paper) == []

    def test_missing_required_fields(self):
        paper = {"id": "test-001"}
        warnings = validate_paper(paper)
        assert len(warnings) >= 4  # title, authors, published, source
        for field in ["title", "authors", "published", "source"]:
            assert any(field in w for w in warnings)

    def test_invalid_citation_count_type(self):
        paper = {
            "id": "test", "title": "T", "authors": "A",
            "published": "2026-01-01", "source": "arxiv",
            "citation_count": "not_a_number"
        }
        warnings = validate_paper(paper)
        assert any("citation_count" in w for w in warnings)

    def test_invalid_date_format(self):
        paper = {
            "id": "test", "title": "T", "authors": "A",
            "published": "May 2026", "source": "arxiv"
        }
        warnings = validate_paper(paper)
        assert any("published" in w for w in warnings)

    def test_non_http_url(self):
        paper = {
            "id": "test", "title": "T", "authors": "A",
            "published": "2026-01-01", "source": "arxiv",
            "paper_url": "ftp://example.com/paper"
        }
        warnings = validate_paper(paper)
        assert any("paper_url" in w for w in warnings)

    def test_empty_record(self):
        warnings = validate_paper({})
        assert len(warnings) >= 5

    def test_tags_type_check(self):
        paper = {
            "id": "test", "title": "T", "authors": "A",
            "published": "2026-01-01", "source": "arxiv",
            "tags": "not_a_list"
        }
        warnings = validate_paper(paper)
        assert any("tags" in w for w in warnings)
