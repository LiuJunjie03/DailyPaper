import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetchers.cnki import _absolute_cnki_url, _cnki_url


def test_cnki_urls_can_use_proxy_base():
    config = {
        "home_url": "http://www--cnki--net--https.example.edu:9000/",
        "kns_base_url": "http://kns--cnki--net--https.example.edu:9000/",
    }

    assert _cnki_url(config, "search_page_url", "/kns8s/search") == (
        "http://kns--cnki--net--https.example.edu:9000/kns8s/search"
    )
    assert _cnki_url(config, "home_url", "/") == "http://www--cnki--net--https.example.edu:9000/"
    assert _absolute_cnki_url(config, "/kcms2/article/abstract?v=1") == (
        "http://kns--cnki--net--https.example.edu:9000/kcms2/article/abstract?v=1"
    )
