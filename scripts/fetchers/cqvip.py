"""CQVIP/VIP Chinese literature source."""

from fetchers.chinese_html import fetch_chinese_html_source


def fetch_cqvip_papers(fetcher):
    return fetch_chinese_html_source(
        fetcher=fetcher,
        source_key="cqvip",
        source_label="维普",
        default_url="https://www.cqvip.com/search",
        prefix="cqvip",
    )
