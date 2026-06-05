#!/usr/bin/env python3
"""
生成静态网页脚本
将论文数据生成为 HTML 页面（适配按月份拆分的 JSON 数据源）
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging
import yaml
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

FLUID_RELATED_TAGS = {
    "多相流",
    "空气动力学",
    "智能流体力学",
    "流体力学",
    "CFD与机器学习交叉",
}

FLUID_RELATED_TERMS = [
    "cfd",
    "computational fluid dynamics",
    "fluid dynamics",
    "fluid mechanics",
    "flow simulation",
    "flow modeling",
    "flow computation",
    "turbulence",
    "rans",
    "les",
    "dns",
    "multiphase flow",
    "two-phase flow",
    "aerodynamics",
    "airfoil",
    "navier-stokes",
    "lattice boltzmann",
    "finite volume",
]

FLUID_RELATED_CATEGORIES = {
    "physics.flu-dyn",
    "physics.comp-ph",
    "physics.ao-ph",
}


def is_relevant_paper(paper: Dict) -> bool:
    tags = set(paper.get("tags") or [])
    if tags & FLUID_RELATED_TAGS:
        return True
    if any(tag == "流体力学" or str(tag).startswith("流体力学 /") for tag in tags):
        return True

    categories = {str(cat).lower() for cat in paper.get("categories") or []}
    if categories & FLUID_RELATED_CATEGORIES:
        return True

    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    return any(term in text for term in FLUID_RELATED_TERMS)


class HTMLGenerator:
    """HTML 生成器（适配按月份拆分的数据源）"""
    
    def __init__(self, data_dir: str = "data", 
                 output_dir: str = "docs"):
        # 关键修改1：不再依赖单一papers.json，改为读取data目录下的月度文件
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.papers = []
        self.papers_by_month = {}  # 按月份分组的论文
        
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
        
        # 同步已有月度文件到docs/data目录
        for year_month, papers in self.papers_by_month.items():
            file_path = data_dir / f"{year_month}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
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
        """生成主页 HTML（新增重要程度排序按钮）"""
        published_count = sum(1 for p in self.papers if p.get('conference'))
        preprint_count = sum(1 for p in self.papers if not p.get('conference'))
        
        # 动态计算每个分类的论文数
        category_counts = {'all': len(self.papers)}
        for category in CATEGORIES:
            category_counts[category] = sum(1 for p in self.papers if category in p.get('tags', []))
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DailyPaper - CFD+ML 最新论文</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <header>
        <div class="container">
            <h1>📚 DailyPaper</h1>
            <p class="subtitle">每日自动更新 计算流体力学+机器学习 领域最新论文</p>
            <p class="update-time">最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
    </header>
    
    <nav class="container">
        <div class="filter-section">
            <div class="filter-group">
                <label class="filter-label">📅 月份：</label>
                <div class="filters month-filters">
                    <button class="filter-btn month-btn active" data-month="all">全部 ({len(self.papers)})</button>
                    {self.generate_month_buttons()}
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">📌 发表状态：</label>
                <div class="filters status-filters">
                    <button class="filter-btn status-btn active" data-status="all">全部 ({len(self.papers)})</button>
                    <button class="filter-btn status-btn" data-status="published">已发表 ({published_count})</button>
                    <button class="filter-btn status-btn" data-status="preprint">预印本 ({preprint_count})</button>
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">📄 全文状态：</label>
                <div class="filters pdf-filters">
                    <button class="filter-btn pdf-btn active" data-pdf="all">全部</button>
                    <button class="filter-btn pdf-btn" data-pdf="available">有PDF</button>
                    <button class="filter-btn pdf-btn" data-pdf="missing">无PDF</button>
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">🏷️ 研究领域：</label>
                <div class="filters category-filters">
                    {self.generate_category_buttons(category_counts)}
                </div>
            </div>
            <div class="filter-group">
                <label class="filter-label">🔄 排序方式：</label>
                <div class="filters sort-filters">
                    <button class="filter-btn sort-btn active" data-sort="date-desc">最新优先</button>
                    <button class="filter-btn sort-btn" data-sort="date-asc">最早优先</button>
                    <!-- 关键修改2：添加重要程度排序按钮 -->
                    <button class="filter-btn sort-btn" data-sort="importance-desc">重要程度优先</button>
                </div>
            </div>
        </div>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="🔍 搜索论文标题、作者、摘要...">
        </div>
        <div class="results-info">
            <span id="resultsCount">加载中...</span>
            <div class="export-controls">
                <button class="select-btn" id="selectAllBtn">✓ 全选</button>
                <button class="select-btn" id="clearAllBtn">✗ 清空</button>
                <button class="export-btn" id="exportBtn">📥 下载选中PDF (<span id="selectedCount">0</span>)</button>
            </div>
        </div>
    </nav>
    
    <main class="container">
        <div id="papers-container">
            <!-- Papers will be loaded by JavaScript -->
        </div>
    </main>
    
    <footer>
        <div class="container">
            <p>© 2025 DailyPaper | 数据来源: ArXiv | <a href="https://github.com/LiuJunjie03/DailyPaper" target="_blank">GitHub</a></p>
        </div>
    </footer>
    
    <script src="js/main.js"></script>
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
        """生成 CSS 样式（包含关键词区分样式）"""
        css = """/* 全局样式 */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f5f5f5;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

/* 头部样式 */
header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 2rem 0;
    text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

header h1 {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
}

.subtitle {
    font-size: 1.1rem;
    opacity: 0.9;
}

.update-time {
    font-size: 0.9rem;
    opacity: 0.8;
    margin-top: 0.5rem;
}

/* 导航和筛选 */
nav {
    background: white;
    padding: 1.5rem 20px;
    margin: 2rem auto;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.filter-section {
    margin-bottom: 1rem;
}

.filter-group {
    margin-bottom: 1rem;
}

.filter-label {
    display: inline-block;
    font-weight: 600;
    color: #333;
    margin-bottom: 0.5rem;
    font-size: 0.95rem;
}

.filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.category-filters {
    flex-direction: column;
    align-items: flex-start;
}

.category-breadcrumb,
.category-children {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.category-children {
    padding-left: 0.75rem;
    border-left: 3px solid #e3e8ff;
}

.category-back-btn {
    border-color: #9ca3af;
    color: #4b5563;
}

.filter-btn {
    padding: 0.5rem 1rem;
    border: 2px solid #667eea;
    background: white;
    color: #667eea;
    border-radius: 20px;
    cursor: pointer;
    transition: all 0.3s;
    font-size: 0.9rem;
}

.filter-btn:hover {
    background: #f0f0f0;
}

.filter-btn.active {
    background: #667eea;
    color: white;
}

.search-box {
    margin-top: 1.5rem;
}

.search-box input {
    width: 100%;
    padding: 0.8rem;
    border: 2px solid #ddd;
    border-radius: 8px;
    font-size: 1rem;
    transition: border-color 0.3s;
}

.search-box input:focus {
    outline: none;
    border-color: #667eea;
}

/* 主内容区域 */
main {
    margin-top: 0;
}

#papers-container {
    margin-top: 1rem;
}

/* 结果信息栏 */
.results-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 1rem;
    padding: 0.8rem;
    background: #f8f9fa;
    border-radius: 8px;
}

#resultsCount {
    font-size: 0.9rem;
    color: #666;
    font-weight: 500;
}

.export-btn {
    padding: 0.5rem 1rem;
    background: #667eea;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    transition: background 0.3s;
}

.export-btn:hover {
    background: #5568d3;
}

/* 论文卡片 */
.paper-card {
    position: relative;
    background: white;
    padding: 1.5rem;
    padding-top: 2.5rem;
    padding-left: 4rem;
    margin-bottom: 1rem;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    transition: transform 0.3s, box-shadow 0.3s;
    display: flex;
    align-items: flex-start;
}

.paper-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}

/* 复选框样式 */
.paper-select {
    position: absolute;
    left: 1.2rem;
    top: 1.5rem;
}

.paper-checkbox {
    width: 20px;
    height: 20px;
    cursor: pointer;
    accent-color: #667eea;
}

.paper-content {
    flex: 1;
}

/* 导出控制按钮 */
.export-controls {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.select-btn {
    padding: 0.5rem 1rem;
    background: white;
    border: 2px solid #667eea;
    color: #667eea;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    transition: all 0.3s;
}

.select-btn:hover {
    background: #667eea;
    color: white;
}

/* Venue 徽章 - 增强对比度和可见性 */
.venue-badge {
    display: inline-block;
    padding: 0.4rem 0.9rem;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: none;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    margin-left: 0.5rem;
    max-width: 600px;
    white-space: normal;
    word-wrap: break-word;
    line-height: 1.4;
}

.badge-neurips {
    background: #6B46C1;
    color: white;
}

.badge-cvpr, .badge-iccv, .badge-eccv {
    background: #E53E3E;
    color: white;
}

.badge-icml, .badge-iclr {
    background: #3182CE;
    color: white;
}

.badge-acl, .badge-emnlp, .badge-naacl {
    background: #38A169;
    color: white;
}

.badge-aaai, .badge-ijcai {
    background: #D69E2E;
    color: white;
}

.badge-published {
    background: #4A5568;
    color: white;
}

.preprint {
    background: #f5f5f5;
    color: #757575;
}

.paper-title {
    font-size: 1.3rem;
    margin-bottom: 0.8rem;
}

.paper-title a {
    color: #333;
    text-decoration: none;
    transition: color 0.3s;
}

.paper-title a:hover {
    color: #667eea;
}

.paper-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 0.8rem;
    font-size: 0.9rem;
    color: #666;
}

.meta-item.venue-conference {
    color: #2e7d32;
    font-weight: 600;
    background: #e8f5e9;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
}

.meta-item.venue-preprint {
    color: #666;
}

.paper-authors {
    margin-bottom: 0.8rem;
    color: #555;
    font-size: 0.95rem;
}

.paper-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1rem;
}

.paper-keywords {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1rem;
    align-items: center;
}

/* ========== 新增：关键词标签标题样式 ========== */
.keyword-label {
    font-size: 0.85rem;
    color: #666;
    font-weight: 600;
    min-width: 80px;
}

/* ========== 新增：官方/自定义关键词区域样式 ========== */
.official-keywords, .custom-keywords {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.8rem;
    align-items: center;
}

/* 基础标签样式 */
.tag {
    display: inline-block;
    padding: 0.3rem 0.8rem;
    background: #e3f2fd;
    color: #1976d2;
    border-radius: 15px;
    font-size: 0.85rem;
}

/* 原有关键词标签样式 */
.tag.keyword {
    background: #f3e5f5;
    color: #6a1b9a;
}

/* ========== 新增：官方关键词标签样式 ========== */
.tag.tag-official {
    background: #fef2f2 !important;
    color: #dc2626 !important;
    border: 1px solid #fecdd3;
}

/* ========== 新增：自定义关键词标签样式 ========== */
.tag.tag-custom {
    background: #e3f2fd !important;
    color: #1976d2 !important;
    border: 1px solid #bbdefb;
}

.paper-abstract {
    margin-bottom: 1rem;
}

.paper-abstract details summary {
    cursor: pointer;
    color: #667eea;
    font-weight: 500;
    user-select: none;
}

.paper-abstract details[open] summary {
    margin-bottom: 0.5rem;
}

.paper-abstract p {
    color: #555;
    line-height: 1.8;
    text-align: justify;
}

.paper-links {
    display: flex;
    gap: 1rem;
}

.btn-link {
    padding: 0.5rem 1rem;
    background: #667eea;
    color: white;
    text-decoration: none;
    border-radius: 5px;
    font-size: 0.9rem;
    transition: background 0.3s;
    display: inline-block;
}

.btn-link:hover {
    background: #555;
}

.btn-code {
    background: #28a745;
}

.btn-code:hover {
    background: #218838;
}

.btn-project {
    background: #17a2b8;
}

.btn-project:hover {
    background: #138496;
}

/* 底部 */
footer {
    background: #333;
    color: white;
    text-align: center;
    padding: 2rem 0;
    margin-top: 3rem;
}

footer a {
    color: #667eea;
    text-decoration: none;
}

/* 无结果提示 */
.no-results {
    text-align: center;
    padding: 3rem;
    color: #999;
    font-size: 1.1rem;
}

/* 加载指示器 */
.loading-indicator {
    text-align: center;
    padding: 2rem;
    color: #667eea;
    font-size: 1rem;
    font-weight: 500;
}

.loading-indicator::after {
    content: '';
    display: inline-block;
    width: 20px;
    height: 20px;
    margin-left: 10px;
    border: 3px solid #667eea;
    border-radius: 50%;
    border-top-color: transparent;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* 响应式设计 */
@media (max-width: 768px) {
    header h1 {
        font-size: 2rem;
    }
    
    .filters {
        justify-content: center;
    }
    
    .paper-meta {
        flex-direction: column;
        gap: 0.3rem;
    }

    /* 响应式：关键词区域适配 */
    .keyword-label {
        min-width: auto;
        margin-bottom: 0.2rem;
    }

    .official-keywords, .custom-keywords {
        flex-direction: column;
        align-items: flex-start;
    }
}
"""
        css_dir = self.output_dir / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        with open(css_dir / "style.css", 'w', encoding='utf-8') as f:
            f.write(css)
        logger.info("生成 CSS 样式文件（包含关键词区分样式）")
    
    def generate_js(self):
        """生成 JavaScript 文件（包含重要程度排序逻辑）"""
        js = f"""// 筛选、搜索、排序和懒加载功能
document.addEventListener('DOMContentLoaded', function() {{
    console.log('JavaScript loaded');
    
    // 获取DOM元素
    const monthBtns = document.querySelectorAll('.month-btn');
    const statusBtns = document.querySelectorAll('.status-btn');
    const pdfBtns = document.querySelectorAll('.pdf-btn');
    let categoryBtns = document.querySelectorAll('.category-btn');
    const categoryFilters = document.querySelector('.category-filters');
    const sortBtns = document.querySelectorAll('.sort-btn');
    const searchInput = document.getElementById('searchInput');
    const exportBtn = document.getElementById('exportBtn');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const clearAllBtn = document.getElementById('clearAllBtn');
    const selectedCount = document.getElementById('selectedCount');
    const resultsCount = document.getElementById('resultsCount');
    const papersContainer = document.getElementById('papers-container');
    
    console.log('DOM elements:', {{
        monthBtns: monthBtns.length,
        statusBtns: statusBtns.length,
        pdfBtns: pdfBtns.length,
        categoryBtns: categoryBtns.length,
        sortBtns: sortBtns.length,
        searchInput: !!searchInput,
        exportBtn: !!exportBtn,
        selectAllBtn: !!selectAllBtn,
        clearAllBtn: !!clearAllBtn,
        resultsCount: !!resultsCount,
        papersContainer: !!papersContainer
    }});
    
    // 状态变量
    let allPapersData = [];  // 所有论文数据
    let currentMonth = 'all';  // 当前选中的月份
    let currentStatus = 'all';
    let currentPdf = 'all';
    let currentCategory = 'all';
    let currentCategoryParent = '';
    let currentSort = 'date-desc';
    let searchTerm = '';
    let filteredPapers = [];
    let loadedCount = 0;
    const initialBatchSize = 20;  // 第一次加载20个
    const subsequentBatchSize = 10;  // 后续每次加载10个
    let isLoading = false;
    let observer = null;
    let monthsCache = {{}};  // 缓存已加载的月份数据
    let selectedPaperIds = new Set();
    
    // 配置里的分类列表（从Python传入）
    const CATEGORIES = {json.dumps(CATEGORIES)};

    function splitCategory(category) {{
        return category.split('/').map(part => part.trim()).filter(Boolean);
    }}

    function categoryDepth(category) {{
        return category === 'all' ? 0 : splitCategory(category).length;
    }}

    function categoryLabel(category) {{
        if (category === 'all') return '全部';
        const parts = splitCategory(category);
        return parts[parts.length - 1] || category;
    }}

    function parentCategory(category) {{
        const parts = splitCategory(category);
        if (parts.length <= 1) return '';
        return parts.slice(0, -1).join(' / ');
    }}

    function childCategories(parent) {{
        parent = parent === 'all' ? '' : parent;
        const parentDepth = parent ? categoryDepth(parent) : 0;
        return CATEGORIES.filter(category => {{
            if (!parent) return categoryDepth(category) === 1;
            return parentCategory(category) === parent && categoryDepth(category) === parentDepth + 1;
        }});
    }}

    function categoryCount(category) {{
        return allPapersData.filter(paper => {{
            const status = isPreprint(paper) ? 'preprint' : 'published';
            const tags = paper.tags || [];
            const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
            return (currentStatus === 'all' || status === currentStatus) && matchPdf && tags.includes(category);
        }}).length;
    }}

    function renderCategoryNav() {{
        if (!categoryFilters) return;
        const visibleCategories = childCategories(currentCategory);
        const currentLabel = currentCategory === 'all' ? '全部领域' : categoryLabel(currentCategory);
        const backTarget = currentCategory === 'all' ? '' : parentCategory(currentCategory) || 'all';
        const currentCount = currentCategory === 'all'
            ? allPapersData.filter(paper => {{
                const status = isPreprint(paper) ? 'preprint' : 'published';
                const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
                return (currentStatus === 'all' || status === currentStatus) && matchPdf;
            }}).length
            : categoryCount(currentCategory);

        let html = `<div class="category-breadcrumb">`;
        if (currentCategory !== 'all') {{
            html += `<button class="filter-btn category-back-btn" data-category-back="${{escapeAttribute(backTarget)}}">返回上一级</button>`;
        }}
        html += `<button class="filter-btn category-btn active" data-category="${{escapeAttribute(currentCategory)}}">${{escapeHTML(currentLabel)}} (${{currentCount}})</button>`;
        html += `</div>`;

        if (visibleCategories.length > 0) {{
            html += `<div class="category-children">`;
            visibleCategories.forEach(category => {{
                html += `<button class="filter-btn category-btn" data-category="${{escapeAttribute(category)}}">${{escapeHTML(categoryLabel(category))}} (${{categoryCount(category)}})</button>`;
            }});
            html += `</div>`;
        }}

        categoryFilters.innerHTML = html;
        categoryBtns = document.querySelectorAll('.category-btn');
    }}

    function escapeHTML(value) {{
        return String(value ?? '').replace(/[&<>"']/g, char => ({{
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }}[char]));
    }}

    function escapeAttribute(value) {{
        return escapeHTML(value).replace(/`/g, '&#96;');
    }}

    function safeURL(value, fallback = '#') {{
        try {{
            const url = new URL(String(value || ''), window.location.href);
            return ['http:', 'https:'].includes(url.protocol) ? url.href : fallback;
        }} catch (e) {{
            return fallback;
        }}
    }}

    function escapeBibTeX(value) {{
        const backslash = String.fromCharCode(92);
        const text = String(value ?? '').trim();
        let escaped = '';
        for (const char of text) {{
            escaped += ['{{', '}}', backslash].includes(char) ? backslash + char : char;
        }}
        return escaped.split(/\s+/).join(' ');
    }}

    function isPreprint(paper) {{
        return paper.is_preprint === true || paper.publication_type === 'preprint' || (!paper.venue && !paper.conference);
    }}

    function hasPDF(paper) {{
        return Boolean(paper.pdf_url || paper.preprint_pdf_url || paper.arxiv_id);
    }}

    function sourceLabel(source, paper = {{}}) {{
        if (source === 'semantic_scholar') return 'Semantic Scholar';
        if (source === 'arxiv') return 'arXiv';
        if (paper.semantic_scholar_id || paper.doi || String(paper.paper_url || '').includes('semanticscholar.org')) return 'Semantic Scholar';
        if (paper.arxiv_id || String(paper.arxiv_url || paper.paper_url || '').includes('arxiv.org')) return 'arXiv';
        return source ? String(source) : 'Literature';
    }}

    function publicationTypeLabel(type, preprint) {{
        if (preprint) return 'Preprint';
        if (type === 'journal') return 'Journal';
        if (type === 'conference') return 'Conference';
        return 'Published';
    }}
    
    // 加载月份索引
    async function loadMonthsIndex() {{
        try {{
            const response = await fetch('data/index.json');
            const monthsIndex = await response.json();
            console.log('Months index loaded:', monthsIndex);
            
            // 默认加载最新月份的数据
            if (monthsIndex.length > 0) {{
                await loadMonthData('all');
            }}
        }} catch (e) {{
            console.error('Failed to load months index:', e);
        }}
    }}
    
    // 加载指定月份的数据
    async function loadMonthData(month) {{
        if (month === 'all') {{
            // 加载所有月份
            try {{
                const response = await fetch('data/index.json');
                const monthsIndex = await response.json();
                
                // 加载所有月份数据
                allPapersData = [];
                for (const monthInfo of monthsIndex) {{
                    if (!monthsCache[monthInfo.month]) {{
                        const monthResponse = await fetch(`data/${{monthInfo.month}}.json`);
                        monthsCache[monthInfo.month] = await monthResponse.json();
                    }}
                    allPapersData.push(...monthsCache[monthInfo.month]);
                }}
                console.log(`Loaded all months, total ${{allPapersData.length}} papers`);
            }} catch (e) {{
                console.error('Failed to load all months data:', e);
            }}
        }} else {{
            // 加载单个月份
            if (!monthsCache[month]) {{
                try {{
                    const response = await fetch(`data/${{month}}.json`);
                    monthsCache[month] = await response.json();
                    console.log(`Loaded month ${{month}}, ${{monthsCache[month].length}} papers`);
                }} catch (e) {{
                    console.error(`Failed to load month ${{month}}:`, e);
                    return;
                }}
            }}
            allPapersData = monthsCache[month];
            console.log(`Using cached data for ${{month}}, ${{allPapersData.length}} papers`);
        }}
        
        // 数据加载完成后，触发筛选
        filterAndSortPapers();
    }}
    
    // 生成论文HTML（包含引用数/影响因子渲染）
    function createPaperHTML(paper) {{
        const paperId = String(paper.id || '');
        const escapedId = escapeAttribute(paperId);
        const title = escapeHTML(paper.title);
        const authors = escapeHTML(paper.authors);
        const abstract = escapeHTML(paper.abstract);
        const published = escapeHTML(paper.published);
        const tags = paper.tags ? paper.tags.map(tag => `<span class="tag">${{escapeHTML(categoryLabel(tag))}}</span>`).join('') : '';
        const keywords = paper.keywords ? paper.keywords.map(kw => `<span class="tag keyword">${{escapeHTML(kw)}}</span>`).join('') : '';
        const checked = selectedPaperIds.has(paperId) ? 'checked' : '';
        const paperURL = safeURL(paper.paper_url || paper.arxiv_url, paperId ? `https://arxiv.org/abs/${{encodeURIComponent(paperId)}}` : '#');
        const keywordsSection = keywords ? `<div class="paper-keywords"><span class="keyword-label">关键词：</span>${{keywords}}</div>` : '';
        const preprint = isPreprint(paper);
        const status = preprint ? 'preprint' : 'published';
        const venue = paper.venue || paper.conference || '';
        const publicationType = publicationTypeLabel(paper.publication_type, preprint);
        const sourceBadge = `<span class="meta-item">${{escapeHTML(sourceLabel(paper.source, paper))}}</span>`;
        const typeBadge = `<span class="meta-item">${{escapeHTML(publicationType)}}</span>`;
        const doiLink = paper.doi ? `<a href="${{escapeAttribute(safeURL(`https://doi.org/${{paper.doi}}`))}}" target="_blank" rel="noopener noreferrer" class="code-link">DOI</a>` : '';
        const sourcePageLink = paper.paper_url ? `<a href="${{escapeAttribute(safeURL(paper.paper_url))}}" target="_blank" rel="noopener noreferrer" class="code-link">${{escapeHTML(sourceLabel(paper.source, paper))}}</a>` : '';
        const arxivLink = paper.arxiv_url ? `<a href="${{escapeAttribute(safeURL(paper.arxiv_url))}}" target="_blank" rel="noopener noreferrer" class="code-link">arXiv</a>` : '';
        const pdfLink = paper.pdf_url ? `<a href="${{escapeAttribute(safeURL(paper.pdf_url))}}" target="_blank" rel="noopener noreferrer" class="code-link">PDF</a>` : '';
        const preprintPdfLink = paper.preprint_pdf_url ? `<a href="${{escapeAttribute(safeURL(paper.preprint_pdf_url))}}" target="_blank" rel="noopener noreferrer" class="code-link">Preprint PDF</a>` : '';
        
        // 提取代码链接
        let codeLink = '';
        if (paper.code_link) {{
            codeLink = `<a href="${{paper.code_link}}" target="_blank" class="code-link">📄 Code/Project</a>`;
        }}
        
        // 获取会议徽章
        if (paper.code_link) {{
            codeLink = `<a href="${{escapeAttribute(safeURL(paper.code_link))}}" target="_blank" rel="noopener noreferrer" class="code-link">Code/Project</a>`;
        }}

        let venueBadge = '';
        if (venue) {{
            const badgeInfo = getVenueBadge(venue);
            if (badgeInfo) {{
                venueBadge = `<span class="venue-badge ${{badgeInfo.class}}">${{escapeHTML(badgeInfo.text)}}</span>`;
            }}
        }}
        
        // 新增：渲染引用数和影响因子
        const citationText = paper.citation_count ? `📊 引用数: ${{paper.citation_count}}` : "📊 引用数: 暂无";
        const impactText = paper.impact_factor ? `🌟 影响因子: ${{paper.impact_factor}}` : "🌟 影响因子: 暂无";
        
        const safeCitationText = paper.citation_count ? `引用数: ${{escapeHTML(paper.citation_count)}}` : "引用数: 暂无";
        const safeImpactText = paper.impact_factor ? `推荐分: ${{escapeHTML(paper.impact_factor)}}` : "推荐分: 暂无";
        const firstCategory = paper.categories && paper.categories.length > 0 ? paper.categories[0] : '';
        
        return `
            <article class="paper-card" data-date="${{published}}" data-status="${{status}}" data-tags="${{paper.tags ? escapeAttribute(paper.tags.join(',')) : ''}}" data-paper-id="${{escapedId}}">
                <div class="paper-select">
                    <input type="checkbox" class="paper-checkbox" id="check-${{escapedId}}" data-paper-id="${{escapedId}}" ${{checked}}>
                    <label for="check-${{escapedId}}"></label>
                </div>
                <div class="paper-content">
                    <h2 class="paper-title">
                        <a href="${{escapeAttribute(paperURL)}}" target="_blank" rel="noopener noreferrer">${{title}}</a>
                    </h2>
                    <div class="paper-meta">
                        <span class="meta-item">${{published}}</span>
                        ${{sourceBadge}}
                        ${{typeBadge}}
                        ${{venueBadge}}
                        <span class="meta-item">${{safeCitationText}}</span>
                        <span class="meta-item">${{safeImpactText}}</span>
                        ${{sourcePageLink}}
                        ${{doiLink}}
                        ${{arxivLink}}
                        ${{pdfLink}}
                        ${{preprintPdfLink}}
                        ${{codeLink}}
                    </div>
                    <div class="paper-authors">
                        ${{authors}}
                    </div>
                    <div class="paper-tags">
                        ${{tags}}
                    </div>
                    ${{keywordsSection}}
                    <div class="paper-abstract">
                        <details>
                            <summary>查看摘要</summary>
                            <p>${{abstract}}</p>
                        </details>
                    </div>
                </div>
            </article>
        `;
    }}
    
    // 获取会议徽章信息
    function getVenueBadge(conference) {{
        if (!conference) return null;
        
        const conferenceUpper = conference.toUpperCase();
        let badgeClass = 'badge-published';
        
        if (conferenceUpper.includes('NEURIPS')) {{
            badgeClass = 'badge-neurips';
        }} else if (conferenceUpper.includes('ICLR')) {{
            badgeClass = 'badge-iclr';
        }} else if (conferenceUpper.includes('ICML')) {{
            badgeClass = 'badge-icml';
        }} else if (conferenceUpper.includes('CVPR')) {{
            badgeClass = 'badge-cvpr';
        }} else if (conferenceUpper.includes('ICCV')) {{
            badgeClass = 'badge-iccv';
        }} else if (conferenceUpper.includes('ECCV')) {{
            badgeClass = 'badge-eccv';
        }} else if (conferenceUpper.includes('ACL')) {{
            badgeClass = 'badge-acl';
        }} else if (conferenceUpper.includes('EMNLP')) {{
            badgeClass = 'badge-emnlp';
        }} else if (conferenceUpper.includes('NAACL')) {{
            badgeClass = 'badge-naacl';
        }} else if (conferenceUpper.includes('AAAI')) {{
            badgeClass = 'badge-aaai';
        }} else if (conferenceUpper.includes('IJCAI')) {{
            badgeClass = 'badge-ijcai';
        }}
        
        return {{ class: badgeClass, text: conference }};
    }}
    
    // 更新发表状态按钮的数量
    function updateStatusButtonCounts() {{
        const categoryFilteredPapers = allPapersData.filter(paper => {{
            const tags = paper.tags || [];
            const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
            const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
            return matchCategory && matchPdf;
        }});

        let publishedCount = 0;
        let preprintCount = 0;
        categoryFilteredPapers.forEach(paper => {{
            if (!isPreprint(paper)) {{
                publishedCount++;
            }} else {{
                preprintCount++;
            }}
        }});

        statusBtns.forEach(btn => {{
            const status = btn.dataset.status;
            if (status === 'all') {{
                btn.textContent = `全部 (${{categoryFilteredPapers.length}})`;
            }} else if (status === 'published') {{
                btn.textContent = `已发表 (${{publishedCount}})`;
            }} else if (status === 'preprint') {{
                btn.textContent = `预印本 (${{preprintCount}})`;
            }}
        }});
    }}

    // 更新研究领域按钮的数量
    function updateCategoryButtonCounts() {{
        renderCategoryNav();
        return;
        const statusFilteredPapers = allPapersData.filter(paper => {{
            const status = isPreprint(paper) ? 'preprint' : 'published';
            return currentStatus === 'all' || status === currentStatus;
        }});
        
        const categoryCounts = {{ 'all': statusFilteredPapers.length }};
        CATEGORIES.forEach(category => {{
            categoryCounts[category] = 0;
        }});
        
        statusFilteredPapers.forEach(paper => {{
            const tags = paper.tags || [];
            tags.forEach(tag => {{
                if (categoryCounts.hasOwnProperty(tag)) {{
                    categoryCounts[tag]++;
                }}
            }});
        }});
        
        categoryBtns.forEach(btn => {{
            const category = btn.dataset.category;
            const displayName = category === 'all' ? '全部' : 
                               category.replace("Natural Language Processing", "NLP");
            const count = categoryCounts[category] || 0;
            btn.textContent = `${{displayName}} (${{count}})`;
        }});
    }}
    
    // 筛选和排序论文（包含重要程度排序）
    function filterAndSortPapers() {{
        console.log('Filtering papers:', {{ currentStatus, currentPdf, currentCategory, searchTerm, currentSort }});
        
        // 筛选
        filteredPapers = allPapersData.filter(paper => {{
            const status = isPreprint(paper) ? 'preprint' : 'published';
            const tags = paper.tags || [];
            const text = `${{paper.title}} ${{paper.authors}} ${{paper.abstract}}`.toLowerCase();
            
            const matchStatus = currentStatus === 'all' || status === currentStatus;
            const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
            const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
            const matchSearch = searchTerm === '' || text.includes(searchTerm);
            
            return matchStatus && matchPdf && matchCategory && matchSearch;
        }});
        
        console.log(`Filtered to ${{filteredPapers.length}} papers`);
        
        // 排序（新增重要程度排序）
        filteredPapers.sort((a, b) => {{
            const dateA = new Date(a.published);
            const dateB = new Date(b.published);
            
            if (currentSort === 'date-desc') {{
                return dateB - dateA;
            }} else if (currentSort === 'date-asc') {{
                return dateA - dateB;
            }} else if (currentSort === 'importance-desc') {{
                // 重要程度：先按影响因子降序，再按引用数降序
                const impactA = a.impact_factor || 0;
                const impactB = b.impact_factor || 0;
                if (impactA !== impactB) {{
                    return impactB - impactA;
                }}
                const citeA = a.citation_count || 0;
                const citeB = b.citation_count || 0;
                return citeB - citeA;
            }}
            return 0;
        }});
        
        // 更新按钮数量和显示
        updateStatusButtonCounts();
        updatePDFButtonCounts();
        updateCategoryButtonCounts();
        if (resultsCount) {{
            resultsCount.textContent = `显示 ${{filteredPapers.length}} 篇论文`;
        }}
        
        // 重置懒加载
        loadedCount = 0;
        if (papersContainer) {{
            papersContainer.innerHTML = '';
        }}
        if (observer) {{
            observer.disconnect();
        }}
        
        // 加载第一批
        loadMorePapers();
    }}
    
    // 加载更多论文
    function loadMorePapers() {{
        if (isLoading || loadedCount >= filteredPapers.length) {{
            console.log('Skip loading:', {{ isLoading, loadedCount, total: filteredPapers.length }});
            return;
        }}
        
        isLoading = true;
        const batchSize = loadedCount === 0 ? initialBatchSize : subsequentBatchSize;
        const endIndex = Math.min(loadedCount + batchSize, filteredPapers.length);
        const fragment = document.createDocumentFragment();
        
        for (let i = loadedCount; i < endIndex; i++) {{
            const paperHTML = createPaperHTML(filteredPapers[i]);
            const temp = document.createElement('div');
            temp.innerHTML = paperHTML;
            fragment.appendChild(temp.firstElementChild);
        }}
        
        // 移除旧加载指示器
        const oldIndicator = document.getElementById('loading-indicator');
        if (oldIndicator) {{
            oldIndicator.remove();
        }}
        
        papersContainer.appendChild(fragment);
        loadedCount = endIndex;
        isLoading = false;
        
        // 设置加载触发器
        if (loadedCount < filteredPapers.length) {{
            setupLoadTrigger();
        }}
    }}
    
    // 设置加载触发器
    function setupLoadTrigger() {{
        let indicator = document.getElementById('loading-indicator');
        if (!indicator) {{
            indicator = document.createElement('div');
            indicator.id = 'loading-indicator';
            indicator.className = 'loading-indicator';
            indicator.style.height = '100px';
            indicator.style.margin = '20px 0';
            indicator.style.textAlign = 'center';
            indicator.style.color = '#666';
            indicator.textContent = '加载更多...';
            papersContainer.appendChild(indicator);
        }}
        
        if (observer) {{
            observer.disconnect();
        }}
        
        observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    loadMorePapers();
                }}
            }});
        }}, {{ rootMargin: '200px' }});
        
        observer.observe(indicator);
    }}
    
    // 绑定事件
    monthBtns.forEach(btn => {{
        btn.addEventListener('click', async function() {{
            monthBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentMonth = this.dataset.month;
            
            resultsCount.textContent = '加载中...';
            papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';
            
            await loadMonthData(currentMonth);
        }});
    }});
    
    statusBtns.forEach(btn => {{
        btn.addEventListener('click', function() {{
            statusBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentStatus = this.dataset.status;
            filterAndSortPapers();
        }});
    }});

    pdfBtns.forEach(btn => {{
        btn.addEventListener('click', function() {{
            pdfBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentPdf = this.dataset.pdf;
            filterAndSortPapers();
        }});
    }});
    
    categoryBtns.forEach(btn => {{
        btn.addEventListener('click', function() {{
            categoryBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentCategory = this.dataset.category;
            filterAndSortPapers();
        }});
    }});

    if (categoryFilters) {{
        categoryFilters.addEventListener('click', function(e) {{
            const backButton = e.target.closest('[data-category-back]');
            const categoryButton = e.target.closest('.category-btn');

            if (backButton) {{
                currentCategory = backButton.dataset.categoryBack || 'all';
                filterAndSortPapers();
                return;
            }}

            if (categoryButton) {{
                currentCategory = categoryButton.dataset.category || 'all';
                filterAndSortPapers();
            }}
        }});
    }}

    function updatePDFButtonCounts() {{
        const statusCategoryFilteredPapers = allPapersData.filter(paper => {{
            const status = isPreprint(paper) ? 'preprint' : 'published';
            const tags = paper.tags || [];
            const matchStatus = currentStatus === 'all' || status === currentStatus;
            const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
            return matchStatus && matchCategory;
        }});

        const availableCount = statusCategoryFilteredPapers.filter(hasPDF).length;
        const missingCount = statusCategoryFilteredPapers.length - availableCount;

        pdfBtns.forEach(btn => {{
            const pdf = btn.dataset.pdf;
            if (pdf === 'all') {{
                btn.textContent = `全部 (${{statusCategoryFilteredPapers.length}})`;
            }} else if (pdf === 'available') {{
                btn.textContent = `有PDF (${{availableCount}})`;
            }} else if (pdf === 'missing') {{
                btn.textContent = `无PDF (${{missingCount}})`;
            }}
        }});
    }}
    
    sortBtns.forEach(btn => {{
        btn.addEventListener('click', function(e) {{
            e.preventDefault();
            sortBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentSort = this.dataset.sort;
            filterAndSortPapers();
        }});
    }});
    
    if (searchInput) {{
        searchInput.addEventListener('input', function() {{
            searchTerm = this.value.toLowerCase();
            filterAndSortPapers();
        }});
    }}
    
    // 更新选中数量
    function updateSelectedCount() {{
        if (selectedCount) {{
            selectedCount.textContent = selectedPaperIds.size;
        }}
    }}
    
    if (papersContainer) {{
        papersContainer.addEventListener('change', function(e) {{
            if (e.target.classList.contains('paper-checkbox')) {{
                if (e.target.checked) {{
                    selectedPaperIds.add(e.target.dataset.paperId);
                }} else {{
                    selectedPaperIds.delete(e.target.dataset.paperId);
                }}
                updateSelectedCount();
            }}
        }});
    }}
    
    if (selectAllBtn) {{
        selectAllBtn.addEventListener('click', function() {{
            filteredPapers.forEach(paper => selectedPaperIds.add(String(paper.id || '')));
            document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = true);
            updateSelectedCount();
        }});
    }}
    
    if (clearAllBtn) {{
        clearAllBtn.addEventListener('click', function() {{
            selectedPaperIds.clear();
            document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = false);
            updateSelectedCount();
        }});
    }}
    
    // 导出功能
    if (exportBtn) {{
        exportBtn.addEventListener('click', function(e) {{
            e.preventDefault();
            downloadSelectedPDFs();
        }});
    }}
    
    function getPaperPDFUrl(paper) {{
        if (paper.pdf_url) return safeURL(paper.pdf_url, '');
        if (paper.preprint_pdf_url) return safeURL(paper.preprint_pdf_url, '');
        if (paper.arxiv_id) return safeURL(`https://arxiv.org/pdf/${{paper.arxiv_id}}`, '');
        return '';
    }}

    function sanitizeFilename(value) {{
        return String(value || 'paper')
            .replace(/[\\\\/:*?"<>|]+/g, '_')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, 120) || 'paper';
    }}

    function downloadSelectedPDFs() {{
        if (selectedPaperIds.size === 0) {{
            alert('请至少选择一篇论文下载！');
            return;
        }}
        
        const selectedPapers = allPapersData.filter(paper => selectedPaperIds.has(String(paper.id || '')));
        const missing = [];
        let downloadCount = 0;

        selectedPapers.forEach((paper, index) => {{
            const pdfUrl = getPaperPDFUrl(paper);
            if (!pdfUrl) {{
                missing.push(paper.title || paper.id || `paper ${{index + 1}}`);
                return;
            }}

            const link = document.createElement('a');
            link.href = pdfUrl;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.download = `${{sanitizeFilename(paper.title || paper.id || `paper_${{index + 1}}`)}}.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            downloadCount += 1;
        }});

        if (missing.length > 0) {{
            alert(`已尝试下载 ${{downloadCount}} 个 PDF；${{missing.length}} 篇没有可用 PDF 链接。`);
        }}
    }}
    
    function downloadFile(content, filename, contentType) {{
        const blob = new Blob([content], {{ type: contentType }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }}
    
    // 初始化
    console.log('Initializing...');
    loadMonthsIndex();
}});
"""
        
        js_dir = self.output_dir / "js"
        js_dir.mkdir(parents=True, exist_ok=True)
        
        with open(js_dir / "main.js", 'w', encoding='utf-8') as f:
            f.write(js)
        
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
