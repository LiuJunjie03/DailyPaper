#!/usr/bin/env python3
"""
生成静态网页脚本
将论文数据生成为 HTML 页面（适配按月份拆分的 JSON 数据源）
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import re
from typing import List, Dict
import logging
import yaml
import os
import copy
import hashlib
from jinja2 import Environment, FileSystemLoader

# 关键词规范化与相关性判断：从 fetch_papers 导入，保持单一数据源
from fetch_papers import KEYWORD_CANONICAL, is_relevant_paper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_complete_publication_date(value: str) -> bool:
    """Return True only for real day-level publication dates."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")))


# 加载config.yaml的函数
def load_config():
    """加载项目根目录的config.yaml配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        logger.error(f"配置文件不存在: {config_path}")
        raise FileNotFoundError(f"config.yaml not found at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info(f"成功加载配置文件，包含分类: {list(config.get('categories', {}).keys())}")
    return config


# 加载配置（全局使用）
config = load_config()
# 获取配置里的分类列表
CATEGORIES = list(config.get('categories', {}).keys())


def build_subdir_trends(papers_by_month: dict) -> dict:
    """计算智能CFD子方向按月的论文数量，用于前端趋势折线图"""
    # 子方向列表：以 "流体力学 / 智能CFD /" 开头的分类
    subdirs = [c for c in CATEGORIES if c.startswith("流体力学 / 智能CFD /")]
    months = sorted(papers_by_month.keys())
    # 只取最近 12 个月
    recent_months = months[-12:] if len(months) > 12 else months
    trends = {}
    for month in recent_months:
        papers = papers_by_month.get(month, [])
        for subdir in subdirs:
            count = sum(1 for p in papers if subdir in p.get('tags', []))
            trends.setdefault(subdir, {})[month] = count
    # 子方向简称（取最后一段）
    short_names = {s: s.split('/')[-1].strip() for s in subdirs}
    return {"months": recent_months, "subdirs": subdirs, "short_names": short_names, "trends": trends}


def build_dashboard_stats(papers: list, papers_by_month: dict) -> dict:
    """纯计算，无 I/O，可单测。返回模板所需的全部统计数据。"""
    today = datetime.now().strftime("%Y-%m-%d")
    current_month = datetime.now().strftime("%Y-%m")

    today_count = sum(1 for p in papers if str(p.get('published', '')) == today)
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    this_week_count = sum(
        1 for p in papers
        if is_complete_publication_date(p.get('published', ''))
        and week_start <= str(p.get('published', '')) <= today
    )
    current_month_count = sum(
        1 for p in papers
        if is_complete_publication_date(p.get('published', ''))
        and str(p.get('published', '')).startswith(current_month)
    )
    previous_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    previous_month_count = sum(
        1 for p in papers
        if is_complete_publication_date(p.get('published', ''))
        and str(p.get('published', '')).startswith(previous_month)
    )
    month_delta = current_month_count - previous_month_count
    if month_delta > 0:
        month_compare_text = f"较上月 +{month_delta}"
    elif month_delta < 0:
        month_compare_text = f"较上月 {month_delta}"
    else:
        month_compare_text = "较上月持平"

    published_count = sum(1 for p in papers if p.get('conference'))
    preprint_count = sum(1 for p in papers if not p.get('conference'))
    pdf_count = sum(1 for p in papers if p.get('pdf_url') or p.get('preprint_pdf_url') or p.get('arxiv_id'))
    smart_cfd_count = sum(1 for p in papers if "流体力学 / 智能CFD" in p.get('tags', []))
    early_access_count = sum(1 for p in papers if p.get('is_early_access'))

    total_count = max(len(papers), 1)
    pdf_rate = round(pdf_count * 100 / total_count)
    published_rate = round(published_count * 100 / total_count)
    smart_cfd_rate = round(smart_cfd_count * 100 / total_count)
    early_access_rate = round(early_access_count * 100 / total_count)

    smart_leaf_counts = {}
    for paper in papers:
        for tag in paper.get('tags', []):
            if str(tag).startswith("流体力学 / 智能CFD /"):
                smart_leaf_counts[tag] = smart_leaf_counts.get(tag, 0) + 1
    smart_top = sorted(smart_leaf_counts.items(), key=lambda item: item[1], reverse=True)[:2]
    smart_top_lines = [f"{name.split('/')[-1].strip()} {count}" for name, count in smart_top] or ["子方向待积累"]
    smart_top_html = "<br>".join(smart_top_lines)

    return {
        "today": today,
        "current_month": current_month,
        "today_count": today_count,
        "this_week_count": this_week_count,
        "current_month_count": current_month_count,
        "previous_month_count": previous_month_count,
        "month_compare_text": month_compare_text,
        "published_count": published_count,
        "preprint_count": preprint_count,
        "pdf_count": pdf_count,
        "smart_cfd_count": smart_cfd_count,
        "early_access_count": early_access_count,
        "total_count": len(papers),
        "pdf_rate": pdf_rate,
        "published_rate": published_rate,
        "smart_cfd_rate": smart_cfd_rate,
        "early_access_rate": early_access_rate,
        "smart_top_text": " · ".join(smart_top_lines),
        "smart_top_html": smart_top_html,
        "smart_top_lines": smart_top_lines,
    }


class HTMLGenerator:
    """HTML 生成器（适配按月份拆分的数据源）"""

    def __init__(self, data_dir: str = "data",
                 output_dir: str = "docs"):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.papers = []
        self.papers_by_month = {}  # 按月份分组的论文

    @staticmethod
    def _content_hash(content: str) -> str:
        """计算内容的短哈希值，用于检测模板是否变更"""
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _normalize_papers_keywords(papers: List[Dict]) -> List[Dict]:
        """对论文列表的关键词进行规范化（深拷贝，不修改原数据）"""
        result = []
        for p in papers:
            p_copy = copy.deepcopy(p)
            kws = p_copy.get("keywords") or []
            normalized = set()
            for kw in kws:
                canonical = KEYWORD_CANONICAL.get(kw.lower().strip(), kw)
                normalized.add(canonical)
            p_copy["keywords"] = sorted(normalized)
            result.append(p_copy)
        return result

    def load_papers(self):
        """加载论文数据（从月度JSON文件读取，替代原papers.json）"""
        self.papers = []
        self.papers_by_month = {}

        month_files = list(self.data_dir.glob("????-??.json"))
        if not month_files:
            logger.warning(f"未找到任何月度数据文件（格式：YYYY-MM.json），目录：{self.data_dir}")
            return

        for month_file in sorted(month_files, reverse=True):
            year_month = month_file.stem
            try:
                with open(month_file, 'r', encoding='utf-8') as f:
                    month_papers = json.load(f)
                _today = datetime.now().strftime("%Y-%m-%d")
                for paper in month_papers:
                    if "is_early_access" not in paper:
                        _pub = paper.get("published", "")
                        paper["is_early_access"] = (
                            len(_pub) >= 10 and _pub > _today
                            and bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))
                        )
                month_papers = [paper for paper in month_papers if is_relevant_paper(paper)]

                self.papers.extend(month_papers)
                self.papers_by_month[year_month] = month_papers

                logger.info(f"加载月度文件: {month_file} ({len(month_papers)} 篇论文)")
            except Exception as e:
                logger.error(f"加载月度文件失败: {month_file}，错误: {e}")
                continue

        logger.info(f"总计加载了 {len(self.papers)} 篇论文")
        logger.info(f"论文分布: {', '.join([f'{k}: {len(v)}篇' for k, v in sorted(self.papers_by_month.items(), reverse=True)])}")

    def generate_monthly_data_files(self):
        """生成按月份分离的数据文件（适配已有月度文件，仅同步到docs目录）"""
        data_dir = self.output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        for year_month, papers in self.papers_by_month.items():
            file_path = data_dir / f"{year_month}.json"
            normalized = self._normalize_papers_keywords(papers)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            logger.info(f"同步月度数据文件到输出目录: {file_path} ({len(papers)} 篇)")

        months_index = []
        for year_month in sorted(self.papers_by_month.keys(), reverse=True):
            papers = self.papers_by_month[year_month]
            months_index.append({
                'month': year_month,
                'count': len(papers),
                'published_count': sum(1 for p in papers if p.get('conference')),
                'preprint_count': sum(1 for p in papers if not p.get('conference')),
                'early_access_count': sum(1 for p in papers if p.get('is_early_access'))
            })

        index_file = data_dir / "index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(months_index, f, ensure_ascii=False, indent=2)

        logger.info(f"生成/更新月份索引文件: {index_file}")

    def generate_index_html(self):
        """生成主页 HTML — 通过 Jinja2 模板渲染"""
        stats = build_dashboard_stats(self.papers, self.papers_by_month)
        subdir_trends = build_subdir_trends(self.papers_by_month)

        # 分类统计
        category_counts = {'all': len(self.papers)}
        for category in CATEGORIES:
            category_counts[category] = sum(1 for p in self.papers if category in p.get('tags', []))

        # 月份按钮数据
        month_buttons = [
            (ym, len(papers))
            for ym, papers in sorted(self.papers_by_month.items(), reverse=True)
        ]

        # 分类按钮数据
        category_buttons = [
            (cat, cat.replace("Natural Language Processing", "NLP"), category_counts.get(cat, 0))
            for cat in CATEGORIES
        ]

        # 内容哈希
        template_dir = Path(__file__).parent / "templates"
        css_hash = self._content_hash((template_dir / "style.css").read_text(encoding="utf-8"))
        # 合并所有 JS 模块的哈希（任一模块变化都会刷新缓存）
        js_files = sorted(template_dir.glob("*.js"))
        js_hash = self._content_hash("".join(f.read_text(encoding="utf-8") for f in js_files))
        data_hash = self._content_hash(
            "|".join(sorted(p.get("id", "") for p in self.papers))
        )

        # Jinja2 渲染
        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        template = env.get_template("index.html")
        html = template.render(
            css_hash=css_hash,
            js_hash=js_hash,
            data_hash=data_hash,
            categories_json=json.dumps(CATEGORIES),
            subdir_trends_json=json.dumps(subdir_trends, ensure_ascii=False),
            now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            year=datetime.now().year,
            stats=stats,
            month_buttons=month_buttons,
            category_buttons=category_buttons,
            category_counts=category_counts,
        )

        output_file = self.output_dir / "index.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"生成主页: {output_file}")

    def generate_css(self):
        """生成 CSS 样式 — 从模板文件读取"""
        template_path = Path(__file__).parent / "templates" / "style.css"
        css = template_path.read_text(encoding="utf-8")
        css_dir = self.output_dir / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        css_file = css_dir / "style.css"
        content_hash = self._content_hash(css)
        hash_file = css_dir / "style.css.hash"

        if css_file.exists() and hash_file.exists():
            existing_hash = hash_file.read_text(encoding="utf-8").strip()
            if existing_hash == content_hash:
                logger.info("CSS 样式文件内容未变化，跳过生成")
                return

        with open(css_file, 'w', encoding='utf-8') as f:
            f.write(css)
        hash_file.write_text(content_hash, encoding="utf-8")
        logger.info("生成 CSS 样式文件")

    def generate_js(self):
        """生成 JavaScript 模块 — 将 templates/ 下所有 .js 文件复制到 docs/js/"""
        template_dir = Path(__file__).parent / "templates"
        js_dir = self.output_dir / "js"
        js_dir.mkdir(parents=True, exist_ok=True)

        for js_file in sorted(template_dir.glob("*.js")):
            content = js_file.read_text(encoding="utf-8")
            content_hash = self._content_hash(content)
            hash_file = js_dir / (js_file.name + ".hash")
            dest = js_dir / js_file.name

            if dest.exists() and hash_file.exists():
                if hash_file.read_text(encoding="utf-8").strip() == content_hash:
                    continue

            dest.write_text(content, encoding="utf-8")
            hash_file.write_text(content_hash, encoding="utf-8")
            logger.info(f"生成 JS 模块: {js_file.name}")

    def run(self):
        """运行生成流程"""
        logger.info("开始生成静态网页...")

        self.load_papers()
        self.generate_monthly_data_files()
        self.generate_css()
        self.generate_js()
        self.generate_index_html()

        logger.info(f"网页生成完成! 输出目录: {self.output_dir}")


def main():
    generator = HTMLGenerator()
    generator.run()


if __name__ == "__main__":
    main()
