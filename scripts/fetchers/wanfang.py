"""Wanfang Data Chinese literature source."""

from fetchers.chinese_html import fetch_chinese_html_source


def fetch_wanfang_papers(fetcher):
    return fetch_chinese_html_source(
        fetcher=fetcher,
        source_key="wanfang",
        source_label="万方",
        default_url="https://s.wanfangdata.com.cn/paper",
        prefix="wanfang",
    )
