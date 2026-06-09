"""通过 CrossRef API 补全论文真实发表日期（仅处理非 ArXiv 来源的 -01-01 日期）"""
import json
import glob
import os
import time
import requests

DATA_DIR = "data"


def fetch_crossref_date(doi):
    """从 CrossRef 获取论文的实际发表日期"""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "DailyPaper/1.0"})
        if resp.status_code == 200:
            data = resp.json()["message"]
            # 优先用 published-print，其次 published-online，再次 created
            for field in ["published-print", "published-online", "created"]:
                parts = data.get(field, {}).get("date-parts", [[]])
                if parts and parts[0]:
                    y, m, d = parts[0][0], parts[0][1] if len(parts[0]) > 1 else 1, parts[0][2] if len(parts[0]) > 2 else 1
                    return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception as e:
        print(f"  CrossRef 查询失败 {doi}: {e}")
    return None


def fetch_semantic_scholar_date(title):
    """从 Semantic Scholar 搜索获取发表日期"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": title, "fields": "publicationDate", "limit": 1}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                pub_date = data["data"][0].get("publicationDate")
                if pub_date and len(pub_date) >= 10:
                    return pub_date[:10]
                elif pub_date and len(pub_date) == 7:
                    return f"{pub_date}-15"  # 取月中
                elif pub_date and len(pub_date) == 4:
                    return f"{pub_date}-07-01"  # 取年中
    except Exception:
        pass
    return None


total_fixed = 0
total_checked = 0

for f in sorted(glob.glob(os.path.join(DATA_DIR, "????-??.json"))):
    with open(f, "r", encoding="utf-8") as fh:
        papers = json.load(fh)

    modified = False
    for p in papers:
        pub = p.get("published", "")
        source = p.get("source", "")

        # 只处理非 ArXiv 且日期是 -01-01 的论文
        if source == "arxiv" or not pub.endswith("-01-01"):
            continue

        # 检查这个 -01-01 是否是我们之前补全的（原始只有年份）
        # 通过检查月份文件名和日期是否匹配来判断
        month_file = os.path.basename(f).replace(".json", "")
        if pub[:7] == month_file and month_file.endswith("-01"):
            total_checked += 1
            doi = p.get("doi", "")
            new_date = None

            if doi:
                new_date = fetch_crossref_date(doi)
                time.sleep(0.5)

            if not new_date:
                new_date = fetch_semantic_scholar_date(p.get("title", ""))
                time.sleep(1)

            if new_date:
                print(f"  {pub} -> {new_date}  {p.get('title', '')[:50]}")
                p["published"] = new_date
                total_fixed += 1
                modified = True
            else:
                print(f"  未能获取: {pub} doi={doi} {p.get('title', '')[:40]}")

    if modified:
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(papers, fh, ensure_ascii=False, indent=2)
        print(f"已更新 {os.path.basename(f)}")

print(f"\n检查: {total_checked} 篇，补全: {total_fixed} 篇")
