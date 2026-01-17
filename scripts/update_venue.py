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
        # 匹配 "CVPR 2025" 或 "Accepted to CVPR 2025" 等模式
        pattern = rf'\b{conf}\s*[:\']?\s*(\d{{4}})\b'
        match = re.search(pattern, comment, re.IGNORECASE)
        if match:
            year = match.group(1)
            return f"{conf} {year}"
        
        # 匹配只有会议名的情况
        pattern = rf'\b{conf}\b'
        if re.search(pattern, comment, re.IGNORECASE):
            return conf
    
    return None


def update_papers_with_venue():
    """更新论文数据，添加会议信息"""
    data_file = Path("data/papers.json")
    
    if not data_file.exists():
        print("❌ papers.json 不存在")
        return
    
    # 读取论文数据
    with open(data_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)
    
    print(f"📚 加载了 {len(papers)} 篇论文")
    
    # 统计
    updated_count = 0
    venue_count = {}
    
    # 更新会议信息
    for paper in papers:
        comment = paper.get('comment')
        if comment:
            venue = extract_venue_from_comment(comment)
            if venue:
                paper['conference'] = venue
                updated_count += 1
                
                # 统计
                venue_name = venue.split()[0]  # 只取会议名
                venue_count[venue_name] = venue_count.get(venue_name, 0) + 1
    
    # 保存更新后的数据
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 更新完成！")
    print(f"📊 统计：")
    print(f"  - 总论文数：{len(papers)}")
    print(f"  - 有会议信息：{updated_count} 篇")
    print(f"  - 预印本：{len(papers) - updated_count} 篇")
    
    if venue_count:
        print(f"\n📍 会议分布：")
        for venue, count in sorted(venue_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {venue}: {count} 篇")


if __name__ == "__main__":
    update_papers_with_venue()
