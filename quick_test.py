#!/usr/bin/env python3
"""
简单测试 - 只抓取少量论文进行快速验证
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scripts.fetch_papers import PaperFetcher
from scripts.generate_html import HTMLGenerator


def quick_test():
    """快速测试 - 只抓取一个类别"""
    print("🧪 快速测试开始...")
    print("=" * 60)

    fetcher = PaperFetcher()

    # 使用项目实际类别，限制数量和时间范围
    fetcher.config['sources']['arxiv']['categories'] = ['physics.flu-dyn']
    fetcher.config['sources']['arxiv']['max_results'] = 10
    fetcher.config['sources']['arxiv']['days_back'] = 30

    print("📥 正在抓取 physics.flu-dyn 类别的 10 篇最新论文...")
    print()

    try:
        papers = fetcher.fetch_arxiv_papers()

        if papers:
            print(f"✅ 成功抓取 {len(papers)} 篇论文！")
            print()
            authors = papers[0]['authors'] if isinstance(papers[0]['authors'], list) else papers[0]['authors'].split(', ')
            print("📄 第一篇论文信息：")
            print(f"  标题: {papers[0]['title']}")
            print(f"  作者: {', '.join(authors[:2])} {'等' if len(authors) > 2 else ''}")
            print(f"  日期: {papers[0]['published']}")
            print(f"  分类: {', '.join(papers[0]['tags']) if papers[0]['tags'] else '未分类'}")
            print(f"  链接: {papers[0]['arxiv_url']}")
            print()

            # 保存数据
            print("💾 保存数据...")
            fetcher.save_papers()
            print("✅ 数据保存成功")
            print()

            # 生成网页
            print("🌐 生成网页...")
            generator = HTMLGenerator()
            generator.run()
            print()

            print("=" * 60)
            print("✨ 测试完全成功！")
            print()
            print("📝 下一步操作：")
            print("  1. 在浏览器中打开: docs/index.html")
            print("  2. 查看生成的网页效果")
            print("  3. 运行完整测试: python test.py")
            print("  4. 或者直接抓取所有类别: python scripts/fetch_papers.py")
            print()
            return 0
        else:
            print("❌ 未能抓取到论文")
            print()
            print("可能的原因：")
            print("  1. 网络连接问题")
            print("  2. ArXiv API 暂时不可用")
            print("  3. days_back 设置过小，最近没有新论文")
            print()
            return 1

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(quick_test())
