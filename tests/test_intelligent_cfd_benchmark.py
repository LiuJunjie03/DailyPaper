"""Regression benchmark assembled from verified Chinese journal article pages."""

from daily_paper.classify import is_intelligent_cfd_paper

BENCHMARK_PAPERS = [
    {"title": "基于神经算子的湍流模拟方法"},
    {"title": "卷积神经网络在流场重构研究中的进展"},
    {"title": "融合物理的神经网络方法在流场重建中的应用"},
    {"title": "物理方程约束的机器学习流场时程表征方法"},
    {"title": "一种求解非定常可压缩流动的流场信息融合的图神经网络方法"},
    {"title": "基于PINN的二维剪切流圆柱绕流场重构"},
    {"title": "基于深度神经网络的流场时空重构方法"},
    {"title": "机器学习技术在气动优化中的应用"},
    {"title": "基于深度神经网络的高速翼型流场降阶模型"},
    {"title": "基于深度学习的非定常周期性流动预测方法"},
    {"title": "基于深度学习的超分辨率重构方法在CAARC标模绕流流场重构中的应用"},
    {"title": "自动编码器在流场降阶中的应用"},
    {"title": "基于机器学习的高速复杂流场流动控制效果预测分析"},
    {"title": "基于物理信息神经网络的飞机气动参数辨识方法"},
    {
        "title": "基于稀疏神经核的多保真度代理模型",
        "abstract": "将多保真代理模型应用于 NACA0012 翼型阻力系数的气动预测。",
    },
    {"title": "基于深度神经网络的高阶非线性激波判别式"},
    {"title": "基于物理约束深度学习的大跨柔性光伏阵列绕流场重构"},
    {
        "title": "基于柔性智能蒙皮的翼型流场预测和重建方法",
        "abstract": "采用编码器-解码器深度神经网络预测翼型周围二维流场。",
    },
    {
        "title": "基于二维局部掩码自监督的三维流场全局重构",
        "abstract": "提出自监督深度学习模型重构三维流场。",
    },
    {
        "title": "工况感知驱动的层次化点云流场预测网络",
        "abstract": "提出点云深度学习网络，替代 CFD 进行高速飞行器表面流场预测。",
    },
]


def test_verified_chinese_intelligent_cfd_benchmark_has_full_gate_recall():
    """The curated 20-paper benchmark is the minimum regression floor."""
    accepted = [
        paper
        for paper in BENCHMARK_PAPERS
        if is_intelligent_cfd_paper({**paper, "venue": "中文核心期刊"})
    ]
    assert len(accepted) / len(BENCHMARK_PAPERS) >= 0.8
    assert len(accepted) == len(BENCHMARK_PAPERS)


def test_geotechnical_pinn_is_not_mistaken_for_intelligent_cfd():
    paper = {
        "title": "物理信息神经网络方法求解一维非饱和土柱降雨入渗问题",
        "abstract": "采用神经网络和数值模拟研究土壤入渗规律。",
        "venue": "计算力学学报",
    }
    assert not is_intelligent_cfd_paper(paper)
