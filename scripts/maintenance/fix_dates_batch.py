"""
批量补全论文日期脚本（第二轮 - 剩余 31 篇）
增加请求间隔到 3 秒，优先使用 CrossRef（更稳定的速率限制）
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
import sys
import os
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

DELAY = 3  # 请求间隔秒数

def fetch_json(url, retries=3):
    """获取 JSON 数据，带指数退避重试"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'DailyPaperBot/1.0 (mailto:research@dailyPaper.org)',
                'Accept': 'application/json'
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = DELAY * (attempt + 2)  # 6s, 9s, 12s
                print(f"    [429 速率限制] 等待 {wait}s...")
                time.sleep(wait)
            else:
                print(f"    [HTTP {e.code}] {url[:80]}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(DELAY)
            else:
                print(f"    [ERROR] {e}")
                return None
    return None

def extract_date_from_crossref_parts(parts):
    """从 CrossRef date-parts 提取日期字符串"""
    if parts and parts.get('date-parts') and parts['date-parts'][0]:
        dp = parts['date-parts'][0]
        year = dp[0] if len(dp) > 0 else None
        month = dp[1] if len(dp) > 1 else 1
        day = dp[2] if len(dp) > 2 else 1
        if year:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None

def lookup_crossref_by_doi(doi):
    """通过 DOI 从 CrossRef 获取发布日期"""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    data = fetch_json(url)
    if not data:
        return None
    msg = data.get('message', {})
    for field in ['published-print', 'published-online', 'created', 'deposited']:
        result = extract_date_from_crossref_parts(msg.get(field, {}))
        if result:
            return result
    return None

def lookup_arxiv(arxiv_id):
    """通过 arXiv API 获取发布日期"""
    clean_id = arxiv_id.rstrip('v0123456789').rstrip('v')
    url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DailyPaperBot/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode('utf-8')
        root = ET.fromstring(text)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            published = entry.find('atom:published', ns)
            if published is not None and published.text:
                return published.text[:10]
    except Exception as e:
        print(f"    [ERROR] arXiv: {e}")
    return None

def lookup_crossref_by_title(title):
    """通过标题从 CrossRef 查找"""
    encoded = urllib.parse.quote(title[:300])
    url = f"https://api.crossref.org/works?query={encoded}&rows=5&select=DOI,title,published-print,published-online,created"
    data = fetch_json(url)
    if not data:
        return None
    items = data.get('message', {}).get('items', [])
    for item in items:
        titles = item.get('title', [])
        if not titles:
            continue
        # 更宽松的标题匹配：取两边前50字符的公共子串
        ref = titles[0].lower().replace('–', '-').replace('—', '-').replace("'", "'").strip()
        src = title.lower().replace('–', '-').replace('—', '-').replace("'", "'").strip()
        # 检查前40字符是否有足够的重叠
        ref_short = ref[:40].strip()
        src_short = src[:40].strip()
        if ref_short and src_short and (ref_short in src_short or src_short in ref_short):
            for field in ['published-print', 'published-online', 'created']:
                result = extract_date_from_crossref_parts(item.get(field, {}))
                if result:
                    return result
    return None

def lookup_semantic_scholar_by_title(title):
    """通过标题从 Semantic Scholar 查找"""
    encoded = urllib.parse.quote(title[:200])
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded}&limit=3&fields=externalIds,title,publicationDate"
    data = fetch_json(url)
    if not data or not data.get('data'):
        return None
    for paper in data['data']:
        if paper.get('publicationDate'):
            pd = paper['publicationDate']
            if len(pd) == 4:
                return f"{pd}-01-01"
            elif len(pd) == 7:
                return f"{pd}-01"
            return pd
    return None

def find_date(paper):
    """查找一篇论文的完整日期"""
    pid = paper['id']
    title = paper['title']

    # 1. arXiv 论文
    if pid.startswith('2') and ('arxiv' in paper.get('arxiv_url', '') or 'arxiv' in paper.get('pdf_url', '')):
        print(f"  [arXiv] {pid}")
        date = lookup_arxiv(pid)
        if date:
            return date
        time.sleep(DELAY)

    # 2. DOI 论文
    if pid.startswith('10.'):
        print(f"  [CrossRef DOI] {pid}")
        date = lookup_crossref_by_doi(pid)
        if date:
            return date
        time.sleep(DELAY)

    # 3. CrossRef 标题搜索
    print(f"  [CrossRef 标题] {title[:60]}...")
    date = lookup_crossref_by_title(title)
    if date:
        return date
    time.sleep(DELAY)

    # 4. Semantic Scholar 标题搜索
    print(f"  [Semantic Scholar] {title[:60]}...")
    date = lookup_semantic_scholar_by_title(title)
    if date:
        return date

    return None

def main():
    updated_count = 0

    for fname in ['data/2025-01.json', 'data/2026-01.json']:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict) and 'papers' in data:
            papers = data['papers']
        else:
            papers = data

        incomplete = []
        for i, p in enumerate(papers):
            pub = p.get('published', '')
            if len(pub) <= 4 or pub == '2026-01-01':
                incomplete.append((i, p))

        if not incomplete:
            print(f"\n{fname}: 全部已补全 ✓")
            continue

        print(f"\n{'='*60}")
        print(f"{fname}: 还有 {len(incomplete)} 篇待补全")
        print(f"{'='*60}")

        file_updated = 0
        for idx, (i, p) in enumerate(incomplete):
            print(f"\n[{idx+1}/{len(incomplete)}] {p['title'][:70]}")
            new_date = find_date(p)
            if new_date:
                old_date = p['published']
                papers[i]['published'] = new_date
                file_updated += 1
                updated_count += 1
                print(f"  ✓ {old_date} → {new_date}")
            else:
                print(f"  ✗ 未找到: {p['published']}")

            time.sleep(DELAY)

        # 保存文件
        if file_updated > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n  💾 {fname}: 已更新 {file_updated} 篇")

    print(f"\n{'='*60}")
    print(f"总计本轮更新: {updated_count} 篇")

if __name__ == '__main__':
    main()
