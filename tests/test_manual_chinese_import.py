from pathlib import Path

from daily_paper.sources.journal_sites import parse_issue_links
from daily_paper.sources.manual_chinese import import_file


def _config():
    return {
        "categories": {
            "机器学习": {"keywords": ["机器学习", "深度学习", "神经网络"]},
            "流体力学": {"keywords": ["计算流体力学", "流场", "CFD"]},
        }
    }


def test_imports_ris_refworks_endnote_and_csv(tmp_path: Path):
    samples = {
        "sample.ris": """TY  - JOUR
TI  - 基于神经网络的计算流体力学流场预测
AU  - 张三
JO  - 空气动力学学报
PY  - 2026/07/01
DO  - 10.1234/example
AB  - 使用深度学习代理模型预测CFD流场。
KW  - 深度学习
KW  - 流场预测
ER  -
""",
        "sample.refworks": """RT Journal Article
T1 物理信息神经网络流体模拟
A1 李四
JF 力学学报
YR 2026
AB 计算流体力学和机器学习方法。

""",
        "sample.enw": """%0 Journal Article
%T 深度学习湍流闭合模型
%A 王五
%J 计算物理
%D 2026
%X 面向流体力学数值模拟。

""",
        "sample.csv": "题名,作者,摘要,关键词,期刊,出版日期,DOI,链接\n代理模型流场重建,赵六,计算流体力学机器学习,代理模型;流场,航空学报,2026-07-02,10.1/test,https://example.test/paper\n",
    }
    for name, content in samples.items():
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        papers = import_file(path, _config())
        assert len(papers) == 1, name
        assert papers[0]["title"]
        assert papers[0]["source"].startswith("manual_")


def test_imports_saved_article_html(tmp_path: Path):
    path = tmp_path / "article.html"
    path.write_text(
        """<html><head>
        <meta name="citation_title" content="基于神经算子的湍流模拟方法">
        <meta name="citation_author" content="张三">
        <meta name="citation_journal_title" content="力学学报">
        <meta name="citation_publication_date" content="2026-07-01">
        <meta name="citation_abstract" content="神经算子用于计算流体力学湍流模拟。">
        <meta name="citation_keywords" content="神经算子;湍流;计算流体力学">
        </head></html>""",
        encoding="utf-8",
    )
    papers = import_file(path, _config())
    assert len(papers) == 1
    assert papers[0]["venue"] == "力学学报"
    assert "神经算子" in papers[0]["official_keywords"]


def test_issue_parser_keeps_article_links_only():
    html = """<nav><a href="/cn/about">关于</a></nav>
    <a href="/article/doi/10.1234/test">基于深度学习的流场预测方法</a>
    <a href="/article/doi/10.1234/test?viewType=HTML">HTML</a>
    <a href="/data/article/pdf/preview/test.pdf">PDF</a>"""
    records = parse_issue_links(html, "https://journal.test/cn/article/current", {})
    assert records == [{
        "title": "基于深度学习的流场预测方法",
        "paper_url": "https://journal.test/article/doi/10.1234/test",
        "venue": "",
    }]
