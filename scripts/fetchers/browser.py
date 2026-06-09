"""Chrome DevTools Protocol 浏览器自动化工具"""
import json
import os
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def cdp_base_url(config: dict, source_config: dict) -> str:
    """获取 Chrome DevTools Protocol 基础 URL"""
    return (
        source_config.get("browser_url")
        or config.get("browser", {}).get("chrome_devtools_url")
        or os.environ.get("CHROME_DEVTOOLS_URL")
        or "http://127.0.0.1:9222"
    ).rstrip("/")


def evaluate_in_chrome(url: str, script: str, source_name: str, config: dict, source_config: dict) -> Optional[dict]:
    """通过 Chrome DevTools Protocol 执行 DOM 提取脚本"""
    timeout = int(source_config.get("browser_timeout", config.get("browser", {}).get("timeout", 30)))
    ws = None
    tab_id = None
    try:
        import websocket
    except ImportError:
        logger.info(f"{source_name} browser backend requires websocket-client; falling back.")
        return None

    base_url = cdp_base_url(config, source_config)
    try:
        new_tab = requests.put(f"{base_url}/json/new?about:blank", timeout=10)
        if new_tab.status_code not in (200, 201):
            logger.info(f"{source_name} Chrome DevTools unavailable at {base_url}: {new_tab.status_code}")
            return None

        tab = new_tab.json()
        tab_id = tab.get("id")
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            logger.info(f"{source_name} Chrome target has no websocket URL.")
            return None

        ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        message_id = 1
        ws.send(json.dumps({"id": message_id, "method": "Page.enable"}))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") == message_id:
                break

        message_id += 1
        ws.send(json.dumps({
            "id": message_id,
            "method": "Page.navigate",
            "params": {"url": url},
        }))
        while True:
            message = json.loads(ws.recv())
            if message.get("method") == "Page.loadEventFired":
                break
            if message.get("id") == message_id and "error" in message:
                logger.warning(f"{source_name} browser navigation failed: {message['error']}")
                return None

        message_id += 1
        ws.send(json.dumps({
            "id": message_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": f"({script})()",
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": timeout * 1000,
            },
        }))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") != message_id:
                continue
            if "exceptionDetails" in message:
                logger.warning(f"{source_name} browser extraction script failed: {message['exceptionDetails']}")
                return None
            result = message.get("result", {}).get("result", {})
            if "value" in result:
                return result["value"]
            if result.get("type") == "undefined":
                return {}
            logger.warning(f"{source_name} browser extraction returned non-JSON result: {result}")
            return None
    except Exception as e:
        logger.info(f"{source_name} browser backend unavailable, falling back: {e}")
        return None
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        if tab_id:
            try:
                requests.get(f"{base_url}/json/close/{tab_id}", timeout=5)
            except Exception:
                pass
