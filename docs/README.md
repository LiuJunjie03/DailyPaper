# docs/ — 构建产物目录

**⚠️ 本目录下所有文件均由 `scripts/generate_html.py` 自动生成，请勿手工编辑。**

## 目录结构

```
docs/
├── index.html          # 主页（由 Jinja2 模板渲染）
├── css/style.css       # 样式（从 scripts/templates/style.css 复制）
├── js/main.js          # 前端脚本（从 scripts/templates/main.js 复制）
└── data/               # 月度论文数据（从 data/ 同步）
    ├── index.json      # 月份索引
    └── YYYY-MM.json    # 按月存储的论文数据
```

## 生成方式

```bash
python scripts/generate_html.py
```

## 部署

本目录通过 GitHub Actions 自动部署到 GitHub Pages（`gh-pages` 分支）。
