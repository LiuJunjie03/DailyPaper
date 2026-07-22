from daily_paper.chinese_pipeline import prepare_candidates
from daily_paper.classify import classify_paper


def test_first_seen_is_discovery_date_not_publication_date():
    config = {"categories": {}}
    candidate = {
        "id": "manual-one",
        "title": "基于深度学习的计算流体力学流场预测",
        "authors": "张三",
        "abstract": "机器学习方法用于CFD流场预测。",
        "published": "2025-01-01",
        "paper_url": "https://example.test/one",
        "venue": "空气动力学学报",
        "source": "manual_table",
        "publication_types": ["journal-article"],
        "official_keywords": ["计算流体力学", "深度学习"],
    }
    prepared, new_papers = prepare_candidates([candidate], [], config)
    assert len(new_papers) == 1
    assert prepared[0]["first_seen"] != prepared[0]["published"]
    assert 0 <= prepared[0]["relevance_score"] <= 100


def test_existing_paper_does_not_get_fake_first_seen():
    config = {"categories": {}}
    existing = [{"id": "old", "title": "神经网络计算流体力学", "published": "2024-01-01"}]
    candidate = {
        "id": "new-source-id",
        "title": "神经网络计算流体力学",
        "published": "2024-01-01",
        "abstract": "流体力学机器学习研究",
        "source": "manual_html",
    }
    prepared, new_papers = prepare_candidates([candidate], existing, config)
    assert not new_papers
    assert prepared[0]["first_seen"] == ""


def test_traditional_cfd_is_rejected_from_intelligent_pipeline():
    config = {"categories": {}}
    traditional = {
        "id": "traditional",
        "title": "基于CFD仿真的风力机尾流模型研究",
        "abstract": "采用雷诺平均方法完成风力机尾流数值模拟。",
        "published": "2026-01-01",
        "source": "official_journal",
    }
    prepared, new_papers = prepare_candidates([traditional], [], config)
    assert prepared == []
    assert new_papers == []


def test_intelligent_fluid_paper_gets_parent_tag_without_leaf_rule():
    config = {
        "categories": {
            "机器学习": {},
            "流体力学": {},
            "流体力学 / 智能CFD": {},
            "流体力学 / 空气动力学理论": {},
        }
    }
    paper = {
        "title": "气动性能智能预测模型及迁移学习框架",
        "abstract": "使用CFD数据研究飞行器气动性能。",
    }
    tags = classify_paper(paper, config)
    assert "机器学习" in tags
    assert "流体力学 / 智能CFD" in tags
