import requests
import yaml
import arxiv
import json
import os
import re  # 新增：正则匹配官方关键词
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging

# 配置日志（方便查看抓取过程）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PaperFetcher:
    # 常见期刊/会议影响因子静态表（可自行扩充）
    IMPACT_FACTOR_TABLE = {
        # 期刊
        'Nature': 64.8,
        'Science': 63.8,
        'PAMI': 24.3,
        'JMLR': 6.8,
        'TPAMI': 24.3,
        'IJCV': 19.5,
        'Journal of Computational Physics': 5.6,
        'Computers & Fluids': 3.7,
        'Journal of Fluid Mechanics': 4.0,
        'AIAA Journal': 2.2,
        'International Journal for Numerical Methods in Fluids': 2.1,
        'Physics of Fluids': 3.5,
        'Computational Mechanics': 3.2,
        'Journal of Machine Learning for Science and Technology': 2.5,

        # 会议（无官方IF，给排序参考分值）
        'NeurIPS': 14.0,
        'ICML': 12.0,
        'ICLR': 10.0,
        'CVPR': 11.2,
        'ICCV': 10.5,
        'ECCV': 8.5,
        'ACL': 7.1,
        'EMNLP': 6.2,
        'NAACL': 5.5,
        'AAAI': 7.7,
        'IJCAI': 5.6,
        'KDD': 6.9,
        'IROS': 4.7,
        'ICRA': 4.3,
        'AIAA SciTech Forum': 3.0,
        'ASME Fluids Engineering Division Meeting': 2.5,
        'International Conference on Computational Fluid Dynamics': 3.5,
        'International Conference on Numerical Methods in Fluid Dynamics': 3.0,
        'International Symposium on Turbulence and Shear Flow Phenomena': 3.0,
        'Conference on Machine Learning for Fluid Dynamics': 4.0,
        'International Conference on Computational Mechanics': 3.0,
        'European Conference on Computational Fluid Dynamics': 3.0,
    }

    # ========== 修正缩进：__init__ 必须是类的成员方法 ==========
    def __init__(self, config_path: str = "config.yaml"):
        """初始化：读取你的自定义yaml配置"""
        self.config = self._load_config(config_path)  # 关键：赋值self.config
        self.arxiv_client = arxiv.Client()  # ArXiv客户端

    def _load_config(self, config_path: str) -> Dict:
        """加载你的yaml配置，确保结构匹配"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在：{config_path}，请确认文件路径正确")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f"成功加载你的配置文件：{config_path}")
            return config
        except Exception as e:
            raise ValueError(f"配置文件解析失败：{e}")

    def get_impact_factor(self, paper):
        """根据会议/期刊名获取影响因子"""
        # 优先用 conference 字段，否则用 categories/venue
        name = paper.get('conference') or paper.get('venue')
        if not name:
            # 尝试从 categories 里找
            cats = paper.get('categories', [])
            for cat in cats:
                if cat in self.IMPACT_FACTOR_TABLE:
                    return self.IMPACT_FACTOR_TABLE[cat]
            return None
        # 标准化名称
        for k in self.IMPACT_FACTOR_TABLE:
            if k.lower() in name.lower():
                return self.IMPACT_FACTOR_TABLE[k]
        return None

    def get_citation_count(self, title, authors=None, year=None):
        """通过 Semantic Scholar API 获取引用次数"""
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": title,
            "fields": "title,authors,year,citationCount",
            "limit": 1
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 1000:
                data = resp.json()
                if data.get("data"):
                    paper = data["data"][0]
                    # 可选：进一步比对作者/年份
                    return paper.get("citationCount", 0)
        except Exception as e:
            logger.warning(f"Semantic Scholar API 查询失败: {e}")
        return None

    # ========== 关键新增：提取论文的官方关键词 ==========
    def extract_official_keywords(self, result: arxiv.Result) -> List[str]:
        """
        提取论文标注的「官方关键词」（从摘要/评论中匹配 Keywords: xxx 格式）
        匹配规则：支持 Keywords/Key words/关键词 等中英文标注格式
        """
        official_kw = []
        # 拼接可能包含关键词的文本：摘要 + 评论（ArXiv论文的comment字段可能包含期刊/关键词标注）
        text_parts = [
            result.summary.replace("\n", " ").strip(),  # 摘要
            result.comment if result.comment else ""    # 评论字段
        ]
        full_text = " ".join(text_parts).lower()

        # 正则匹配：匹配 "Keywords: xxx,xxx" 或 "Key words: xxx" 或 "关键词：xxx" 等格式
        kw_pattern = r'(?:key\s*words?|关键词)\s*:\s*([^.;\n]+)'
        matches = re.findall(kw_pattern, full_text, re.IGNORECASE)

        if matches:
            # 拆分关键词、去重、清理空格
            for match in matches:
                keywords = re.split(r'[,;]', match)
                keywords = [kw.strip() for kw in keywords if kw.strip()]
                official_kw.extend(keywords)

        # 最终处理：去重 + 转小写（统一格式）
        official_kw = list(set([kw.lower() for kw in official_kw]))
        return official_kw

    def extract_paper_keywords(self, paper: Dict) -> List[str]:
        """
        提取「自定义预设关键词」（原有逻辑，仅做注释优化）
        """
        # 拼接标题+摘要，转小写（统一匹配）
        text = (paper["title"] + " " + paper["abstract"]).lower()
        all_keywords = []
        
        # 收集你yaml中所有分类的关键词（包含新增的中英文）
        categories = self.config.get("categories", {})  # 现在self.config已正确初始化
        for cat_info in categories.values():
            all_keywords.extend([kw.lower() for kw in cat_info.get("keywords", [])])
        
        # 提取文本中存在的关键词（去重）
        extracted = list({kw for kw in all_keywords if kw in text})
        
        # 补充新增的高频核心关键词（兼容你的yaml扩充）
        core_keywords = [
            # 流体新增
            "计算流体力学", "数值模拟", "数值计算", "物理信息神经网络", "代理模型", "rom",
            # ML新增
            "深度学习", "神经网络", "强化学习", "迁移学习", "监督学习", "无监督学习",
            # 基础核心
            "cfd", "fluid dynamics", "turbulence", "aerodynamics", "multiphase flow",
            "machine learning", "deep learning", "pinn", "neural network"
        ]
        for kw in core_keywords:
            if kw.lower() in text and kw.lower() not in extracted:
                extracted.append(kw.lower())
        
        # 最多保留10个关键词（适配新增词汇，多保留2个）
        return extracted[:10]

    def classify_paper(self, paper: Dict) -> List[str]:
        """
        修复版分类逻辑：确保满足关键词的论文一定打上对应标签，解决点击数量变0问题
        """
        tags = set()
        text = (paper["title"] + " " + paper["abstract"]).lower()
        categories = self.config.get("categories", {})  # self.config已正确初始化
        
        # ========== 核心修改：扩充关键词池，兼容你的新增词汇 ==========
        fluid_keywords_pool = [
            # 原有流体关键词
            "cfd", "fluid dynamics", "turbulence", "aerodynamics", "multiphase flow",
            "流体力学", "空气动力学", "多相流", "湍流", "流动模拟",
            # 新增流体关键词（yaml里的）
            "计算流体力学", "数值模拟", "数值计算", "flow modeling", "flow computation"
        ]
        ml_keywords_pool = [
            # 原有ML关键词
            "machine learning", "deep learning", "neural network", "pinn", "data-driven",
            "智能流体力学", "机器学习", "深度学习",
            # 新增ML关键词（yaml里的）
            "神经网络", "强化学习", "迁移学习", "监督学习", "无监督学习",
            "物理信息神经网络", "代理模型", "reduced-order model", "rom",
            "cnn", "rnn", "gan", "data-driven modeling", "surrogate model"
        ]
        
        # 检查是否含流体/ML关键词（兼容新增词汇）
        has_fluid = any(kw.lower() in text for kw in fluid_keywords_pool)
        has_ml = any(kw.lower() in text for kw in ml_keywords_pool)
        
        # ========== 关键修复：遍历分类时，只要含该分类关键词就强制打标 ==========
        for category_name, category_info in categories.items():
            keywords = [kw.lower() for kw in category_info.get("keywords", [])]
            has_category_kw = any(kw in text for kw in keywords)
            
            # 1. CFD与机器学习交叉：必须同时包含流体+ML关键词
            if category_name == "CFD与机器学习交叉":
                if has_fluid and has_ml:
                    tags.add(category_name)
            
            # 2. 智能流体力学：含关键词即可打标
            elif category_name == "智能流体力学":
                if has_category_kw:
                    tags.add(category_name)
            
            # 3. 纯流体领域：只要含该分类关键词 → 强制打标
            elif category_name in ["多相流", "空气动力学", "流体力学"]:
                if has_category_kw:
                    tags.add(category_name)
            
            # 4. 机器学习：含关键词即可打标
            elif category_name == "机器学习":
                if has_category_kw:
                    tags.add(category_name)
        
        # ========== 终极兜底：避免漏标（核心修复点） ==========
        # 1. 只要含流体关键词，至少打“流体力学”标签
        if has_fluid and "流体力学" not in tags:
            tags.add("流体力学")
        # 2. 不再自动补打“CFD与机器学习交叉”，避免全部都落入该类
        # 3. 含智能流体关键词但未打标 → 补充打标
        if "智能流体力学" in text and "智能流体力学" not in tags:
            tags.add("智能流体力学")
        # 4. 含多相流/空气动力学关键词但未打标 → 补充打标
        if "多相流" in text or "multiphase flow" in text:
            tags.add("多相流")
        if "空气动力学" in text or "aerodynamics" in text:
            tags.add("空气动力学")
        
        return list(tags)

    def fetch_arxiv_papers(self) -> List[Dict]:
        """
        严格按你的新版yaml配置抓取：指定分类、30天、200篇
        """
        arxiv_config = self.config.get("sources", {}).get("arxiv", {})  # self.config已正确初始化
        if not arxiv_config.get("enabled", False):
            logger.warning("ArXiv数据源已禁用！")
            return []
        
        # 提取你的配置参数
        arxiv_categories = arxiv_config.get("categories", [])
        max_results = arxiv_config.get("max_results", 1000)
        days_back = arxiv_config.get("days_back", 180)
        
        # 构建ArXiv查询（指定分类+扩充的流体/ML关键词）
        query_parts = []
        if arxiv_categories:
            query_parts.extend([f"cat:{cat}" for cat in arxiv_categories])
        # 扩充查询词：只限定流体相关，避免强制包含机器学习
        fluid_kw = "CFD OR fluid dynamics OR 计算流体力学 OR turbulence OR aerodynamics OR multiphase flow"
        query_parts.append(f"({fluid_kw})")
        
        query = " AND ".join(query_parts)
        logger.info(f"ArXiv查询条件（兼容新增关键词）：{query}")
        
        # 时间范围
        start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        start_date_str = start_date.strftime("%Y-%m-%d")
        
        logger.info(f"开始抓取：近{days_back}天，最多{max_results}篇，分类：{arxiv_categories}")
        
        # 构建搜索（arxiv API 不支持 SubmissionDate 过滤，改为本地过滤）
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        papers_high_if = []
        papers_other = []
        for result in self.arxiv_client.results(search):
            published = result.published
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < start_date:
                continue
            
            # ========== 核心修改：构建paper字典时，新增官方/自定义关键词字段 ==========
            paper = {
                "id": result.entry_id.split("/")[-1],
                "title": result.title,
                "authors": ", ".join([author.name for author in result.authors]),
                "abstract": result.summary.replace("\n", " ").strip(),
                "published": published.strftime("%Y-%m-%d"),
                "arxiv_url": result.entry_id,
                "pdf_url": result.pdf_url,
                "categories": result.categories,
                "conference": "",
                "code_link": "",
                "tags": [],
                # 新增字段1：官方关键词（从摘要/评论中提取）
                "official_keywords": self.extract_official_keywords(result),
                # 新增字段2：自定义预设关键词（原有逻辑）
                "custom_keywords": [],
                # 兼容原有keywords字段（合并官方+自定义，去重）
                "keywords": []
            }
            
            if result.comment:
                venues = self.config.get("venues", {})  # self.config已正确初始化
                all_venues = venues.get("conferences", []) + venues.get("journals", [])
                for venue in all_venues:
                    if venue.lower() in result.comment.lower():
                        paper["conference"] = venue
                        break
            
            # 填充分类标签
            paper["tags"] = self.classify_paper(paper)
            # 填充自定义关键词
            paper["custom_keywords"] = self.extract_paper_keywords(paper)
            # 合并官方+自定义关键词，去重（保持原有keywords字段兼容）
            paper["keywords"] = list(set(paper["official_keywords"] + paper["custom_keywords"]))
            
            # 补充引用数和影响因子
            paper["citation_count"] = self.get_citation_count(paper["title"], paper["authors"], published.year)
            paper["impact_factor"] = self.get_impact_factor(paper)
            
            # 按影响因子分类
            if paper["tags"]:
                if paper["impact_factor"] and paper["impact_factor"] >= 3.0:
                    papers_high_if.append(paper)
                else:
                    papers_other.append(paper)
        
        # 优先返回高影响因子文献，数量不足时补充其他
        max_results = arxiv_config.get("max_results", 1000)
        selected = papers_high_if[:max_results]
        if len(selected) < max_results:
            selected += papers_other[:max_results-len(selected)]
        logger.info(f"抓取完成：高影响因子{len(papers_high_if)}篇，其他{len(papers_other)}篇，实际返回{len(selected)}篇")
        return selected

    def save_papers(self):
        output_config = self.config.get("output", {})  # self.config已正确初始化
        data_dir = output_config.get("data_dir", "data")
        os.makedirs(data_dir, exist_ok=True)
        docs_dir = output_config.get("docs_dir", "docs")
        os.makedirs(docs_dir, exist_ok=True)

        # 抓取论文
        papers = self.fetch_arxiv_papers()
        if not papers:
            logger.warning("未抓取到任何相关论文！")
            return

        # ========== 新增：按月份拆分数据（和main.js加载逻辑对齐） ==========
        month_papers = {}
        for paper in papers:
            month = paper["published"].split("-")[0] + "-" + paper["published"].split("-")[1]
            if month not in month_papers:
                month_papers[month] = []
            month_papers[month].append(paper)

        # 生成月份索引文件（data/index.json）
        index_data = [{"month": month, "count": len(papers)} for month, papers in month_papers.items()]
        with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        logger.info(f"月份索引已保存到：{os.path.join(data_dir, 'index.json')}")

        # 保存各月份数据（如data/2026-01.json）—— 已包含official_keywords/custom_keywords
        for month, papers in month_papers.items():
            month_path = os.path.join(data_dir, f"{month}.json")
            with open(month_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            logger.info(f"月份数据已保存到：{month_path}")

        # 同步到docs目录（可选，保留papers.json）—— 同样包含新字段
        with open(os.path.join(docs_dir, "papers.json"), "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

def main():
    """主函数：一键抓取+分类+保存+同步"""
    try:
        fetcher = PaperFetcher()  # 实例化时调用__init__，正确初始化self.config
        fetcher.save_papers()
        logger.info("\n✅ 全部完成！直接打开 docs/index.html 即可查看结果")
    except Exception as e:
        logger.error(f"运行失败：{e}", exc_info=True)

if __name__ == "__main__":
    main()