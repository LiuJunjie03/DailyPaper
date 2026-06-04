#!/usr/bin/env python3
"""
更新论文数据 - 添加会议/期刊信息
从现有论文数据中提取并更新会议信息
"""

import json
from pathlib import Path
import re


def extract_venue_from_comment(comment: str) -> str:
    """从 comment 字段提取会议/期刊信息"""
    if not comment:
        return None

    comment = comment.strip()

    # 如果是 preprint，返回 None
    if 'preprint' in comment.lower():
        return None

    # 常见会议列表
    conferences = [
        'CVPR', 'ICCV', 'ECCV', 'NeurIPS', 'ICML', 'ICLR',
        'ACL', 'EMNLP', 'NAACL', 'AAAI', 'IJCAI', 'KDD',
        'ICRA', 'IROS', 'CoRL', 'RSS',
        'SIGIR', 'WWW', 'WSDM', 'RecSys',
        'SIGMOD', 'VLDB', 'ICDE',
        'SIGGRAPH', 'ICASSP', 'INTERSPEECH'
    ]

    # 匹配模式：会议名 + 年份
    for conf in conferences:
        pattern = rf'\b{conf}\s*[:\']?\s*(\d{{4}})\b'
        match = re.search(pattern, comment, re.IGNORECASE)
        if match:
            year = match.group(1)
            return f"{conf} {year}"

        pattern = rf'\b{conf}\b'
        if re.search(pattern, comment, re.IGNORECASE):
            return conf

    return None


def update_papers_with_venue():
    """更新论文数据，添加会议信息（遍历月度 JSON 文件）"""
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
                venue = extract_venue_from_comment(comment)
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
