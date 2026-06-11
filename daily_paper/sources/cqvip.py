"""CQVIP/VIP Chinese literature source."""

from daily_paper.sources.chinese_html import fetch_chinese_html_source


def fetch_cqvip_papers(config, ss_api_key: str = "", arxiv_client=None):
    return fetch_chinese_html_source(
        top_config=config,
        source_key="cqvip",
        source_label="维普",
        default_url="https://www.cqvip.com/search",
        prefix="cqvip",
    )
