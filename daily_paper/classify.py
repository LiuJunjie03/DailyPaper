"""
论文分类模块：从 fetch_papers.py 提取的分类常量与函数。

包含：
- 分类相关常量（FLUID_RELATED_TAGS, FLUID_RELATED_TERMS, ...）
- 术语匹配与子域评分函数
- 论文分类、关键词提取、规范化函数
"""

import json
import logging
import os
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  分类常量
# ═══════════════════════════════════════════════════════════

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
    # 中文术语 — 让知网/万方等中文源的论文能通过相关性过滤
    "计算流体力学",
    "流体力学",
    "流体动力学",
    "流场",
    "流动机理",
    "流动控制",
    "流动数值",
    "湍流",
    "雷诺平均",
    "大涡模拟",
    "直接数值模拟",
    "多相流",
    "两相流",
    "空气动力学",
    "气动",
    "翼型",
    "纳维斯托克斯",
    "navier-stokes方程",
    "格子玻尔兹曼",
    "有限体积",
    "数值模拟",
    "多孔介质",
    "血流",
    "传热",
    "燃烧",
    "风力机",
    "风机",
    "降水",
    "反应流",
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
            # 中文术语
            "代理模型", "代理预测", "降阶模型", "降维模型",
            "本征正交分解", "算子学习", "神经算子",
            "傅里叶神经算子", "koopman算子",
            "数据驱动代理", "流场预测",
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
            # 中文术语
            "湍流闭合", "湍流闭合模型", "湍流模型",
            "雷诺应力", "涡黏性", "涡粘性",
            "亚网格", "亚格子", "壁面模型",
            "数据驱动湍流", "湍流模拟", "湍流建模",
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
            # 中文术语
            "数值通量", "通量限制器", "可微求解器",
            "神经求解器", "数值粘性",
            "数值格式", "离散格式", "数值离散",
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
            # 中文术语
            "加速求解", "快速计算", "超分辨", "超分辨率",
            "粗网格", "多重网格", "实时仿真", "实时模拟",
            "降尺度", "流场超分辨",
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
            # 中文术语
            "物理信息神经网络", "物理约束神经网络",
            "物理引导神经网络", "物理嵌入",
            "pinn方程", "pinn求解",
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
            # 中文术语
            "流场重建", "流场重构", "流场反演",
            "不确定性量化", "数据同化",
            "稀疏传感", "稀疏测量", "反问题",
            "状态估计", "流场估计",
            "卡尔曼", "概率预测",
            "扩散模型",
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
            # 中文术语
            "流动控制", "主动流动控制", "主动控制",
            "强化学习", "深度强化学习",
            "闭环控制", "最优控制",
            "减阻控制", "减阻",
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
            # 中文术语
            "气动优化", "气动外形优化", "气动设计优化",
            "翼型优化", "机翼优化", "形状优化",
            "反设计", "拓扑优化", "伴随优化",
            "气动减阻", "增升",
        ],
        "context": ["airfoil", "wing", "aerodynamics", "drag", "lift", "uav", "aircraft",
                    "翼型", "机翼", "气动", "减阻", "飞行器"],
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
            # 中文术语
            "湍流机理", "湍流结构", "各向同性湍流",
            "涡旋", "旋涡", "涡结构",
            "边界层流动", "流动不稳定性",
            "射流", "剪切流", "尾流", "混合层",
            "流动机理",
        ],
        "context": ["flow", "fluid", "navier-stokes", "physics.flu-dyn",
                    "流动", "流体", "边界层"],
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
            # 中文术语
            "多相流", "两相流",
            "相分离", "相场", "界面捕获", "界面追踪", "界面跟踪",
            "level set方法", "水平集",
            "格子玻尔兹曼", "空化", "空蚀",
            "沸腾", "液滴", "气泡", "雾化",
        ],
        "context": ["fluid", "flow", "navier-stokes", "cfd", "流体", "流动"],
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
            # 中文术语
            "空气动力学", "翼型", "机翼气动",
            "无人机气动", "飞行器气动",
            "可压缩流", "高超声速", "高超音速",
            "激波", "气动弹性",
            "流固耦合",
        ],
        "context": ["flow", "fluid", "cfd", "navier-stokes", "流动", "流体"],
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
            # 中文术语
            "天气预报", "气候", "降水",
            "大气流动", "海洋流动", "海洋环流",
            "海冰", "地球物理流体", "环境流体",
            "海岸水动力", "风暴", "大气动力学",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd", "流体", "流动"],
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
            # 中文术语
            "血流", "心血管", "动脉瘤", "主动脉",
            "生物医学流体", "纤毛",
            "微流体", "微流控",
            "呼吸流", "血流动力学", "心室流",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd", "流体", "流动"],
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
            # 中文术语
            "燃烧", "反应流", "爆轰",
            "火灾模拟", "传热", "对流传热",
            "辐射传热", "火焰", "热流",
        ],
        "context": ["fluid", "flow", "simulation", "navier-stokes", "cfd", "流体", "流动"],
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
            # 中文术语
            "风力机", "风力发电机", "海上风电", "漂浮式风电",
            "尾流建模", "风电场", "漂浮式风机",
            "波浪结构", "海洋水动力",
            "海洋能", "风能",
        ],
        "context": ["fluid", "flow", "simulation", "cfd", "turbulent", "流体", "流动"],
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
            # 中文术语
            "有限体积法", "有限元法", "有限体积", "有限元",
            "网格生成", "自适应网格", "网格加密",
            "高阶格式", "开源求解器",
            "误差估计", "网格收敛",
            "离散误差", "数值方法",
        ],
        "context": ["cfd", "navier-stokes", "numerical", "computational fluid dynamics",
                    "数值", "网格", "离散"],
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

# ═══════════════════════════════════════════════════════════
#  术语匹配
# ═══════════════════════════════════════════════════════════


def term_in_text(text: str, term: str) -> bool:
    term = (term or "").lower().strip()
    if not term:
        return False
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


# ═══════════════════════════════════════════════════════════
#  分类辅助函数
# ═══════════════════════════════════════════════════════════


def paper_text(paper: Dict) -> str:
    parts = [
        paper.get("title", ""),
        paper.get("abstract", ""),
        " ".join(str(cat) for cat in paper.get("categories", []) or []),
        paper.get("conference", ""),
        paper.get("venue", ""),
    ]
    return " ".join(parts).lower()


def contains_any(text: str, terms: list) -> bool:
    return any(term_in_text(text, term) for term in terms)


def score_subdomains(paper_text: str, subdomain_rules: dict, fluid_terms, paper_categories) -> dict:
    """计算论文在各子域的匹配分数。

    Args:
        paper_text: 论文标题+摘要拼接的归一化文本（由 paper_text() 生成）
        subdomain_rules: SUBDOMAIN_RULES 字典
        fluid_terms: FLUID_RELATED_TERMS 列表
        paper_categories: 论文的 ArXiv 分类列表（paper.get("categories", [])），
                          用于检测流体相关分类
    """
    scores = {}
    has_fluid_context = contains_any(paper_text, fluid_terms) or any(
        str(cat).lower() in FLUID_RELATED_CATEGORIES
        for cat in paper_categories or []
    )
    if not has_fluid_context:
        return scores

    for label, rule in subdomain_rules.items():
        strong_hits = [term for term in rule["strong"] if term_in_text(paper_text, term)]
        context_hits = [term for term in rule["context"] if term_in_text(paper_text, term)]
        negative_hits = [term for term in rule.get("negative", []) if term_in_text(paper_text, term)]
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


INTELLIGENT_METHOD_TERMS = [
    "machine learning", "deep learning", "neural network", "neural operator",
    "operator learning", "physics-informed", "pinn", "data-driven",
    "reinforcement learning", "transfer learning", "surrogate model",
    "reduced-order model", "reduced order model", "autoencoder", "deep autoencoder",
    "differentiable solver", "learned numerical", "data assimilation",
    "机器学习", "深度学习", "神经网络", "神经算子", "算子学习",
    "物理信息神经网络", "物理约束深度学习", "物理增强",
    "数据驱动", "强化学习", "迁移学习", "代理模型", "智能预测模型",
    "降阶模型", "降维模型", "自动编码器", "可微求解器", "数据同化",
    "多保真数据", "流场智能预测", "智能流动控制",
]


# ``FLUID_RELATED_TERMS`` is deliberately broad because it is also used for
# general site navigation and non-ML fluid classification.  It contains terms
# such as "数值模拟" and "降水" that are useful in that setting, but are not
# enough to prove that a machine-learning paper is about CFD.  The Chinese
# portal intake must use this narrower gate, otherwise a query like
# "计算力学学报 + 神经网络" admits structural- or geotechnical-mechanics
# papers before their abstracts have been enriched.
INTELLIGENT_CFD_CONTEXT_TERMS = [
    "cfd", "computational fluid dynamics", "fluid dynamics", "fluid mechanics",
    "navier-stokes", "flow field", "flow simulation", "turbulence", "rans", "les", "dns",
    "aerodynamics", "aerodynamic", "airfoil", "compressible flow", "multiphase flow",
    "计算流体力学", "流体力学", "流体动力学", "流场", "流动", "湍流", "雷诺平均",
    "大涡模拟", "直接数值模拟", "空气动力学", "气动", "翼型", "可压缩流", "激波",
    "多相流", "两相流", "纳维斯托克斯", "格子玻尔兹曼", "绕流", "尾流", "边界层",
]


def is_intelligent_cfd_paper(paper: Dict) -> bool:
    """Strict admission gate: a real fluid/CFD problem AND an intelligent method."""
    text = paper_text(paper)
    return (
        contains_any(text, INTELLIGENT_METHOD_TERMS)
        and contains_any(text, INTELLIGENT_CFD_CONTEXT_TERMS)
    )


# ═══════════════════════════════════════════════════════════
#  论文分类
# ═══════════════════════════════════════════════════════════


def classify_paper(paper: Dict, config: Dict) -> List[str]:
    """Classify into the smallest CFD/fluid subdomain using strict scored rules."""
    text = paper_text(paper)
    ordered_tags = []
    categories = config.get("categories", {})

    def add_tag(category_name: str):
        if category_name in categories and category_name not in ordered_tags:
            ordered_tags.append(category_name)

    has_fluid = contains_any(text, FLUID_RELATED_TERMS) or any(
        str(cat).lower() in FLUID_RELATED_CATEGORIES
        for cat in paper.get("categories", []) or []
    )
    has_ml = contains_any(text, INTELLIGENT_METHOD_TERMS)

    if has_ml:
        add_tag("机器学习")
    if has_fluid:
        add_tag("流体力学")
    if has_fluid and has_ml:
        add_tag("流体力学 / 智能CFD")
    if not has_fluid:
        paper["classification_score"] = {}
        return ordered_tags

    scores = {}
    has_fluid_context = contains_any(text, FLUID_RELATED_TERMS) or any(
        str(cat).lower() in FLUID_RELATED_CATEGORIES
        for cat in paper.get("categories", []) or []
    )
    if has_fluid_context:
        for label, rule in SUBDOMAIN_RULES.items():
            strong_hits = [term for term in rule["strong"] if term_in_text(text, term)]
            context_hits = [term for term in rule["context"] if term_in_text(text, term)]
            negative_hits = [term for term in rule.get("negative", []) if term_in_text(text, term)]
            score = len(strong_hits) * 3 + len(context_hits) - len(negative_hits) * 4
            if "智能CFD" in label and not context_hits:
                score -= 3
            if strong_hits and score >= 3:
                scores[label] = {
                    "score": score,
                    "strong_hits": strong_hits[:8],
                    "context_hits": context_hits[:8],
                    "negative_hits": negative_hits[:5],
                }

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


# ═══════════════════════════════════════════════════════════
#  关键词提取
# ═══════════════════════════════════════════════════════════


def extract_paper_keywords(paper: Dict, config: Dict) -> List[str]:
    """
    提取「自定义预设关键词」（原有逻辑，仅做注释优化）
    """
    # 拼接标题+摘要，转小写（统一匹配）
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    all_keywords = []

    # 收集你yaml中所有分类的关键词（包含新增的中英文）
    categories = config.get("categories", {})
    for cat_info in categories.values():
        all_keywords.extend([kw.lower() for kw in cat_info.get("keywords", [])])

    # 提取文本中存在的关键词（去重）
    extracted = list({kw for kw in all_keywords if term_in_text(text, kw)})

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
        if term_in_text(text, kw) and kw.lower() not in extracted:
            extracted.append(kw.lower())

    # 最多保留10个关键词（适配新增词汇，多保留2个）
    return extracted[:10]


def normalize_keywords(keywords: List[str]) -> List[str]:
    """将同义关键词合并为规范缩写形式，去重并排序"""
    normalized = set()
    for kw in keywords:
        canonical = KEYWORD_CANONICAL.get(kw.lower().strip(), kw)
        normalized.add(canonical)
    return sorted(normalized)


def extract_official_keywords(result) -> List[str]:
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


# ═══════════════════════════════════════════════════════════
#  分类报告
# ═══════════════════════════════════════════════════════════


def write_classification_report(papers, output_dir):
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
    path = os.path.join(output_dir, "classification_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"分类验证报告已保存到: {path}")
