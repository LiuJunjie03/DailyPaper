#!/usr/bin/env python3
"""
更新论文数据 - 添加会议/期刊信息
从现有论文数据中提取并更新会议信息
"""

import json
import yaml
from pathlib import Path
import re


def load_config():
    """加载项目根目录的 config.yaml"""
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_venue_from_comment(comment: str, venues: list = None) -> str:
    """从 comment 字段提取会议/期刊信息"""
    if not comment:
        return None

    comment = comment.strip()

    # 如果是 preprint，返回 None
    if 'preprint' in comment.lower():
        return None

    if not venues:
        return None

    # 匹配：config 中的 venue 名 + 可选年份
    for venue in venues:
        # 提取短名称（config 中可能有括号注释）
        venue_name = venue.split("(")[0].strip() if "(" in venue else venue.strip()
        if not venue_name:
            continue
        if venue_name.lower() in comment.lower():
            # 尝试提取年份
            match = re.search(r'\b(19|20)\d{2}\b', comment)
            if match:
                return f"{venue_name} {match.group(0)}"
            return venue_name

    return None


def update_papers_with_venue():
    """更新论文数据，添加会议信息（遍历月度 JSON 文件）"""
    config = load_config()
    # 从 config.yaml 统一加载会议 + 期刊列表
    all_venues = (
        config.get("venues", {}).get("conferences", [])
        + config.get("venues", {}).get("journals", [])
    )
    print(f"📋 已加载 {len(all_venues)} 个会议/期刊名称")

    data_dir = Path("data")

    if not data_dir.exists():
        print("❌ data/ 目录不存在")
        return

    # 查找所有月度 JSON 文件（排除 index.json）
    monthly_files = sorted(data_dir.glob("2*.json"))

    if not monthly_files:
        print("❌ 未找到月度数据文件")
        return

    total_papers = 0
    total_updated = 0
    venue_count = {}

    for file_path in monthly_files:
        print(f"\n📂 处理 {file_path.name}...")

        with open(file_path, 'r', encoding='utf-8') as f:
            papers = json.load(f)

        updated_count = 0

        for paper in papers:
            comment = paper.get('comment')
            if comment:
                venue = extract_venue_from_comment(comment, all_venues)
                if venue:
                    paper['conference'] = venue
                    updated_count += 1
                    venue_name = venue.split()[0]
                    venue_count[venue_name] = venue_count.get(venue_name, 0) + 1

        # 保存更新后的数据
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

        total_papers += len(papers)
        total_updated += updated_count
        print(f"  ✅ {len(papers)} 篇论文，更新 {updated_count} 篇")

    print(f"\n{'=' * 40}")
    print(f"✅ 全部更新完成！")
    print(f"📊 统计：")
    print(f"  - 总论文数：{total_papers}")
    print(f"  - 有会议信息：{total_updated} 篇")
    print(f"  - 预印本：{total_papers - total_updated} 篇")

    if venue_count:
        print(f"\n📍 会议分布：")
        for venue, count in sorted(venue_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {venue}: {count} 篇")


if __name__ == "__main__":
    update_papers_with_venue()
