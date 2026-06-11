"""store.py 关键用例测试 — 月度写入、索引生成、日期拆分"""

import json


from daily_paper.storage import load_monthly_data, split_papers_by_month, save_monthly_data, build_month_index


def _make_paper(title="Test Paper", published="2026-03-15", source="test"):
    """生成一条最小合法论文记录"""
    return {
        "id": "test-001",
        "title": title,
        "published": published,
        "source": source,
    }


class TestSplitPapersByMonth:
    """split_papers_by_month 关键用例"""

    def test_normal_dates(self):
        """正常 YYYY-MM-DD 日期分配到正确月份桶"""
        papers = [
            _make_paper(published="2026-01-10"),
            _make_paper(published="2026-01-20"),
            _make_paper(published="2026-02-05"),
        ]
        result = split_papers_by_month(papers)
        assert set(result.keys()) == {"2026-01", "2026-02"}
        assert len(result["2026-01"]) == 2
        assert len(result["2026-02"]) == 1

    def test_year_only_goes_to_unknown_month(self):
        """只有年份的日期归到 YYYY-unk 桶，标记 _date_precision"""
        papers = [_make_paper(published="2026")]
        result = split_papers_by_month(papers)
        assert "2026-unk" in result
        assert result["2026-unk"][0]["_date_precision"] == "year"

    def test_unknown_date_goes_to_unknown_bucket(self):
        """日期为空或无法解析时归到 unknown 桶"""
        papers = [
            _make_paper(published=""),
            _make_paper(published="unknown"),
        ]
        result = split_papers_by_month(papers)
        assert "unknown" in result
        assert len(result["unknown"]) == 2

    def test_empty_list(self):
        """空列表返回空字典"""
        assert split_papers_by_month([]) == {}


class TestSaveAndLoadMonthlyData:
    """save_monthly_data + load_monthly_data 往返测试"""

    def test_roundtrip(self, tmp_path):
        """写入后能正确读回"""
        month_papers = {
            "2026-01": [_make_paper(title="Paper A"), _make_paper(title="Paper B")],
            "2026-02": [_make_paper(title="Paper C")],
        }
        save_monthly_data(month_papers, str(tmp_path), docs_dir="")

        loaded = load_monthly_data(str(tmp_path))
        assert set(loaded.keys()) == {"2026-01", "2026-02"}
        assert len(loaded["2026-01"]) == 2
        assert loaded["2026-01"][0]["title"] == "Paper A"

    def test_ignores_non_monthly_files(self, tmp_path):
        """加载时跳过非 YYYY-MM.json 文件"""
        (tmp_path / "index.json").write_text("[]", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "2026-01.json").write_text(
            json.dumps([_make_paper()]), encoding="utf-8"
        )
        loaded = load_monthly_data(str(tmp_path))
        assert list(loaded.keys()) == ["2026-01"]


class TestBuildMonthIndex:
    """build_month_index 关键用例"""

    def test_index_structure(self, tmp_path):
        """索引文件包含正确的月份和计数"""
        papers = [
            _make_paper(title="A"),
            _make_paper(title="B", published="2026-02-01"),
        ]
        month_papers = {"2026-02": papers, "2026-01": [_make_paper()]}
        save_monthly_data(month_papers, str(tmp_path), docs_dir="")
        build_month_index(str(tmp_path))

        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert len(index) == 2
        # 按月份倒序
        assert index[0]["month"] == "2026-02"
        assert index[0]["count"] == 2
        assert index[1]["month"] == "2026-01"
        assert index[1]["count"] == 1

    def test_index_counts_preprints(self, tmp_path):
        """索引正确统计 preprint 和 early_access"""
        papers = [
            {"id": "1", "title": "A", "published": "2026-01-01", "source": "arxiv",
             "is_preprint": True, "is_early_access": False},
            {"id": "2", "title": "B", "published": "2026-01-02", "source": "crossref",
             "is_preprint": False, "is_early_access": True},
        ]
        month_papers = {"2026-01": papers}
        save_monthly_data(month_papers, str(tmp_path), docs_dir="")
        build_month_index(str(tmp_path))

        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        entry = index[0]
        assert entry["preprint_count"] == 1
        assert entry["early_access_count"] == 1
        assert entry["published_count"] == 1
