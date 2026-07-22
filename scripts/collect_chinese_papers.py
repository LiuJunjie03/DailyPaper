"""Run the local Chinese intelligent-CFD pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

from daily_paper.chinese_pipeline import (
    discovery_now,
    load_existing,
    merge_and_save,
    prepare_candidates,
    render_daily_report,
    write_run_json,
)
from daily_paper.sources.journal_sites import fetch_official_journal_papers
from daily_paper.sources.manual_chinese import import_paths

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="采集中文智能 CFD 期刊论文")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--import-path", action="append", default=[])
    parser.add_argument("--portals", action="store_true", help="尝试知网、万方、维普（需本地机构登录）")
    parser.add_argument("--no-official", action="store_true", help="跳过期刊官网公开目录")
    parser.add_argument("--no-html", action="store_true", help="不重新生成 GitHub Pages")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    data_dir = ROOT / config.get("output", {}).get("data_dir", "data")
    import_paths_config = config.get("chinese_pipeline", {}).get("import_paths", ["imports/chinese"])
    paths = [Path(item) if Path(item).is_absolute() else ROOT / item for item in (args.import_path or import_paths_config)]
    paths = [path for path in paths if path.exists()]

    source_batches = {}
    if not args.no_official:
        source_batches["official_journal"] = fetch_official_journal_papers(config)
    source_batches["manual_import"] = import_paths(paths, config)
    if args.portals:
        from daily_paper.sources.cnki import fetch_cnki_papers
        from daily_paper.sources.cqvip import fetch_cqvip_papers
        from daily_paper.sources.wanfang import fetch_wanfang_papers

        for name, fetcher in (("cnki", fetch_cnki_papers), ("wanfang", fetch_wanfang_papers), ("cqvip", fetch_cqvip_papers)):
            try:
                source_batches[name] = fetcher(config)
            except Exception as exc:
                print(f"[warning] {name} unavailable: {exc}", file=sys.stderr)
                source_batches[name] = []

    raw_candidates = [paper for batch in source_batches.values() for paper in batch]
    existing = load_existing(data_dir)
    candidates, new_papers = prepare_candidates(raw_candidates, existing, config)
    merge_and_save(existing, candidates, data_dir)

    source_counts = dict(Counter({name: len(batch) for name, batch in source_batches.items()}))
    day, _ = discovery_now()
    render_daily_report(new_papers, candidates, source_counts, ROOT / "reports" / "chinese" / f"{day}.md")
    write_run_json(new_papers, candidates, source_counts, data_dir / "chinese_runs" / f"{day}.json")
    if not args.no_html:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_html.py")], cwd=ROOT)
        if result.returncode:
            return result.returncode
    print(f"中文采集完成：候选 {len(candidates)} 篇，首次发现 {len(new_papers)} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
