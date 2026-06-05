"""
一次性迁移脚本：用新的分类规则重新分类所有月度 JSON 中的论文。

用法：python scripts/migrate_categories.py
"""

import json
import os
import sys

# 将项目根目录加入搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_papers import PaperFetcher


def main():
    fetcher = PaperFetcher()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    total_migrated = 0
    total_papers = 0

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".json") or fname in ("index.json", "classification_report.json"):
            continue

        path = os.path.join(data_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            papers = json.load(f)

        count = 0
        for p in papers:
            old_tags = p.get("tags", [])
            old_domain = p.get("primary_domain", "")

            # 重新分类
            p["tags"] = fetcher.classify_paper(p)
            p["primary_domain"] = p["tags"][-1] if p.get("tags") else ""
            p["classification_score"] = fetcher._score_subdomains(p)

            if p["tags"] != old_tags or p["primary_domain"] != old_domain:
                count += 1

        with open(path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

        print(f"{fname}: {count}/{len(papers)} 篇论文分类已更新")
        total_migrated += count
        total_papers += len(papers)

    print(f"\n总计: {total_migrated}/{total_papers} 篇论文分类已更新")


if __name__ == "__main__":
    main()
