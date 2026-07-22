# 智能 CFD 中英文期刊监测清单

## 筛选依据

本清单不是简单复制“核心期刊”目录，而按实际检索价值分层：

1. 论文必须长期覆盖流体力学、计算方法、航空航天、传热多相流或科学机器学习之一。
2. 优先收录已经出现 PINN（物理信息神经网络）、神经算子、代理模型、湍流闭合、流场重建、强化学习流动控制等论文的期刊。
3. 自动化层面优先选择有稳定官网目录、规范元数据、DOI 或 RIS/EndNote 导出的来源。
4. “核心”在本项目中表示重点监测，不等价于某一年度的北大核心、CSCD 或 EI 名单；数据库收录状态会变化，应另行核验。

## 中文期刊（15 种）

| 层级 | 期刊 | 主要价值 | 当前采集方式 |
|---|---|---|---|
| A | 空气动力学学报 | 气动代理模型、流场预测、智能优化 | 官网自动 |
| A | 力学学报 | 湍流建模、神经算子、机器学习力学专题 | 官网自动 |
| A | 计算力学学报 | 数值方法、PINN、降阶模型 | 官网自动 |
| A | 航空学报 | 飞行器气动、多保真代理与优化 | 官网自动 |
| A | 计算物理 | 科学计算、学习增强数值方法 | 人工导出兜底 |
| B | 工程力学 | 物理约束流场表征、工程流体交叉 | 官网自动 |
| B | 实验流体力学 | 流场测量、重建和数据驱动控制 | 官网自动 |
| B | 力学进展 | 智能流体综述与方法进展 | 官网自动 |
| B | 物理学报 | 复杂流动、格子玻尔兹曼、物理机器学习 | 官网自动 |
| B | 中国舰船研究 | 船舶水动力与智能优化 | 官网自动 |
| B | 流体机械 | 叶轮机械流动、故障预测和优化 | 官网自动/人工导出 |
| B | 化工学报 | 多相流、反应流、传热与数据驱动模型 | 人工导出兜底 |
| B | 机械工程学报 | 流体机械、热流体及智能设计 | 人工导出兜底 |
| B | 系统仿真学报 | 降阶模型、数字孪生和快速仿真 | 人工导出兜底 |
| B | 推进技术 | 发动机流动、燃烧与气动智能建模 | 人工导出兜底 |

## 英文期刊（15 种）

| 层级 | 期刊 | 主要价值 |
|---|---|---|
| A | Journal of Computational Physics | 学习增强离散、神经算子、可微分求解器 |
| A | Computer Methods in Applied Mechanics and Engineering | PINN、算子学习、计算力学方法 |
| A | Computers & Fluids | 智能 CFD 工程应用与求解加速 |
| A | Physics of Fluids | 数据驱动湍流、流场重建和流动控制 |
| A | Journal of Fluid Mechanics | 流动物理与数据驱动方法的高水平成果 |
| A | International Journal for Numerical Methods in Fluids | 数值流体方法与机器学习增强算法 |
| A | Engineering Applications of Computational Fluid Mechanics | CFD 工程应用和代理建模 |
| B | Theoretical and Computational Fluid Dynamics | 湍流、降阶与计算流体理论 |
| B | AIAA Journal | 航空气动、代理模型和气动优化 |
| B | Journal of Machine Learning for Modeling and Computing | 科学机器学习与计算建模 |
| B | Machine Learning: Science and Technology | 科学机器学习通用方法及流体应用 |
| B | Data-Centric Engineering | 数据同化、数字孪生和工程代理模型 |
| B | International Journal of Heat and Fluid Flow | 热流体、湍流与数据驱动建模 |
| B | Flow, Turbulence and Combustion | 湍流闭合、燃烧与学习模型 |
| B | Computer Physics Communications | 科学计算软件、加速器和可复现工具 |

## 主题检索词

只用“智能 CFD”会严重漏检。检索式至少组合一个流体词和一个智能方法词：

- 流体词：计算流体力学、流体力学、流场、湍流、RANS、LES、气动、多相流、两相流、燃烧、传热、格子玻尔兹曼。
- 方法词：机器学习、深度学习、神经网络、物理信息神经网络、神经算子、代理模型、降阶模型、数据同化、流场重建、强化学习、多保真、可微分求解器。
- 排除词：仅涉及交通流、金融流、网络流，且没有真实流体或偏微分方程数值问题的论文。
