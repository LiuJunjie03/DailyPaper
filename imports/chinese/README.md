# 中文数据库人工导入区

将知网、万方、维普的检索结果放到此目录，再运行：

```powershell
python scripts\collect_chinese_papers.py
```

支持 RIS、EndNote (`.enw`)、RefWorks (`.txt` / `.refworks`)、CSV、XLSX，以及浏览器保存的 HTML。
导出文件可能包含机构访问链接或个人检索信息，默认不会提交到 Git；本文件除外。
