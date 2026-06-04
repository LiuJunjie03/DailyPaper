# DailyPaper - CFD/流体力学论文自动汇总工具

![GitHub Pages](https://img.shields.io/badge/GitHub-Pages-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

每天自动汇总流体力学/CFD + 机器学习领域的最新论文，节省你的检索时间！

## 🎯 功能特点

- ✨ **自动更新**：每天自动抓取最新论文
- 📚 **多源聚合**：支持 ArXiv、顶级会议、期刊等多个数据源
- 🔍 **智能分类**：按研究领域自动分类（多相流、空气动力学、CFD+ML 等）
- 🎨 **美观展示**：响应式网页设计，支持搜索和筛选
- 🔗 **快速访问**：论文原文直接链接

## 📖 支持的数据源

- **ArXiv**：`physics.flu-dyn`（流体动力学）
- **会议**：NeurIPS, ICML, ICLR, AIAA SciTech Forum 等
- **期刊**：JCP, Physics of Fluids, Journal of Fluid Mechanics, AIAA Journal 等

## 🚀 快速开始

### 本地运行

```bash
# 克隆项目
git clone https://github.com/LiuJunjie03/DailyPaper.git
cd DailyPaper

# 安装依赖
pip install -r requirements.txt

# 运行爬虫
python scripts/fetch_papers.py

# 生成网页
python scripts/generate_html.py
```

### 部署到 GitHub Pages

**快速部署（推荐）：**
```powershell
# 运行一键部署脚本
.\deploy.ps1
```

**手动部署：**
1. 在 GitHub 创建新仓库（名为 `DailyPaper`，Public）
2. 将代码推送到 GitHub
3. 在 Settings > Pages 中配置：Source = `gh-pages` 分支
4. 在 Settings > Actions > General 中配置权限：Read and write
5. 在 Actions 中手动运行 "Update Papers Daily"
6. 访问 `https://liujunjie03.github.io/DailyPaper/`

**详细步骤请查看：[DEPLOYMENT.md](DEPLOYMENT.md)**

## 📁 项目结构

```
DailyPaper/
├── .github/
│   └── workflows/
│       └── update-papers.yml    # GitHub Actions 自动化脚本
├── scripts/
│   ├── fetch_papers.py          # 论文抓取脚本
│   ├── generate_html.py         # 生成静态页面
│   ├── update_venue.py          # 会议/期刊标签更新
│   └── utils.py                 # 工具函数
├── data/
│   ├── index.json               # 月份索引
│   └── YYYY-MM.json             # 按月存储的论文数据
├── docs/                        # GitHub Pages 源文件
│   ├── index.html
│   ├── data/                    # 数据部署副本
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
├── config.yaml                  # 核心配置文件
└── requirements.txt
```

## ⚙️ 配置

编辑 `config.yaml` 文件来自定义：

```yaml
# 抓取配置
sources:
  arxiv:
    enabled: true
    categories:
      - physics.flu-dyn
    max_results: 1000
    days_back: 60

# 领域分类
categories:
  多相流:
    keywords: [multiphase flow, two-phase flow, VOF, ...]
  空气动力学:
    keywords: [aerodynamics, drag reduction, ...]
  CFD与机器学习交叉:
    keywords: [CFD, machine learning, PINN, ...]
  # ...

# 更新频率
schedule:
  cron: "0 0 * * *"  # 每天 UTC 0:00
```

## 📊 数据来源

- [ArXiv](https://arxiv.org/) - 开放获取的预印本论文库

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

感谢所有开源数据源提供者和贡献者！

## ⭐ Star History

如果这个项目对你有帮助，请给个 Star ⭐️
