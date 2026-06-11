"""
修复脚本：对现有论文数据重新运行层级分类。
解决 2026-02 到 2026-06 论文缺少 "流体力学 / 智能CFD / ..." 层级标签的问题。
"""
import os
import sys
import json
import re

# 将项目根目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fetch_papers import PaperFetcher


def reclassify():
    fetcher = PaperFetcher()
    data_dir = fetcher.config.get("output", {}).get("data_dir", "data")

    total_papers = 0
    reclassified = 0

    for filename in sorted(os.listdir(data_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}\.json", filename):
            continue

        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            papers = json.load(f)

        changed = False
        for paper in papers:
            total_papers += 1
            old_tags = paper.get("tags", [])

            # 重新分类
            new_tags = fetcher.classify_paper(paper)

            if new_tags != old_tags:
                paper["tags"] = new_tags
                # 同步更新 primary_domain
                paper["primary_domain"] = new_tags[-1] if new_tags else ""
                changed = True
                reclassified += 1

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            print(f"  {filename}: updated")

    print(f"\nDone: {total_papers} papers scanned, {reclassified} reclassified.")


if __name__ == "__main__":
    reclassify()
