"""数据校验命令：扫描所有月度 JSON，报告字段缺失和类型异常

用法: python scripts/validate_data.py [--data-dir data/] [--verbose]
"""

import argparse
import json
import os
import sys

# 确保 scripts/ 在 import 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.schema import validate_paper


def main():
    parser = argparse.ArgumentParser(description="校验 DailyPaper 论文数据")
    parser.add_argument("--data-dir", default="data", help="数据目录（默认 data/）")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示每条警告")
    args = parser.parse_args()

    data_dir = args.data_dir
    total_papers = 0
    total_warnings = 0
    files_scanned = 0

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".json") or filename == "index.json":
            continue
        if filename.endswith(".bak"):
            continue
        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                papers = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR {filename}: read failed - {e}")
            continue

        if not isinstance(papers, list):
            continue

        files_scanned += 1
        file_warnings = 0

        for i, paper in enumerate(papers):
            warnings = validate_paper(paper)
            if warnings:
                file_warnings += len(warnings)
                if args.verbose:
                    for w in warnings:
                        paper_id = paper.get("id", f"index={i}")
                        print(f"  WARN {filename} [{paper_id}]: {w}")

        total_papers += len(papers)
        total_warnings += file_warnings
        status = "OK" if file_warnings == 0 else f"WARN {file_warnings} warnings"
        print(f"{'OK' if file_warnings == 0 else 'WARN'} {filename}: {len(papers)} papers, {status}")

    print(f"\n{'='*50}")
    print(f"Scanned {files_scanned} files, {total_papers} papers total")
    if total_warnings == 0:
        print("OK All papers passed validation")
    else:
        print(f"WARN {total_warnings} warnings total (use --verbose for details)")

    return 0 if total_warnings == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
