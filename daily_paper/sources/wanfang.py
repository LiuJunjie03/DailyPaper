"""Wanfang Data Chinese literature source."""

from daily_paper.sources.chinese_html import fetch_chinese_html_source


def fetch_wanfang_papers(config, ss_api_key: str = "", arxiv_client=None):
    return fetch_chinese_html_source(
        top_config=config,
        source_key="wanfang",
        source_label="万方",
        default_url="https://s.wanfangdata.com.cn/paper",
        prefix="wanfang",
    )
