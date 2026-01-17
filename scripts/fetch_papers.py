import yaml
import arxiv
import json
import os
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
    """ArXiv论文抓取器：适配你的新版yaml，兼容更多中英文关键词"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """初始化：读取你的自定义yaml配置"""
        self.config = self._load_config(config_path)
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

    def extract_paper_keywords(self, paper: Dict) -> List[str]:
        """
        提取核心关键词：自动读取你yaml里的所有中英文关键词，适配新增的词汇
        """
        # 拼接标题+摘要，转小写（统一匹配）
        text = (paper["title"] + " " + paper["abstract"]).lower()
        all_keywords = []
        
        # 收集你yaml中所有分类的关键词（包含新增的中英文）
        categories = self.config.get("categories", {})
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
        categories = self.config.get("categories", {})
        
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
        严格按你的新版yaml配置抓取：指定分类、180天、50篇
        """
        arxiv_config = self.config.get("sources", {}).get("arxiv", {})
        if not arxiv_config.get("enabled", False):
            logger.warning("ArXiv数据源已禁用！")
            return []
        
        # 提取你的配置参数
        arxiv_categories = arxiv_config.get("categories", [])
        max_results = arxiv_config.get("max_results", 50)
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
        
        papers = []
        for result in self.arxiv_client.results(search):
            # 本地时间过滤（仅保留近 N 天）
            published = result.published
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < start_date:
                continue
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
                "keywords": []
            }
            
            # 提取会议信息（匹配你的venues）
            if result.comment:
                venues = self.config.get("venues", {})
                all_venues = venues.get("conferences", []) + venues.get("journals", [])
                for venue in all_venues:
                    if venue.lower() in result.comment.lower():
                        paper["conference"] = venue
                        break
            
            # 分类打标签（修复版逻辑，确保标签不遗漏）
            paper["tags"] = self.classify_paper(paper)
            # 提取核心关键词（包含你新增的）
            paper["keywords"] = self.extract_paper_keywords(paper)
            
            # 仅保留有分类标签的论文
            if paper["tags"]:
                papers.append(paper)
                logger.debug(f"抓取到相关论文：{paper['title'][:50]}...")
        
        logger.info(f"抓取完成：共{len(papers)}篇相关论文（兼容新增关键词）")
        return papers

    def save_papers(self):
        """按你的output配置保存+同步到docs"""
        output_config = self.config.get("output", {})
        data_dir = output_config.get("data_dir", "data")
        os.makedirs(data_dir, exist_ok=True)
        save_path = os.path.join(data_dir, "papers.json")
        
        # 抓取论文
        papers = self.fetch_arxiv_papers()
        if not papers:
            logger.warning("未抓取到任何相关论文！可尝试：\n1. 扩大days_back\n2. 放宽查询关键词")
            return
        
        # 保存JSON
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info(f"论文数据已保存到：{save_path}（共{len(papers)}篇）")
        
        # 同步到docs目录
        docs_dir = output_config.get("docs_dir", "docs")
        os.makedirs(docs_dir, exist_ok=True)
        docs_save_path = os.path.join(docs_dir, "papers.json")
        with open(docs_save_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info(f"论文数据已同步到：{docs_save_path}")

def main():
    """主函数：一键抓取+分类+保存+同步"""
    try:
        fetcher = PaperFetcher()
        fetcher.save_papers()
        logger.info("\n✅ 全部完成！直接打开 docs/index.html 即可查看结果")
    except Exception as e:
        logger.error(f"运行失败：{e}", exc_info=True)

if __name__ == "__main__":
    main()