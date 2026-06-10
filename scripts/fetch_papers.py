import requests
import yaml
import arxiv
import json
import os
import re
import time
import hashlib
import argparse
import calendar
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import logging
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# 配置日志（方便查看抓取过程）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_CASCADE_JSON_CACHE = {}


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
    "porous media",
    "blood flow",
    "heat transfer",
    "combustion",
    "wind turbine",
    "precipitation",
    "reacting flow",
]

FLUID_RELATED_CATEGORIES = {
    "physics.flu-dyn",
    "physics.ao-ph",
}


SUBDOMAIN_RULES = {
    # ===== 智能CFD 子分类（方法优先，ML 论文归入此类） =====

    "流体力学 / 智能CFD / 代理模型与算子学习": {
        "strong": [
            "surrogate model", "surrogate modelling", "surrogate modeling",
            "neural operator", "fourier neural operator", "fno", "deeponet",
            "operator learning", "emulator", "proxy model", "flow field prediction",
            "reduced-order", "reduced order", "rom", "pod", "autoencoder",
            "koopman", "data-driven solver", "end-to-end solver",
            "graph neural network", "gnn", "latent space",
            "field prediction", "flow prediction",
            "reduced-complexity", "variational autoencoder", "cvae",
            "transfer learning", "foundation model",
        ],
        "context": [
            "navier-stokes", "computational fluid dynamics", "cfd",
            "parametric flow", "fluid simulation", "flow simulation",
            "pde solver", "neural network", "deep learning",
            "machine learning", "data-driven", "flow field",
            "spatiotemporal", "flow data",
        ],
        "negative": [
            "language model", "large language model", "recommendation",
            "protein", "molecular", "medical image",
        ],
    },

    "流体力学 / 智能CFD / 湍流建模与闭合": {
        "strong": [
            "turbulence modeling", "turbulence modelling", "turbulent closure",
            "rans closure", "reynolds stress", "eddy viscosity", "les subgrid",
            "subgrid-scale", "sgs model", "wall model", "data-driven turbulence",
            "closure model", "subgrid stress", "turbulence scheme",
            "closure for rans", "subgrid parametrization",
        ],
        "context": [
            "rans", "les", "dns", "turbulent flow", "boundary layer",
            "machine learning", "data-driven", "neural network", "deep learning",
            "cfd", "navier-stokes",
        ],
        "negative": ["language model", "social network"],
    },

    "流体力学 / 智能CFD / 数值方法增强": {
        "strong": [
            "learned numerical scheme", "neural numerical method", "learned discretization",
            "learned flux", "flux limiter", "weno", "differentiable solver",
            "neural solver", "solver-in-the-loop", "stabilization",
            "numerical viscosity", "closure coefficient",
        ],
        "context": [
            "conservation law", "pde", "navier-stokes", "cfd", "shock", "mesh",
            "finite volume", "finite difference",
            "machine learning", "data-driven", "neural network", "deep learning",
        ],
        "negative": ["image classification", "language model"],
    },

    "流体力学 / 智能CFD / 加速求解与超分辨": {
        "strong": [
            "accelerated simulation", "fast cfd", "speedup", "efficient solver",
            "coarse grid", "coarse-grid", "super-resolution", "high-resolution reconstruction",
            "downscaling", "multigrid", "real-time simulation", "flow matching",
        ],
        "context": [
            "cfd", "flow simulation", "navier-stokes", "fluid simulation", "solver",
            "machine learning", "data-driven", "neural network", "deep learning",
        ],
        "negative": ["video super-resolution", "image super-resolution"],
    },

    "流体力学 / 智能CFD / 物理信息神经网络": {
        "strong": [
            "physics-informed neural network", "pinn", "physics-informed",
            "physics-guided neural", "physics-constrained neural",
            "hard constraint projection", "variational pinn", "cpinn",
            "physics-embedded", "physics-encoded",
            "physics-informed machine learning", "residual-guided",
        ],
        "context": [
            "navier-stokes", "cfd", "pde", "fluid", "flow",
            "neural network", "deep learning",
            "machine learning", "data-driven", "flow field",
        ],
        "negative": ["image classification", "materials design"],
    },

    "流体力学 / 智能CFD / 流场重建与数据驱动": {
        "strong": [
            "flow field reconstruction", "uncertainty quantification",
            "data assimilation", "sparse sensor", "sparse measurement",
            "inverse problem", "state estimation", "flow estimation",
            "neural kalman", "ensemble kalman", "sensor placement",
            "field reconstruction", "probabilistic prediction",
            "sparse data", "diffusion model for flow",
        ],
        "context": [
            "navier-stokes", "cfd", "fluid", "flow", "pde",
            "neural network", "machine learning",
            "data-driven", "deep learning", "flow field", "spatiotemporal",
        ],
        "negative": ["image reconstruction", "video"],
    },

    "流体力学 / 智能CFD / 流动控制与强化学习": {
        "strong": [
            "flow control", "active flow control", "reinforcement learning",
            "deep reinforcement learning", "drl",
            "closed-loop control", "optimal control", "active control",
            "drag reduction control",
        ],
        "context": [
            "navier-stokes", "cfd", "fluid", "flow", "turbulent",
            "wake", "boundary layer",
            "machine learning", "data-driven", "neural network", "deep learning",
        ],
        "negative": ["robot", "autonomous driving", "game"],
    },

    # ===== 领域方向（纯传统/非ML论文，ML论文被 negative 排除） =====

    "流体力学 / 气动优化设计": {
        "strong": [
            "aerodynamic optimization", "aerodynamic design optimization",
            "airfoil optimization", "wing optimization", "shape optimization",
            "inverse design", "drag reduction", "lift enhancement",
            "topology optimization", "adjoint optimization", "design optimization",
        ],
        "context": ["airfoil", "wing", "aerodynamics", "drag", "lift", "uav", "aircraft"],
        "negative": [
            "building design", "chip design",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 湍流与流动机理": {
        "strong": [
            "turbulence", "turbulent flow", "isotropic turbulence",
            "convective turbulence", "vortex", "vortices",
            "boundary-layer flow", "flow instability",
            "linear amplification", "resolvent analysis",
            "jet flow", "shear flow", "wake flow", "mixing layer",
        ],
        "context": ["flow", "fluid", "navier-stokes", "physics.flu-dyn"],
        "negative": [
            "language model", "transformer", "photonic", "crystal", "materials design",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 多相流理论": {
        "strong": [
            "multiphase flow", "multiphase flows", "two-phase flow", "two-phase flows",
            "phase separation", "phase field", "interface capturing", "interface tracking",
            "vof", "level set", "lattice boltzmann", "sph", "dem",
            "cavitation", "boiling", "droplet", "bubble", "spray",
        ],
        "context": ["fluid", "flow", "navier-stokes", "cfd"],
        "negative": [
            "semantic segmentation",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 空气动力学理论": {
        "strong": [
            "aerodynamics", "airfoil", "wing aerodynamics", "uav aerodynamics",
            "aircraft aerodynamics", "compressible flow", "hypersonic flow",
            "shock wave", "boundary layer", "aeroelasticity",
            "fluid-structure interaction", "fsi",
        ],
        "context": ["flow", "fluid", "cfd", "navier-stokes"],
        "negative": [
            "wireless", "network traffic",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 环境与地球物理流体": {
        "strong": [
            "weather forecasting", "climate", "precipitation",
            "atmospheric flow", "ocean flow", "ocean circulation",
            "sea ice", "geophysical flow", "environmental fluid",
            "coastal hydrodynamics", "storm", "convective-scale",
            "seasonal forecast", "atmospheric dynamics",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd"],
        "negative": [
            "semiconductor", "electronics", "market",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 生物与医学流体": {
        "strong": [
            "blood flow", "cardiovascular", "aneurysm", "aortic",
            "biomedical flow", "cilia", "cilium", "ciliary",
            "microfluidic", "biolocomotion", "respiratory flow",
            "hemodynamics", "ventricular flow",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd"],
        "negative": [
            "image segmentation", "clinical trial",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 燃烧与传热": {
        "strong": [
            "combustion", "reacting flow", "detonation",
            "fire simulation", "heat transfer", "thermal convection",
            "radiation transfer", "flame", "thermal flow",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd"],
        "negative": [
            "battery thermal", "electronics cooling",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 风能与海洋工程流体": {
        "strong": [
            "wind turbine", "offshore wind", "floating offshore",
            "wake modeling", "wind farm", "floating wind",
            "fatigue loading", "wave-structure", "marine hydrodynamics",
            "ocean energy", "wind energy",
        ],
        "context": ["fluid", "flow", "simulation", "cfd", "turbulent"],
        "negative": [
            "power electronics", "grid connection",
            "machine learning", "neural network", "deep learning",
        ],
    },

    "流体力学 / 计算流体力学方法": {
        "strong": [
            "finite volume method", "finite element method",
            "mesh generation", "adaptive mesh refinement",
            "high-order scheme", "open-source solver",
            "error estimation", "richardson extrapolation",
            "grid convergence", "discretization error",
        ],
        "context": ["cfd", "navier-stokes", "numerical", "computational fluid dynamics"],
        "negative": ["machine learning", "neural network", "deep learning", "surrogate"],
    },
}

PARENT_TAGS = {
    # 智能CFD 子分类（父路径: 流体力学 → 流体力学 / 智能CFD）
    "流体力学 / 智能CFD / 代理模型与算子学习": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 湍流建模与闭合": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 数值方法增强": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 加速求解与超分辨": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 物理信息神经网络": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 流场重建与数据驱动": ["流体力学", "流体力学 / 智能CFD"],
    "流体力学 / 智能CFD / 流动控制与强化学习": ["流体力学", "流体力学 / 智能CFD"],
    # 领域方向（父路径: 流体力学）
    "流体力学 / 气动优化设计": ["流体力学"],
    "流体力学 / 湍流与流动机理": ["流体力学"],
    "流体力学 / 多相流理论": ["流体力学"],
    "流体力学 / 空气动力学理论": ["流体力学"],
    "流体力学 / 环境与地球物理流体": ["流体力学"],
    "流体力学 / 生物与医学流体": ["流体力学"],
    "流体力学 / 燃烧与传热": ["流体力学"],
    "流体力学 / 风能与海洋工程流体": ["流体力学"],
    "流体力学 / 计算流体力学方法": ["流体力学"],
}

# 关键词规范化映射：同义词/全称 → 规范缩写形式
KEYWORD_CANONICAL = {
    # PINN 系列
    "physics-informed neural network": "PINN",
    "physics-informed": "PINN",
    "physics-guided": "PINN",
    "physics-constrained": "PINN",
    "variational pinn": "PINN",
    "cpinn": "PINN",
    "physics-embedded": "PINN",
    "pinn": "PINN",
    # 算子/代理模型
    "fourier neural operator": "FNO",
    "fno": "FNO",
    "neural operator": "Neural Operator",
    "graph neural network": "GNN",
    "gnn": "GNN",
    "reduced-order model": "ROM",
    "reduced-order": "ROM",
    "reduced order": "ROM",
    "rom": "ROM",
    "proper orthogonal decomposition": "POD",
    "pod": "POD",
    # CFD
    "computational fluid dynamics": "CFD",
    "cfd": "CFD",
    # 湍流模拟方法
    "large eddy simulation": "LES",
    "direct numerical simulation": "DNS",
    "reynolds-averaged navier-stokes": "RANS",
    # 控制与学习
    "deep reinforcement learning": "DRL",
    "drl": "DRL",
    "reinforcement learning": "RL",
    # 流固耦合
    "fluid-structure interaction": "FSI",
    "fsi": "FSI",
    # 其他缩写
    "discrete element method": "DEM",
    "dem": "DEM",
    "smoothed particle hydrodynamics": "SPH",
    "sph": "SPH",
    "volume of fluid": "VOF",
    "vof": "VOF",
    "lattice boltzmann": "LBM",
    "lattice boltzmann method": "LBM",
    "variational autoencoder": "VAE",
    "cvae": "VAE",
    "autoencoder": "AE",
    "generative adversarial network": "GAN",
    "convolutional neural network": "CNN",
    "recurrent neural network": "RNN",
    # 拼写变体统一
    "surrogate modelling": "surrogate model",
    "surrogate modeling": "surrogate model",
    "turbulence modelling": "turbulence modeling",
    "aerodynamic design optimization": "aerodynamic optimization",
    "two-phase flows": "two-phase flow",
    "multiphase flows": "multiphase flow",
}


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower().strip())


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def normalize_arxiv_id(arxiv_id: str) -> str:
    arxiv_id = (arxiv_id or "").strip()
    arxiv_id = arxiv_id.rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE).lower()


def term_in_text(text: str, term: str) -> bool:
    term = (term or "").lower().strip()
    if not term:
        return False
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


# ═══════════════════════════════════════════════════════════
#  级联补全工具函数
# ═══════════════════════════════════════════════════════════

def _cascade_request_json(url: str, params: Optional[Dict] = None, timeout: int = 20) -> Optional[Dict]:
    """级联补全专用 JSON 请求，429 自动重试"""
    cache_key = (url, tuple(sorted((params or {}).items())))
    if cache_key in _CASCADE_JSON_CACHE:
        return _CASCADE_JSON_CACHE[cache_key]
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": "DailyPaperBot/1.0 (mailto:research@dailyPaper.org)"})
            if resp.status_code == 200:
                data = resp.json()
                _CASCADE_JSON_CACHE[cache_key] = data
                return data
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def _cascade_normalize_title(title: str) -> str:
    """标题归一化（用于比较）"""
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _cascade_title_matches(expected: str, candidate: str, threshold: float = 0.85) -> bool:
    """判断两个标题是否匹配"""
    from difflib import SequenceMatcher
    left = _cascade_normalize_title(expected)
    right = _cascade_normalize_title(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= threshold


def _cascade_crossref_date(item: Dict) -> str:
    """从 Crossref 工作记录提取日期（published-online > published-print > created）"""
    for field in ("published-online", "published-print", "created"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        dp = parts[0]
        y = dp[0] if len(dp) > 0 else None
        m = dp[1] if len(dp) > 1 else None
        d = dp[2] if len(dp) > 2 else None
        if not y or not m:
            continue
        if not d:
            d = 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    return ""


def _cascade_openalex_abstract(inverted_index: Optional[Dict]) -> str:
    """从 OpenAlex 的 inverted index 重建摘要文本"""
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def _is_reliable_abstract(text: str) -> bool:
    """判断摘要是否可靠"""
    if not text or len(text) < 220:
        return False
    if not text[0].isupper():
        return False
    if "  " in text:
        return False
    if not text[-1] in ".!?":
        return False
    bad_prefixes = ("cookies", "enable javascript", "we use cookies", "this site")
    if any(text.lower().startswith(p) for p in bad_prefixes):
        return False
    return True


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
    return any(term_in_text(text, term) for term in FLUID_RELATED_TERMS)


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
        'Neural Networks': 8.0,
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
        self.config = self._load_config(config_path)
        self._validate_config()
        self.arxiv_client = arxiv.Client()
        self.ss_api_key = (
            self.config.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        )

    def set_date_window(self, start_date: str = "", end_date: str = ""):
        """Apply a date window to sources that support month/range fetching."""
        if not start_date and not end_date:
            return
        for source_name in ("arxiv", "crossref", "openalex", "semantic_scholar", "wanfang", "cqvip"):
            source = self.config.get("sources", {}).setdefault(source_name, {})
            if start_date:
                source["start_date"] = start_date
            if end_date:
                source["end_date"] = end_date

    def _validate_config(self):
        """校验 config.yaml 关键字段是否存在"""
        sources = self.config.get("sources")
        if not sources or not isinstance(sources, dict):
            logger.warning("config.yaml 缺少 sources 配置，将不会抓取任何数据源")
            return

        for source_name in ["arxiv", "semantic_scholar", "google_scholar", "cnki", "wanfang", "cqvip"]:
            src = sources.get(source_name)
            if src and not isinstance(src, dict):
                logger.warning(f"config.yaml sources.{source_name} 格式错误（期望字典）")

        categories = self.config.get("categories")
        if not categories or not isinstance(categories, dict):
            logger.warning("config.yaml 缺少 categories 配置，论文分类将无法工作")

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
        """通过 Semantic Scholar API 获取引用次数（单篇查询，保留兼容）"""
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": title,
            "fields": "title,authors,year,citationCount",
            "limit": 1
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    paper = data["data"][0]
                    return paper.get("citationCount", 0)
        except Exception as e:
            logger.warning(f"Semantic Scholar API 查询失败: {e}")
        return None

    def batch_get_citation_counts(self, papers: List[Dict], batch_size: int = 20) -> Dict[str, Optional[int]]:
        """
        批量获取引用数：使用 Semantic Scholar /paper/batch 接口，
        通过 ArXiv ID 批量查询，避免逐篇请求导致速率限制。
        返回 {paper['id']: citation_count} 字典。
        """
        result_map = {}

        # 收集有 ArXiv ID 的论文
        id_pairs = []  # [(paper_id, arxiv_id), ...]
        for p in papers:
            aid = p.get("arxiv_id", "") or ""
            # 兼容：部分论文的 id 字段本身就是 arxiv_id
            if not aid and re.match(r"^\d{4}\.\d{4,5}", str(p.get("id", ""))):
                aid = p.get("id", "")
            if aid:
                # 标准化 ArXiv ID（去除版本号后缀）
                normalized = re.sub(r"v\d+$", "", aid)
                id_pairs.append((p["id"], normalized))

        if not id_pairs:
            return result_map

        headers = {}
        if self.ss_api_key:
            headers["x-api-key"] = self.ss_api_key

        total_batches = (len(id_pairs) + batch_size - 1) // batch_size
        consecutive_failures = 0
        max_consecutive_failures = 3  # 连续失败 3 次则放弃剩余批次

        # 首次请求前等待，确保 Semantic Scholar 限速窗口冷却
        logger.info(f"等待 API 冷却...")
        time.sleep(3)

        # 分批请求
        for i in range(0, len(id_pairs), batch_size):
            batch = id_pairs[i:i + batch_size]
            ss_ids = [f"ArXiv:{arxiv_id}" for _, arxiv_id in batch]
            batch_num = i // batch_size + 1

            url = "https://api.semanticscholar.org/graph/v1/paper/batch"
            params = {"fields": "title,citationCount"}

            try:
                resp = requests.post(url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30)

                # 遇到限速：最多重试 2 次，每次等待递增
                retry_count = 0
                while resp.status_code == 429 and retry_count < 2:
                    retry_count += 1
                    wait = 30 * retry_count  # 30s, 60s
                    logger.warning(f"批量 API 限速 (批次 {batch_num}/{total_batches})，等待 {wait} 秒后重试...")
                    time.sleep(wait)
                    resp = requests.post(url, params=params, json={"ids": ss_ids}, headers=headers, timeout=30)

                if resp.status_code == 200:
                    consecutive_failures = 0
                    data = resp.json()
                    matched = 0
                    for (paper_id, _), item in zip(batch, data):
                        if item and item.get("citationCount") is not None:
                            result_map[paper_id] = item["citationCount"]
                            matched += 1
                        else:
                            result_map[paper_id] = None
                    logger.info(f"批量引用: 批次 {batch_num}/{total_batches} 完成 ({matched}/{len(batch)} 篇命中)")
                else:
                    consecutive_failures += 1
                    logger.warning(f"批量 API 返回 {resp.status_code} (批次 {batch_num}/{total_batches})")
                    for paper_id, _ in batch:
                        result_map[paper_id] = None

                    # 连续失败过多，放弃剩余批次避免无谓等待
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询")
                        for paper_id, _ in id_pairs[i + batch_size:]:
                            result_map[paper_id] = None
                        break

            except Exception as e:
                consecutive_failures += 1
                logger.warning(f"批量 API 请求失败: {e}")
                for paper_id, _ in batch:
                    result_map[paper_id] = None

                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"连续 {max_consecutive_failures} 批次失败，跳过剩余引用查询")
                    for paper_id, _ in id_pairs[i + batch_size:]:
                        result_map[paper_id] = None
                    break

            # 批次间延迟（API Key 限制 1 req/sec，留足余量）
            if i + batch_size < len(id_pairs):
                time.sleep(3)

        success_count = sum(1 for v in result_map.values() if v is not None)
        logger.info(f"批量引用查询完成: {len(result_map)} 篇，其中 {success_count} 篇有引用数据 ({success_count*100//max(len(result_map),1)}%)")
        return result_map

    def _paper_text(self, paper: Dict) -> str:
        parts = [
            paper.get("title", ""),
            paper.get("abstract", ""),
            " ".join(str(cat) for cat in paper.get("categories", []) or []),
            paper.get("conference", ""),
            paper.get("venue", ""),
        ]
        return " ".join(parts).lower()

    def _term_in_text(self, text: str, term: str) -> bool:
        return term_in_text(text, term)

    def _contains_any(self, text: str, terms: List[str]) -> bool:
        return any(self._term_in_text(text, term) for term in terms)

    def _score_subdomains(self, paper: Dict) -> Dict[str, Dict]:
        text = self._paper_text(paper)
        scores = {}
        has_fluid_context = self._contains_any(text, FLUID_RELATED_TERMS) or any(
            str(cat).lower() in FLUID_RELATED_CATEGORIES
            for cat in paper.get("categories", []) or []
        )
        if not has_fluid_context:
            return scores

        for label, rule in SUBDOMAIN_RULES.items():
            strong_hits = [term for term in rule["strong"] if self._term_in_text(text, term)]
            context_hits = [term for term in rule["context"] if self._term_in_text(text, term)]
            negative_hits = [term for term in rule.get("negative", []) if self._term_in_text(text, term)]
            score = len(strong_hits) * 3 + len(context_hits) - len(negative_hits) * 4

            # 智能CFD 子类要求至少有一个 context 匹配（流体/CFD 场景词），
            # 防止仅凭 ML 术语就误分类。
            if "智能CFD" in label and not context_hits:
                score -= 3
            if strong_hits and score >= 3:
                scores[label] = {
                    "score": score,
                    "strong_hits": strong_hits[:8],
                    "context_hits": context_hits[:8],
                    "negative_hits": negative_hits[:5],
                }
        return scores

    def _publication_type(self, paper: Dict) -> str:
        publication_types = [str(t).lower() for t in paper.get("publication_types", []) or []]
        venue = paper.get("venue") or paper.get("conference") or ""
        if "journalarticle" in publication_types or paper.get("doi"):
            return "journal"
        if "conference" in publication_types:
            return "conference"
        if paper.get("arxiv_id"):
            return "preprint" if not venue else "conference"
        return "unknown"

    def _finalize_paper(self, paper: Dict) -> Dict:
        paper["venue"] = paper.get("venue") or paper.get("conference") or ""
        paper["conference"] = paper.get("conference") or paper.get("venue") or ""
        paper["doi"] = normalize_doi(paper.get("doi", ""))
        raw_arxiv_id = paper.get("arxiv_id") or ""
        if not raw_arxiv_id and re.match(r"^\d{4}\.\d{4,5}", str(paper.get("id", ""))):
            raw_arxiv_id = paper.get("id", "")
        paper["arxiv_id"] = normalize_arxiv_id(raw_arxiv_id)
        if paper.get("arxiv_id") and not paper.get("arxiv_url"):
            paper["arxiv_url"] = f"https://arxiv.org/abs/{paper['arxiv_id']}"
        if paper.get("arxiv_id") and not paper.get("preprint_pdf_url"):
            paper["preprint_pdf_url"] = f"https://arxiv.org/pdf/{paper['arxiv_id']}"
        paper["paper_url"] = (
            paper.get("paper_url")
            or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")
            or paper.get("arxiv_url")
            or ""
        )
        paper["publication_type"] = paper.get("publication_type") or self._publication_type(paper)
        paper["is_preprint"] = paper["publication_type"] == "preprint"
        # 预出版检测：published 在未来且有 DOI/venue（已被接收但未正式见刊）
        _pub = paper.get("published", "")
        _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        paper["is_early_access"] = (
            len(_pub) >= 10 and _pub > _today
            and bool(paper.get("doi") or paper.get("venue") or paper.get("conference"))
        )
        if not paper["is_preprint"] and "arxiv.org" in str(paper.get("pdf_url", "")):
            paper["preprint_pdf_url"] = paper.get("preprint_pdf_url") or paper["pdf_url"]
            paper["pdf_url"] = ""
        if not paper.get("source"):
            if paper.get("semantic_scholar_id") or paper.get("doi"):
                paper["source"] = "semantic_scholar"
            elif paper.get("arxiv_url") or paper.get("arxiv_id"):
                paper["source"] = "arxiv"
            else:
                paper["source"] = "unknown"
        paper["impact_factor"] = paper.get("impact_factor") or self.get_impact_factor(paper)
        # 日期来源追踪（新增）
        if "date_source" not in paper:
            src = paper.get("source", "")
            if src in ("arxiv", "crossref", "openalex", "semantic_scholar", "cnki", "google_scholar"):
                paper["date_source"] = src
            else:
                paper["date_source"] = ""
        if "date_status" not in paper:
            src = paper.get("source", "")
            paper["date_status"] = "reliable" if src in ("arxiv", "crossref", "semantic_scholar") else "approximate"
        paper["tags"] = self.classify_paper(paper)
        paper["primary_domain"] = paper["tags"][-1] if paper.get("tags") else ""
        official_keywords = paper.get("official_keywords") or []
        paper["custom_keywords"] = self.extract_paper_keywords(paper)
        paper["keywords"] = self._normalize_keywords(official_keywords + paper["custom_keywords"])
        return paper

    def _identity_keys(self, paper: Dict) -> List[str]:
        keys = []
        doi = normalize_doi(paper.get("doi", ""))
        arxiv_id = normalize_arxiv_id(paper.get("arxiv_id") or paper.get("id", ""))
        title = normalize_title(paper.get("title", ""))
        if doi:
            keys.append(f"doi:{doi}")
        if arxiv_id and re.match(r"^\d{4}\.\d{4,5}", arxiv_id):
            keys.append(f"arxiv:{arxiv_id}")
        if title:
            keys.append(f"title:{title}")
        return keys

    def _source_rank(self, paper: Dict) -> int:
        rank = 0
        source = paper.get("source", "")
        if source == "semantic_scholar":
            rank += 30
        elif source == "crossref":
            rank += 25   # 正式出版元数据，质量高
        elif source == "openalex":
            rank += 20   # 元数据较全，但可能含预印本
        if paper.get("doi"):
            rank += 20
        if paper.get("venue") or paper.get("conference"):
            rank += 10
        if paper.get("citation_count") is not None:
            rank += 5
        return rank

    def _merge_two_papers(self, old: Dict, new: Dict) -> Dict:
        primary, secondary = (new, old) if self._source_rank(new) >= self._source_rank(old) else (old, new)
        merged = dict(secondary)
        merged.update({k: v for k, v in primary.items() if v not in (None, "", [], {})})

        for field in ["arxiv_url", "pdf_url", "preprint_pdf_url", "paper_url", "doi", "venue", "conference"]:
            if not merged.get(field):
                merged[field] = old.get(field) or new.get(field) or ""

        merged["citation_count"] = (
            new.get("citation_count")
            if new.get("citation_count") is not None
            else old.get("citation_count")
        )
        merged["keywords"] = self._normalize_keywords((old.get("keywords") or []) + (new.get("keywords") or []))
        merged["categories"] = sorted(set((old.get("categories") or []) + (new.get("categories") or [])))
        merged["sources"] = sorted(set((old.get("sources") or [old.get("source", "unknown")]) + (new.get("sources") or [new.get("source", "unknown")])))
        merged["source"] = primary.get("source") or merged.get("source") or "unknown"
        return self._finalize_paper(merged)

    # ═══════════════════════════════════════════════════════════
    #  级联补全：Crossref → OpenAlex → Semantic Scholar → publisher meta
    # ═══════════════════════════════════════════════════════════

    def _cascade_enrich_papers(self, papers: List[Dict]) -> None:
        """对每篇论文依次从 Crossref → OpenAlex → Semantic Scholar → publisher 补全元数据。
        原地修改论文字典，不返回新列表。"""
        enriched_count = 0
        total = len(papers)

        for i, paper in enumerate(papers):
            needs_enrichment = (
                not paper.get("doi")
                or not paper.get("abstract", "").strip()
                or paper.get("date_status") not in ("reliable",)
                or not paper.get("venue")
            )
            if not needs_enrichment:
                continue

            title = paper.get("title", "")
            if not title:
                continue

            before = json.dumps({
                "doi": paper.get("doi"),
                "abstract": bool((paper.get("abstract") or "").strip()),
                "date_status": paper.get("date_status"),
                "venue": paper.get("venue"),
                "citation_count": paper.get("citation_count"),
            }, ensure_ascii=False, sort_keys=True)

            # 级联第1步：Crossref（正式出版元数据；有 DOI 时优先直查）
            if self._needs_crossref_enrichment(paper):
                self._enrich_from_crossref(paper)
                time.sleep(0.15)

            # 级联第2步：OpenAlex（开放摘要/引用/venue 补充）
            if self._needs_openalex_enrichment(paper):
                self._enrich_from_openalex(paper)
                time.sleep(0.15)

            # 级联第3步：Semantic Scholar（最后再用，降低 429 概率）
            if self._needs_semantic_scholar_enrichment(paper):
                self._enrich_from_semantic_scholar(paper)
                time.sleep(0.15)

            # 级联第4步：publisher meta（抓取网页 meta 标签）
            if self._needs_publisher_enrichment(paper):
                self._enrich_from_publisher(paper)

            after = json.dumps({
                "doi": paper.get("doi"),
                "abstract": bool((paper.get("abstract") or "").strip()),
                "date_status": paper.get("date_status"),
                "venue": paper.get("venue"),
                "citation_count": paper.get("citation_count"),
            }, ensure_ascii=False, sort_keys=True)
            if after != before:
                enriched_count += 1
            if (i + 1) % 20 == 0:
                logger.info(f"级联补全进度: {i+1}/{total}")

        logger.info(f"级联补全完成: {enriched_count}/{total} 篇需要补全")

    def _has_reliable_abstract(self, paper: Dict) -> bool:
        return bool((paper.get("abstract") or "").strip()) and paper.get("abstract_status") != "unreliable_google_scholar_snippet"

    def _has_complete_date(self, paper: Dict) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(paper.get("published", ""))))

    def _metadata_complete(self, paper: Dict) -> bool:
        return (
            bool(paper.get("doi") or paper.get("arxiv_id"))
            and self._has_reliable_abstract(paper)
            and self._has_complete_date(paper)
            and bool(paper.get("venue") or paper.get("conference") or paper.get("is_preprint"))
        )

    def _needs_crossref_enrichment(self, paper: Dict) -> bool:
        if paper.get("source") == "arxiv" and not paper.get("doi"):
            return False
        return not self._metadata_complete(paper) and (
            bool(paper.get("doi"))
            or not paper.get("doi")
            or not self._has_complete_date(paper)
            or not paper.get("venue")
        )

    def _needs_openalex_enrichment(self, paper: Dict) -> bool:
        return not self._metadata_complete(paper) and (
            not self._has_reliable_abstract(paper)
            or not self._has_complete_date(paper)
            or not paper.get("doi")
            or paper.get("citation_count") is None
            or not paper.get("venue")
        )

    def _needs_semantic_scholar_enrichment(self, paper: Dict) -> bool:
        return not self._metadata_complete(paper) and (
            not self._has_reliable_abstract(paper)
            or not paper.get("semantic_scholar_id")
            or paper.get("citation_count") is None
            or (not paper.get("doi") and not paper.get("arxiv_id"))
        )

    def _needs_publisher_enrichment(self, paper: Dict) -> bool:
        return not self._has_reliable_abstract(paper)

    def _enrich_from_crossref(self, paper: Dict) -> None:
        """从 Crossref 补全单篇论文的元数据"""
        from urllib.parse import quote
        doi = (paper.get("doi") or "").strip()
        results = []

        # DOI 直查
        if doi:
            data = _cascade_request_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
            if data and data.get("message"):
                results.append(data["message"])

        # 标题搜索
        if not results:
            data = _cascade_request_json(
                "https://api.crossref.org/works",
                params={"query.title": paper.get("title", ""), "rows": 3},
            )
            if data:
                for item in ((data.get("message") or {}).get("items") or []):
                    item_title = " ".join(item.get("title") or [])
                    if _cascade_title_matches(paper.get("title", ""), item_title):
                        results.append(item)
                        break

        for item in results[:1]:
            # 补全 DOI
            if not paper.get("doi") and item.get("DOI"):
                paper["doi"] = item["DOI"].strip().lower()
            # 补全日期
            if paper.get("date_status") != "reliable":
                date = _cascade_crossref_date(item)
                if date:
                    paper["published"] = date
                    paper["date_source"] = "crossref"
                    paper["date_status"] = "reliable"
            # 补全摘要
            if not paper.get("abstract", "").strip():
                abstract = item.get("abstract", "")
                if abstract:
                    abstract = re.sub(r"<[^>]+>", " ", abstract)
                    abstract = re.sub(r"\s+", " ", abstract).strip()
                    if _is_reliable_abstract(abstract):
                        paper["abstract"] = abstract
                        paper["abstract_status"] = "enriched"
                        paper["abstract_source"] = "crossref"
            # 补全 venue
            if not paper.get("venue"):
                container = item.get("container-title") or []
                if container:
                    paper["venue"] = container[0].strip()
                    paper["conference"] = paper["conference"] or paper["venue"]
            # 补全引用数
            if paper.get("citation_count") is None:
                count = item.get("is-referenced-by-count")
                if count is not None:
                    paper["citation_count"] = count

    def _enrich_from_openalex(self, paper: Dict) -> None:
        """从 OpenAlex 补全单篇论文的元数据"""
        data = _cascade_request_json(
            "https://api.openalex.org/works",
            params={
                "search": paper.get("title", ""),
                "per_page": 3,
                "mailto": "research@dailyPaper.org",
            },
        )
        if not data:
            return

        for item in (data.get("results") or []):
            if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
                continue
            # 补全 DOI
            if not paper.get("doi"):
                raw_doi = (item.get("doi") or "").replace("https://doi.org/", "")
                if raw_doi:
                    paper["doi"] = raw_doi
            # 补全日期
            if paper.get("date_status") != "reliable":
                pub_date = item.get("publication_date") or ""
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                    paper["published"] = pub_date
                    paper["date_source"] = "openalex"
                    paper["date_status"] = "approximate"
            # 补全摘要（从 inverted index 重建）
            if not paper.get("abstract", "").strip():
                abstract = _cascade_openalex_abstract(item.get("abstract_inverted_index"))
                if _is_reliable_abstract(abstract):
                    paper["abstract"] = abstract
                    paper["abstract_status"] = "enriched"
                    paper["abstract_source"] = "openalex"
            # 补全 venue
            if not paper.get("venue"):
                loc = item.get("primary_location") or {}
                src = loc.get("source") or {}
                venue = src.get("display_name") or ""
                if venue:
                    paper["venue"] = venue
                    paper["conference"] = paper["conference"] or venue
            # 补全引用数
            if paper.get("citation_count") is None:
                count = item.get("cited_by_count")
                if count is not None:
                    paper["citation_count"] = count
            break  # 只取第一个匹配

    def _enrich_from_semantic_scholar(self, paper: Dict) -> None:
        """从 Semantic Scholar 补全单篇论文的元数据"""
        data = _cascade_request_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": paper.get("title", ""),
                "fields": "paperId,title,abstract,externalIds,publicationDate,citationCount,venue",
                "limit": 3,
            },
        )
        if not data:
            return

        for item in (data.get("data") or []):
            if not _cascade_title_matches(paper.get("title", ""), item.get("title", "")):
                continue
            # 补全 DOI / arXiv ID
            ext = item.get("externalIds") or {}
            if not paper.get("doi") and ext.get("DOI"):
                paper["doi"] = ext["DOI"]
            if not paper.get("arxiv_id") and ext.get("ArXiv"):
                paper["arxiv_id"] = ext["ArXiv"]
                paper["arxiv_url"] = f"https://arxiv.org/abs/{ext['ArXiv']}"
                paper["preprint_pdf_url"] = f"https://arxiv.org/pdf/{ext['ArXiv']}"
            # 补全日期
            if paper.get("date_status") != "reliable":
                pub_date = item.get("publicationDate") or ""
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub_date):
                    paper["published"] = pub_date
                    paper["date_source"] = "semantic_scholar"
                    paper["date_status"] = "approximate"
            # 补全摘要
            if not paper.get("abstract", "").strip():
                abstract = (item.get("abstract") or "").strip()
                if _is_reliable_abstract(abstract):
                    paper["abstract"] = abstract
                    paper["abstract_status"] = "enriched"
                    paper["abstract_source"] = "semantic_scholar"
            # 补全 venue
            if not paper.get("venue"):
                venue = item.get("venue") or ""
                if venue:
                    paper["venue"] = venue
                    paper["conference"] = paper["conference"] or venue
            # 补全引用数
            if paper.get("citation_count") is None:
                count = item.get("citationCount")
                if count is not None:
                    paper["citation_count"] = count
            # 补全 Semantic Scholar ID
            if not paper.get("semantic_scholar_id") and item.get("paperId"):
                paper["semantic_scholar_id"] = item["paperId"]
            break

    def _enrich_from_publisher(self, paper: Dict) -> None:
        """从出版商网页 meta 标签补全摘要"""
        if paper.get("abstract", "").strip():
            return  # 已有摘要，跳过
        url = paper.get("paper_url") or paper.get("arxiv_url") or ""
        if not url:
            return
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "DailyPaperBot/1.0"})
            if resp.status_code != 200:
                return
            soup = BeautifulSoup(resp.text, "lxml")
            for tag_name in ("citation_abstract", "dc.description", "description", "og:description"):
                tag = soup.find("meta", attrs={"name": tag_name}) or soup.find("meta", attrs={"property": tag_name})
                if tag and tag.get("content"):
                    abstract = re.sub(r"\s+", " ", tag["content"]).strip()
                    if _is_reliable_abstract(abstract):
                        paper["abstract"] = abstract
                        paper["abstract_status"] = "enriched"
                        paper["abstract_source"] = "publisher_meta"
                        break
        except Exception:
            pass

    def _merge_paper_list(self, papers: List[Dict]) -> List[Dict]:
        merged = []
        key_to_index = {}
        for paper in papers:
            paper = self._finalize_paper(paper)
            keys = self._identity_keys(paper)
            existing_index = next((key_to_index[k] for k in keys if k in key_to_index), None)
            if existing_index is None:
                key_to_index.update({k: len(merged) for k in keys})
                merged.append(paper)
                continue

            merged[existing_index] = self._merge_two_papers(merged[existing_index], paper)
            for key in self._identity_keys(merged[existing_index]):
                key_to_index[key] = existing_index
        return merged

    def write_classification_report(self, papers: List[Dict], data_dir: str):
        report = {}
        for paper in papers:
            primary = paper.get("primary_domain") or "未分类"
            report.setdefault(primary, [])
            if len(report[primary]) >= 12:
                continue
            report[primary].append({
                "title": paper.get("title", ""),
                "source": paper.get("source", ""),
                "publication_type": paper.get("publication_type", ""),
                "venue": paper.get("venue") or paper.get("conference") or "",
                "citation_count": paper.get("citation_count"),
                "classification_score": paper.get("classification_score", {}).get(primary),
                "doi": paper.get("doi", ""),
                "arxiv_id": paper.get("arxiv_id", ""),
            })
        path = os.path.join(data_dir, "classification_report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"分类验证报告已保存到: {path}")

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
        extracted = list({kw for kw in all_keywords if self._term_in_text(text, kw)})
        
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
            if self._term_in_text(text, kw) and kw.lower() not in extracted:
                extracted.append(kw.lower())
        
        # 最多保留10个关键词（适配新增词汇，多保留2个）
        return extracted[:10]

    def _normalize_keywords(self, keywords: List[str]) -> List[str]:
        """将同义关键词合并为规范缩写形式，去重并排序"""
        normalized = set()
        for kw in keywords:
            canonical = KEYWORD_CANONICAL.get(kw.lower().strip(), kw)
            normalized.add(canonical)
        return sorted(normalized)

    def classify_paper(self, paper: Dict) -> List[str]:
        """Classify into the smallest CFD/fluid subdomain using strict scored rules."""
        text = self._paper_text(paper)
        ordered_tags = []
        categories = self.config.get("categories", {})

        def add_tag(category_name: str):
            if category_name in categories and category_name not in ordered_tags:
                ordered_tags.append(category_name)

        has_fluid = self._contains_any(text, FLUID_RELATED_TERMS) or any(
            str(cat).lower() in FLUID_RELATED_CATEGORIES
            for cat in paper.get("categories", []) or []
        )
        has_ml = self._contains_any(text, [
            "machine learning", "deep learning", "neural network", "neural operator",
            "reinforcement learning", "data-driven", "pinn", "physics-informed",
            "surrogate", "reduced-order", "rom", "gnn",
        ])

        if has_ml:
            add_tag("机器学习")
        if has_fluid:
            add_tag("流体力学")
        if not has_fluid:
            paper["classification_score"] = {}
            return ordered_tags

        scores = self._score_subdomains(paper)
        paper["classification_score"] = scores
        if not scores:
            # 兜底：流体论文未匹配任何子域时归入"其他"
            add_tag("流体力学 / 其他")
            return ordered_tags

        sorted_labels = sorted(scores, key=lambda label: scores[label]["score"], reverse=True)
        primary = sorted_labels[0]
        for parent in PARENT_TAGS.get(primary, []):
            add_tag(parent)
        add_tag(primary)

        # Keep a small number of secondary leaf tags only when they are clearly distinct.
        primary_score = scores[primary]["score"]
        for label in sorted_labels[1:]:
            if scores[label]["score"] >= max(5, primary_score - 2):
                for parent in PARENT_TAGS.get(label, []):
                    add_tag(parent)
                add_tag(label)
        return ordered_tags

    def fetch_semantic_scholar_papers(self) -> List[Dict]:
        """用 Semantic Scholar 语义搜索替代关键词匹配"""
        from fetchers.semantic_scholar import fetch_semantic_scholar_papers as _fetch
        return _fetch(self)

    def fetch_crossref_papers(self) -> List[Dict]:
        """Crossref 数据源抓取（正式发表论文）"""
        from fetchers.crossref_fetcher import fetch_crossref_papers as _fetch
        return _fetch(self)

    def fetch_openalex_papers(self) -> List[Dict]:
        """OpenAlex 数据源抓取（开放学术图谱）"""
        from fetchers.openalex_fetcher import fetch_openalex_papers as _fetch
        return _fetch(self)

    def _flatten_queries(self, raw_queries) -> List[str]:
        if isinstance(raw_queries, dict):
            queries = []
            for values in raw_queries.values():
                queries.extend(values if isinstance(values, list) else [values])
            return [str(q) for q in queries if str(q).strip()]
        return [str(q) for q in (raw_queries or []) if str(q).strip()]

    def fetch_google_scholar_papers(self) -> List[Dict]:
        """Google Scholar 数据源抓取"""
        from fetchers.google_scholar import fetch_google_scholar_papers as _fetch
        return _fetch(self)
    def fetch_cnki_papers(self) -> List[Dict]:
        """CNKI 数据源抓取"""
        from fetchers.cnki import fetch_cnki_papers as _fetch
        return _fetch(self)
    def fetch_wanfang_papers(self) -> List[Dict]:
        """Wanfang data source."""
        from fetchers.wanfang import fetch_wanfang_papers as _fetch
        return _fetch(self)
    def fetch_cqvip_papers(self) -> List[Dict]:
        """CQVIP data source."""
        from fetchers.cqvip import fetch_cqvip_papers as _fetch
        return _fetch(self)
    def fetch_arxiv_papers(self) -> List[Dict]:
        """从 ArXiv 抓取论文"""
        from fetchers.arxiv_fetcher import fetch_arxiv_papers as _fetch
        return _fetch(self)
    def save_papers(self):
        output_config = self.config.get("output", {})
        data_dir = output_config.get("data_dir", "data")
        os.makedirs(data_dir, exist_ok=True)
        docs_dir = output_config.get("docs_dir", "docs")
        os.makedirs(docs_dir, exist_ok=True)

        # 从多个数据源抓取
        papers = []

        try:
            arxiv_papers = self.fetch_arxiv_papers()
        except Exception as e:
            logger.warning(f"ArXiv 补充源抓取失败，继续使用 Semantic Scholar: {e}")
            arxiv_papers = []
        logger.info(f"ArXiv: {len(arxiv_papers)} 篇")
        papers.extend(arxiv_papers)

        try:
            crossref_papers = self.fetch_crossref_papers()
        except Exception as e:
            logger.warning(f"Crossref 抓取失败: {e}")
            crossref_papers = []
        logger.info(f"Crossref: {len(crossref_papers)} 篇")
        papers.extend(crossref_papers)

        try:
            openalex_papers = self.fetch_openalex_papers()
        except Exception as e:
            logger.warning(f"OpenAlex 抓取失败: {e}")
            openalex_papers = []
        logger.info(f"OpenAlex: {len(openalex_papers)} 篇")
        papers.extend(openalex_papers)

        try:
            ss_papers = self.fetch_semantic_scholar_papers()
        except Exception as e:
            logger.warning(f"Semantic Scholar 抓取失败: {e}")
            ss_papers = []
        logger.info(f"Semantic Scholar: {len(ss_papers)} 篇")
        papers.extend(ss_papers)

        try:
            gs_papers = self.fetch_google_scholar_papers()
        except Exception as e:
            logger.warning(f"Google Scholar 抓取失败: {e}")
            gs_papers = []
        logger.info(f"Google Scholar: {len(gs_papers)} 篇")
        papers.extend(gs_papers)

        try:
            wanfang_papers = self.fetch_wanfang_papers()
        except Exception as e:
            logger.warning(f"Wanfang fetch failed: {e}")
            wanfang_papers = []
        logger.info(f"Wanfang: {len(wanfang_papers)} papers")
        papers.extend(wanfang_papers)

        try:
            cqvip_papers = self.fetch_cqvip_papers()
        except Exception as e:
            logger.warning(f"CQVIP fetch failed: {e}")
            cqvip_papers = []
        logger.info(f"CQVIP: {len(cqvip_papers)} papers")
        papers.extend(cqvip_papers)

        try:
            cnki_papers = self.fetch_cnki_papers()
        except Exception as e:
            logger.warning(f"CNKI 抓取失败: {e}")
            cnki_papers = []
        logger.info(f"CNKI: {len(cnki_papers)} 篇")
        papers.extend(cnki_papers)

        papers = self._merge_paper_list([p for p in papers if is_relevant_paper(p)])
        logger.info(f"抓取结果合并去重后: {len(papers)} 篇")

        # 级联补全元数据（Crossref → OpenAlex → Semantic Scholar → publisher meta）
        self._cascade_enrich_papers(papers)

        # 重新 merge（级联补全可能新增 DOI/arXiv ID）
        papers = self._merge_paper_list(papers)

        # ========== 新增：按月份拆分数据（和main.js加载逻辑对齐） ==========
        existing_papers = []
        for filename in os.listdir(data_dir):
            if not re.fullmatch(r"\d{4}-\d{2}\.json", filename):
                continue
            path = os.path.join(data_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_papers.extend(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to read existing monthly data: {path}, {e}")

        papers = self._merge_paper_list([
            p for p in existing_papers + papers
            if is_relevant_paper(p)
        ])
        logger.info(f"Merged with existing monthly data: {len(papers)} papers")

        if not papers:
            logger.warning("未抓取到任何相关论文，且没有可整理的历史数据！")
            return

        self.write_classification_report(papers, data_dir)

        # 补全不完整的日期（只有年份的补充为 YYYY-01-01）
        for paper in papers:
            pub = paper.get("published", "")
            if pub and len(pub) == 4 and pub.isdigit():
                paper["published"] = f"{pub}-01-01"
                paper["date_status"] = paper.get("date_status") or "year_only"
            elif pub and len(pub) == 7:
                # 只有 YYYY-MM，补充为该月1号
                paper["published"] = f"{pub}-01"
                paper["date_status"] = paper.get("date_status") or "approximate"

        month_papers = {}
        for paper in papers:
            pub = paper.get("published", "")
            parts = pub.split("-")
            if len(parts) >= 2:
                month = f"{parts[0]}-{parts[1]}"
            elif len(parts) == 1 and parts[0].isdigit():
                month = f"{parts[0]}-01"  # 只有年份时归到1月
            else:
                month = "unknown"
            if month not in month_papers:
                month_papers[month] = []
            month_papers[month].append(paper)

        # 生成月份索引文件（data/index.json）
        index_data = []
        for month in sorted(month_papers.keys(), reverse=True):
            month_items = month_papers[month]
            index_data.append({
                "month": month,
                "count": len(month_items),
                "published_count": sum(1 for p in month_items if not p.get("is_preprint")),
                "preprint_count": sum(1 for p in month_items if p.get("is_preprint")),
                "early_access_count": sum(1 for p in month_items if p.get("is_early_access")),
            })
        with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        logger.info(f"月份索引已保存到：{os.path.join(data_dir, 'index.json')}")

        # 保存各月份数据（如data/2026-01.json）—— 已包含official_keywords/custom_keywords
        for month, papers in month_papers.items():
            month_path = os.path.join(data_dir, f"{month}.json")
            # 写入前备份已有文件（最多保留一个 .bak 副本）
            if os.path.exists(month_path):
                import shutil
                shutil.copy2(month_path, month_path + ".bak")
            with open(month_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            logger.info(f"月份数据已保存到：{month_path}")

        # 同步到docs目录（可选，保留papers.json）—— 同样包含新字段
        with open(os.path.join(docs_dir, "papers.json"), "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

def _month_window(month: str) -> Tuple[str, str]:
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise ValueError("--month must use YYYY-MM format")
    year, month_num = [int(part) for part in month.split("-")]
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year:04d}-{month_num:02d}-01", f"{year:04d}-{month_num:02d}-{last_day:02d}"


def main():
    """主函数：一键抓取+分类+保存+同步"""
    parser = argparse.ArgumentParser(description="Fetch DailyPaper records from configured sources.")
    parser.add_argument("--month", help="Fetch a single month, e.g. 2026-01.")
    parser.add_argument("--start-date", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Inclusive end date, YYYY-MM-DD.")
    args = parser.parse_args()

    try:
        fetcher = PaperFetcher()  # 实例化时调用__init__，正确初始化self.config
        if args.month:
            start_date, end_date = _month_window(args.month)
            fetcher.set_date_window(start_date, end_date)
            logger.info(f"按月抓取窗口: {start_date} 到 {end_date}")
        elif args.start_date or args.end_date:
            fetcher.set_date_window(args.start_date or "", args.end_date or "")
            logger.info(f"按日期抓取窗口: {args.start_date or 'open'} 到 {args.end_date or 'open'}")
        fetcher.save_papers()
        logger.info("\n✅ 全部完成！直接打开 docs/index.html 即可查看结果")
    except Exception as e:
        logger.error(f"运行失败：{e}", exc_info=True)

if __name__ == "__main__":
    main()
