"""
批量将论文导入 Zotero 并自动下载 PDF。

用法：
    # 导入所有有 DOI 的论文到 Zotero
    python scripts/export_to_zotero.py

    # 只导入指定月份
    python scripts/export_to_zotero.py --month 2026-05

    # 只导入指定分类
    python scripts/export_to_zotero.py --category "流体力学 / 智能CFD / 代理模型与算子学习"

    # 指定 Zotero 集合名称（默认自动按分类创建）
    python scripts/export_to_zotero.py --collection "智能CFD"

需要环境变量（或通过 config 设置）：
    ZOTERO_API_KEY  — Zotero API key（从 https://www.zotero.org/settings/keys 获取）
    ZOTERO_LIBRARY_ID — Zotero 用户 ID（从 https://www.zotero.org/settings/keys 页面查看）
"""
import os
import sys
import json
import re
import time
import argparse
import logging

# 将项目根目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from pyzotero import zotero
except ImportError:
    print("请先安装 pyzotero: pip install pyzotero")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """加载项目配置"""
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_papers(data_dir="data", month=None):
    """加载论文数据"""
    papers = []
    for fn in sorted(os.listdir(data_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}\.json", fn):
            continue
        if month and fn != f"{month}.json":
            continue
        with open(os.path.join(data_dir, fn), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            papers.extend(data)
    return papers


def get_zotero_client():
    """创建 Zotero API 客户端"""
    api_key = os.environ.get("ZOTERO_API_KEY", "")
    library_id = os.environ.get("ZOTERO_LIBRARY_ID", "")

    if not api_key or not library_id:
        print("请设置环境变量：")
        print("  export ZOTERO_API_KEY='你的API密钥'")
        print("  export ZOTERO_LIBRARY_ID='你的用户ID'")
        print()
        print("获取方式：https://www.zotero.org/settings/keys")
        sys.exit(1)

    return zotero.Zotero(library_id, "user", api_key)


def ensure_collection(zot_client, name, parent_key=None):
    """确保 Zotero 中存在指定集合，不存在则创建。返回集合 key。"""
    collections = zot_client.collections()
    for coll in collections:
        if coll["data"]["name"] == name:
            if parent_key is None or coll["data"].get("parentCollection") == parent_key:
                return coll["key"]

    # 不存在则创建
    template = zot_client.collection_template()
    template["name"] = name
    if parent_key:
        template["parentCollection"] = parent_key
    result = zot_client.create_collection(template)
    logger.info(f"创建集合: {name}")
    return result["key"] if isinstance(result, dict) else result


def find_collection_by_path(zot_client, path_parts):
    """按路径查找/创建嵌套集合。如 ['流体力学', '智能CFD', '代理模型'] """
    if not path_parts:
        return None

    collections = zot_client.collections()
    name_to_key = {}
    parent_map = {}
    for coll in collections:
        d = coll["data"]
        name_to_key[(d["name"], d.get("parentCollection") or None)] = d["key"]
        parent_map[d["key"]] = d.get("parentCollection") or None

    # 逐级查找/创建
    parent_key = None
    for part in path_parts:
        key = name_to_key.get((part, parent_key))
        if key:
            parent_key = key
        else:
            parent_key = ensure_collection(zot_client, part, parent_key)
            # 刷新缓存
            name_to_key[(part, parent_key)] = parent_key
    return parent_key


def paper_to_zotero_item(paper):
    """将论文数据转为 Zotero item 格式"""
    title = paper.get("title", "")
    authors_str = paper.get("authors", "")
    doi = (paper.get("doi") or "").strip()
    abstract = paper.get("abstract", "")
    pub_date = paper.get("published", "")
    venue = paper.get("venue") or paper.get("conference") or ""
    arxiv_id = paper.get("arxiv_id", "")
    url = paper.get("paper_url") or paper.get("arxiv_url") or ""

    # 判断类型
    item_type = "journalArticle"
    if arxiv_id and not doi and not venue:
        item_type = "preprint"
    elif venue and any(kw in venue.lower() for kw in ["conference", "proceedings", "symposium"]):
        item_type = "conferencePaper"

    # 作者列表
    creators = []
    if authors_str:
        for author in authors_str.split(","):
            author = author.strip()
            if not author:
                continue
            parts = author.rsplit(" ", 1)
            if len(parts) == 2:
                creators.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]})
            else:
                creators.append({"creatorType": "author", "name": author})

    item = {
        "itemType": item_type,
        "title": title,
        "creators": creators,
        "abstractNote": abstract,
        "date": pub_date,
        "url": url,
        "DOI": doi,
        "extra": "",
    }

    if item_type == "journalArticle" and venue:
        item["publicationTitle"] = venue
    elif item_type == "conferencePaper" and venue:
        item["proceedingsTitle"] = venue
    elif item_type == "preprint":
        item["repository"] = "arXiv"
        item["archiveID"] = f"arXiv:{arxiv_id}" if arxiv_id else ""

    # 标签
    tags = paper.get("tags", [])
    item["tags"] = [{"tag": t} for t in tags if t]

    return item


def download_pdf_for_paper(paper):
    """尝试下载论文的开放获取 PDF，返回 (bytes, filename) 或 None"""
    arxiv_id = paper.get("arxiv_id", "")
    pdf_url = paper.get("pdf_url") or paper.get("preprint_pdf_url") or ""

    # ArXiv PDF
    if arxiv_id and not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    if not pdf_url:
        return None

    try:
        resp = requests.get(pdf_url, timeout=30, headers={
            "User-Agent": "DailyPaper/1.0 (mailto:research@example.com)"
        })
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/pdf"):
            filename = re.sub(r'[\\/:*?"<>|]', '_', paper.get("title", "paper")[:80]) + ".pdf"
            return (resp.content, filename)
    except Exception as e:
        logger.warning(f"PDF 下载失败: {e}")

    return None


def main():
    parser = argparse.ArgumentParser(description="批量导入论文到 Zotero")
    parser.add_argument("--month", help="只导入指定月份 (如 2026-05)")
    parser.add_argument("--category", help="只导入指定分类的论文")
    parser.add_argument("--collection", help="指定 Zotero 集合名称")
    parser.add_argument("--no-pdf", action="store_true", help="不下载 PDF")
    parser.add_argument("--limit", type=int, default=0, help="限制导入数量")
    args = parser.parse_args()

    config = load_config()
    data_dir = config.get("output", {}).get("data_dir", "data")
    papers = load_papers(data_dir, args.month)

    # 按分类筛选
    if args.category:
        papers = [p for p in papers if args.category in p.get("tags", [])]

    # 只保留有 DOI 或 arXiv ID 的论文
    eligible = [p for p in papers if (p.get("doi") or "").strip() or p.get("arxiv_id")]
    if args.limit > 0:
        eligible = eligible[:args.limit]

    if not eligible:
        print("没有可导入的论文（需要有 DOI 或 arXiv ID）")
        return

    print(f"共 {len(eligible)} 篇论文待导入")

    # 连接 Zotero
    zot = get_zotero_client()
    logger.info("已连接 Zotero")

    # 确定 Zotero 集合
    collection_key = None
    if args.collection:
        collection_key = ensure_collection(zot, args.collection)
    elif args.category:
        # 按分类路径创建嵌套集合
        path_parts = [p.strip() for p in args.category.split("/") if p.strip()]
        collection_key = find_collection_by_path(zot, path_parts)

    success = 0
    failed = 0

    for i, paper in enumerate(eligible):
        title = paper.get("title", "")[:60]
        doi = (paper.get("doi") or "").strip()
        logger.info(f"[{i+1}/{len(eligible)}] {title}...")

        try:
            # 检查是否已存在（通过 DOI 去重）
            if doi:
                existing = zot.items(q=doi, limit=1)
                if existing and doi in str(existing):
                    logger.info(f"  已存在，跳过")
                    continue

            # 创建 Zotero item
            item_data = paper_to_zotero_item(paper)
            if collection_key:
                item_data["collections"] = [collection_key]

            # 用 DOI 优先（Zotero 会自动获取更好的元数据）
            if doi:
                result = zot.create_items([{"itemType": "journalArticle", "DOI": doi}])
                if result and result.get("successful"):
                    created_key = list(result["successful"].values())[0].get("key")
                    # 添加标签和集合
                    if created_key:
                        tags = [{"tag": t} for t in paper.get("tags", []) if t]
                        if tags or collection_key:
                            update = {}
                            if tags:
                                update["tags"] = tags
                            if collection_key:
                                update["collections"] = [collection_key]
                            zot.update_item({"key": created_key, **update})
                else:
                    # DOI 导入失败，手动创建
                    result = zot.create_items([item_data])
            else:
                result = zot.create_items([item_data])

            # 下载并附加 PDF
            if not args.no_pdf and result and result.get("successful"):
                created_key = list(result["successful"].values())[0].get("key")
                if created_key:
                    pdf_data = download_pdf_for_paper(paper)
                    if pdf_data:
                        content, filename = pdf_data
                        zot.attachment_simple([{"title": filename}], created_key)
                        # 使用 storage upload
                        try:
                            zot.upload_attachment(created_key, filename, content)
                        except Exception:
                            pass
                        logger.info(f"  ✓ 已附加 PDF")

            success += 1
            time.sleep(1)  # 避免请求过快

        except Exception as e:
            logger.warning(f"  ✗ 导入失败: {e}")
            failed += 1

    print(f"\n完成：成功 {success} 篇，失败 {failed} 篇")


if __name__ == "__main__":
    main()
