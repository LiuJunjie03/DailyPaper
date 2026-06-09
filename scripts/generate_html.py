#!/usr/bin/env python3
"""
生成静态网页脚本
将论文数据生成为 HTML 页面（适配按月份拆分的 JSON 数据源）
"""

import json
from pathlib import Path
from datetime import datetime
import re
from typing import List, Dict
import logging
import yaml
import os
import copy
import hashlib

# 关键词规范化与相关性判断：从 fetch_papers 导入，保持单一数据源
try:
    from fetch_papers import KEYWORD_CANONICAL, is_relevant_paper, term_in_text
    from fetch_papers import FLUID_RELATED_TERMS, FLUID_RELATED_TAGS, FLUID_RELATED_CATEGORIES
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("fetch_papers", Path(__file__).parent / "fetch_papers.py")
    _fp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_fp)
    KEYWORD_CANONICAL = _fp.KEYWORD_CANONICAL
    is_relevant_paper = _fp.is_relevant_paper
    term_in_text = _fp.term_in_text
    FLUID_RELATED_TERMS = _fp.FLUID_RELATED_TERMS
    FLUID_RELATED_TAGS = _fp.FLUID_RELATED_TAGS
    FLUID_RELATED_CATEGORIES = _fp.FLUID_RELATED_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_complete_publication_date(value: str) -> bool:
    """Return True only for real day-level publication dates."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")))


def publication_date_key(paper: Dict) -> str:
    """Sortable date key; incomplete year/month placeholders sort last."""
    published = str(paper.get("published", ""))
    return published if is_complete_publication_date(published) else "0000-00-00"

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

class HTMLGenerator:
    """HTML 生成器（适配按月份拆分的数据源）"""
    
    def __init__(self, data_dir: str = "data",
                 output_dir: str = "docs"):
        # 关键修改1：不再依赖单一papers.json，改为读取data目录下的月度文件
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
        # 清空原有数据
        self.papers = []
        self.papers_by_month = {}
        
        # 查找所有YYYY-MM.json格式的月度文件
        month_files = list(self.data_dir.glob("????-??.json"))
        if not month_files:
            logger.warning(f"未找到任何月度数据文件（格式：YYYY-MM.json），目录：{self.data_dir}")
            return
        
        # 遍历所有月度文件加载数据
        for month_file in sorted(month_files, reverse=True):
            year_month = month_file.stem  # 提取"2025-07"这样的月份标识
            try:
                with open(month_file, 'r', encoding='utf-8') as f:
                    month_papers = json.load(f)
                month_papers = [paper for paper in month_papers if is_relevant_paper(paper)]
                
                # 添加到总论文列表
                self.papers.extend(month_papers)
                # 按月份分组
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

        # 同步已有月度文件到docs/data目录（规范化关键词）
        for year_month, papers in self.papers_by_month.items():
            file_path = data_dir / f"{year_month}.json"
            normalized = self._normalize_papers_keywords(papers)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            logger.info(f"同步月度数据文件到输出目录: {file_path} ({len(papers)} 篇)")
        
        # 生成/更新索引文件
        months_index = []
        for year_month in sorted(self.papers_by_month.keys(), reverse=True):
            papers = self.papers_by_month[year_month]
            months_index.append({
                'month': year_month,
                'count': len(papers),
                'published_count': sum(1 for p in papers if p.get('conference')),
                'preprint_count': sum(1 for p in papers if not p.get('conference'))
            })
        
        index_file = data_dir / "index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(months_index, f, ensure_ascii=False, indent=2)
        
        logger.info(f"生成/更新月份索引文件: {index_file}")
    
    def generate_month_buttons(self):
        """生成月份筛选按钮"""
        buttons = []
        for year_month in sorted(self.papers_by_month.keys(), reverse=True):
            count = len(self.papers_by_month[year_month])
            buttons.append(f'<button class="filter-btn month-btn" data-month="{year_month}">{year_month} ({count})</button>')
        return '\n                    '.join(buttons)
    
    def generate_category_buttons(self, category_counts):
        """生成研究领域筛选按钮（从config.yaml读取）"""
        buttons = []
        buttons.append(f'<button class="filter-btn category-btn active" data-category="all">全部 ({category_counts["all"]})</button>')
        for category in CATEGORIES:
            display_name = category.replace("Natural Language Processing", "NLP")
            count = category_counts.get(category, 0)
            buttons.append(f'<button class="filter-btn category-btn" data-category="{category}">{display_name} ({count})</button>')
        return '\n                    '.join(buttons)
    
    def generate_index_html(self):
        """生成主页 HTML"""
        published_count = sum(1 for p in self.papers if p.get('conference'))
        preprint_count = sum(1 for p in self.papers if not p.get('conference'))
        pdf_count = sum(1 for p in self.papers if p.get('pdf_url') or p.get('preprint_pdf_url') or p.get('arxiv_id'))
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")
        today_count = sum(1 for p in self.papers if str(p.get('published', '')) == today)
        current_month_count = sum(
            1 for p in self.papers
            if is_complete_publication_date(p.get('published', ''))
            and str(p.get('published', '')).startswith(current_month)
        )
        smart_cfd_count = sum(1 for p in self.papers if "流体力学 / 智能CFD" in p.get('tags', []))
        
        # 动态计算每个分类的论文数
        category_counts = {'all': len(self.papers)}
        for category in CATEGORIES:
            category_counts[category] = sum(1 for p in self.papers if category in p.get('tags', []))

        template_dir = Path(__file__).parent / "templates"
        css_hash = self._content_hash((template_dir / "style.css").read_text(encoding="utf-8"))
        js_hash = self._content_hash((template_dir / "main.js").read_text(encoding="utf-8"))
        data_hash = self._content_hash(json.dumps(self.papers, ensure_ascii=False, sort_keys=True))
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DailyPaper - CFD+ML 最新论文</title>
    <link rel="stylesheet" href="css/style.css?v={css_hash}">
    <script>window.CATEGORIES = {json.dumps(CATEGORIES)};</script>
    <script>window.DATA_VERSION = "{data_hash}";</script>
</head>
<body>
    <header>
        <div class="header-formula header-formula-left" aria-hidden="true">
            ∂ρ/∂t + ∇·(ρ<strong>v</strong>) = 0
        </div>
        <div class="header-formula header-formula-right" aria-hidden="true">
            Re = ρvL/μ
        </div>
        <div class="container">
            <h1>DailyPaper</h1>
            <p class="subtitle">计算流体力学 + 机器学习论文雷达</p>
            <p class="update-time">最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
    </header>
    
    <nav class="container">
        <div class="dashboard-summary" aria-label="数据概览">
            <div class="summary-item">
                <span class="summary-value">{today_count}</span>
                <span class="summary-label">今日新增</span>
            </div>
            <div class="summary-item">
                <span class="summary-value">{current_month_count}</span>
                <span class="summary-label">本月新增</span>
            </div>
            <div class="summary-item">
                <span class="summary-value">{pdf_count}</span>
                <span class="summary-label">有 PDF</span>
            </div>
            <div class="summary-item">
                <span class="summary-value">{published_count}</span>
                <span class="summary-label">已发表</span>
            </div>
            <div class="summary-item">
                <span class="summary-value">{smart_cfd_count}</span>
                <span class="summary-label">智能 CFD</span>
            </div>
        </div>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="🔍 搜索标题、作者、摘要..." aria-label="搜索论文">
        </div>
        <div class="quick-filter-row">
            <div class="filter-group">
                <label class="filter-label">排序方式</label>
                <div class="filters sort-filters">
                    <button class="filter-btn sort-btn active" data-sort="date-desc">最新优先</button>
                    <button class="filter-btn sort-btn" data-sort="date-asc">最早优先</button>
                    <button class="filter-btn sort-btn" data-sort="importance-desc">推荐优先</button>
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">发表状态</label>
                <div class="filters status-filters">
                    <button class="filter-btn status-btn active" data-status="all">全部 ({len(self.papers)})</button>
                    <button class="filter-btn status-btn" data-status="published">已发表 ({published_count})</button>
                    <button class="filter-btn status-btn" data-status="preprint">预印本 ({preprint_count})</button>
                </div>
            </div>
            <p class="sort-note">推荐分综合发表状态、来源、PDF、摘要、关键词、引用和日期；数据不足时按日期补偿。</p>
        </div>
        <details class="filter-panel">
            <summary>筛选条件</summary>
            <div class="filter-section">
            <div class="filter-group">
                <label class="filter-label">月份</label>
                <div class="filters month-filters">
                    <button class="filter-btn month-btn active" data-month="all">全部 ({len(self.papers)})</button>
                    {self.generate_month_buttons()}
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">全文状态</label>
                <div class="filters pdf-filters">
                    <button class="filter-btn pdf-btn active" data-pdf="all">全部</button>
                    <button class="filter-btn pdf-btn" data-pdf="available">有PDF</button>
                    <button class="filter-btn pdf-btn" data-pdf="missing">无PDF</button>
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">研究领域</label>
                <div class="filters category-filters">
                    {self.generate_category_buttons(category_counts)}
                </div>
            </div>
            </div>
        </details>
        <div class="results-info">
            <span id="resultsCount">加载中...</span>
            <div class="export-controls">
                <button class="select-btn" id="selectAllBtn">✓ 选中当前页</button>
                <button class="select-btn" id="clearAllBtn">✗ 清空</button>
                <button class="export-btn" id="exportBtn">🔗 打开PDF (<span id="selectedCount">0</span>)</button>
                <button class="export-btn export-btn-secondary" id="copyDoiBtn">📋 复制标识符</button>
            </div>
        </div>
    </nav>
    
    <main class="container" aria-label="论文列表">
        <div id="papers-container">
            <!-- Papers will be loaded by JavaScript -->
        </div>
    </main>
    
    <footer>
        <div class="container">
            <p>© 2025 DailyPaper | 数据来源: ArXiv · Semantic Scholar · Google Scholar · CNKI | <a href="https://github.com/LiuJunjie03/DailyPaper" target="_blank">GitHub</a></p>
        </div>
    </footer>
    
    <script src="js/main.js?v={js_hash}"></script>
</body>
</html>
"""
        
        output_file = self.output_dir / "index.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"生成主页: {output_file}")
    
    def get_category_name(self, category: str) -> str:
        """将 ArXiv 类别代码转换为友好的名称"""
        category_map = {
            'cs.AI': 'Artificial Intelligence',
            'cs.CV': 'Computer Vision',
            'cs.CL': 'Computational Linguistics (NLP)',
            'cs.LG': 'Machine Learning',
            'cs.IR': 'Information Retrieval',
            'cs.RO': 'Robotics',
            'cs.NE': 'Neural and Evolutionary Computing',
            'cs.CR': 'Cryptography and Security',
            'cs.HC': 'Human-Computer Interaction',
            'cs.MM': 'Multimedia',
            'stat.ML': 'Machine Learning (Statistics)',
            'physics.flu-dyn': 'Fluid Dynamics (CFD)',
        }
        return category_map.get(category, category)
    
    def extract_code_links(self, abstract: str) -> Dict[str, str]:
        """从摘要中提取代码和项目链接"""
        import re
        links = {}
        
        code_pattern = r'[Cc]ode[:\s]+(?:available at\s+)?(\S+)'
        code_match = re.search(code_pattern, abstract)
        if code_match:
            links['code'] = code_match.group(1).rstrip('.,;')
        
        project_pattern = r'[Pp]roject[:\s]+(?:page\s+)?(\S+)'
        project_match = re.search(project_pattern, abstract)
        if project_match:
            links['project'] = project_match.group(1).rstrip('.,;')
        
        github_pattern = r'(https?://(?:www\.)?github\.com/[\w\-]+/[\w\-]+)'
        github_match = re.search(github_pattern, abstract)
        if github_match and 'code' not in links:
            links['code'] = github_match.group(1)
        
        return links
    
    def get_venue_badge(self, conference: str) -> tuple:
        """获取会议徽章的样式类和显示文本"""
        if not conference:
            return ('preprint', 'Preprint')
        
        venue_styles = {
            'NeurIPS': ('venue-neurips', 'NeurIPS'),
            'CVPR': ('venue-cvpr', 'CVPR'),
            'ICCV': ('venue-iccv', 'ICCV'),
            'ECCV': ('venue-eccv', 'ECCV'),
            'ICML': ('venue-icml', 'ICML'),
            'ICLR': ('venue-iclr', 'ICLR'),
            'ACL': ('venue-acl', 'ACL'),
            'EMNLP': ('venue-emnlp', 'EMNLP'),
            'AAAI': ('venue-aaai', 'AAAI'),
            'IJCAI': ('venue-ijcai', 'IJCAI'),
        }
        
        for venue_name, (style, display) in venue_styles.items():
            if venue_name in conference:
                return (style, conference)
        
        return ('venue-other', conference)
    
    def generate_papers_html(self) -> str:
        """生成论文列表 HTML"""
        if not self.papers:
            return '<p class="no-results">暂无论文数据</p>'
        
        html_parts = []
        for paper in self.papers:
            tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in paper.get('tags', [])])
            authors_html = ', '.join(paper['authors'][:5])
            if len(paper['authors']) > 5:
                authors_html += ' et al.'
            
            primary_category = paper.get('primary_category', paper['venue'])
            category_name = self.get_category_name(primary_category)
            
            conference = paper.get('conference')
            venue_class, venue_display = self.get_venue_badge(conference)
            
            is_published = 'published' if conference else 'preprint'
            
            code_links = self.extract_code_links(paper['abstract'])
            code_links_html = ''
            if code_links.get('code'):
                code_links_html += f'<a href="{code_links["code"]}" target="_blank" class="btn-link btn-code">💻 Code</a>'
            if code_links.get('project'):
                code_links_html += f'<a href="{code_links["project"]}" target="_blank" class="btn-link btn-project">🌐 Project</a>'
            
            paper_html = f"""
            <article class="paper-card" data-tags="{','.join(paper.get('tags', []))}" data-status="{is_published}" data-date="{paper['published']}">
                <div class="venue-badge {venue_class}">{venue_display}</div>
                <h2 class="paper-title">
                    <a href="{paper['arxiv_url']}" target="_blank">{paper['title']}</a>
                </h2>
                <div class="paper-meta">
                    <span class="meta-item">📅 {paper['published']}</span>
                    <span class="meta-item">📖 ArXiv {category_name}</span>
                </div>
                <div class="paper-authors">
                    👥 {authors_html}
                </div>
                <div class="paper-tags">
                    {tags_html}
                </div>
                <div class="paper-abstract">
                    <details>
                        <summary>查看摘要</summary>
                        <p>{paper['abstract']}</p>
                    </details>
                </div>
                <div class="paper-links">
                    <a href="{paper['pdf_url']}" target="_blank" class="btn-link">📄 PDF</a>
                    <a href="{paper['arxiv_url']}" target="_blank" class="btn-link">🔗 ArXiv</a>
                    {code_links_html}
                </div>
            </article>
            """
            html_parts.append(paper_html)
        
        return '\n'.join(html_parts)
    
    def generate_css(self):
        """生成 CSS 样式 — 从模板文件读取"""
        template_path = Path(__file__).parent / "templates" / "style.css"
        css = template_path.read_text(encoding="utf-8")
        css_dir = self.output_dir / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        css_file = css_dir / "style.css"
        content_hash = self._content_hash(css)
        hash_file = css_dir / "style.css.hash"

        # 仅当模板内容变更时才重新生成，避免覆盖用户自定义修改
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
        """生成 JavaScript 文件 — 从模板文件读取"""
        template_path = Path(__file__).parent / "templates" / "main.js"
        js = template_path.read_text(encoding="utf-8")
        
        js_dir = self.output_dir / "js"
        js_dir.mkdir(parents=True, exist_ok=True)

        js_file = js_dir / "main.js"
        content_hash = self._content_hash(js)
        hash_file = js_dir / "main.js.hash"

        # 仅当模板内容变更时才重新生成，避免覆盖用户自定义修改
        if js_file.exists() and hash_file.exists():
            existing_hash = hash_file.read_text(encoding="utf-8").strip()
            if existing_hash == content_hash:
                logger.info("JavaScript 文件内容未变化，跳过生成")
                return

        with open(js_file, 'w', encoding='utf-8') as f:
            f.write(js)
        hash_file.write_text(content_hash, encoding="utf-8")
        logger.info("生成 JavaScript 文件")
    
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
