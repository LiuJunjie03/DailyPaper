#!/usr/bin/env python3
"""
简单测试 - 不限制时间，确保能抓到论文
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scripts.fetch_papers import PaperFetcher
from scripts.generate_html import HTMLGenerator


def simple_test():
    """简单测试 - 无时间限制"""
    print("🧪 简单测试开始（无时间限制）...")
    print("=" * 60)

    # 创建抓取器
    fetcher = PaperFetcher()

    # 修改配置：只抓取一个类别，不限制时间
    fetcher.config['sources']['arxiv']['categories'] = ['physics.flu-dyn']
    fetcher.config['sources']['arxiv']['max_results'] = 10
    fetcher.config['sources']['arxiv']['days_back'] = 365  # 1年内的论文都可以

    print("📥 正在抓取 physics.flu-dyn 类别的 10 篇最新论文（不限制时间）...")
    print()

    try:
        papers = fetcher.fetch_arxiv_papers()

        if papers:
            print(f"✅ 成功抓取 {len(papers)} 篇论文！")
            print()

            # 显示前3篇
            for i, paper in enumerate(papers[:3], 1):
                print(f"📄 论文 {i}:")
                print(f"  标题: {paper['title'][:80]}...")
                authors = paper['authors'] if isinstance(paper['authors'], list) else paper['authors'].split(', ')
                print(f"  作者: {', '.join(authors[:2])} {'等' if len(authors) > 2 else ''}")
                print(f"  发布: {paper['published']}")
                print(f"  标签: {', '.join(paper['tags']) if paper['tags'] else '未分类'}")
                print()

            # 保存数据（save_papers 内部会调用 fetch_arxiv_papers，此处直接重新保存）
            print("💾 保存数据...")
            fetcher.save_papers()
            print("✅ 数据已保存到 data/ 目录")
            print()

            # 生成网页
            print("🌐 生成网页...")
            generator = HTMLGenerator()
            generator.run()
            print()

            print("=" * 60)
            print("✨ 测试完全成功！")
            print()
            print("📝 下一步：")
            print("  1. 在浏览器中打开: docs/index.html")
            print("  2. 如果效果满意，可以修改 config.yaml 中的 days_back")
            print("  3. 运行完整抓取: python scripts/fetch_papers.py")
            print()
            return 0
        else:
            print("❌ 仍然未能抓取到论文")
            print()
            print("请检查：")
            print("  1. 网络连接是否正常")
            print("  2. 能否访问 https://arxiv.org")
            print()
            return 1

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(simple_test())
