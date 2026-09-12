#!/usr/bin/env python3
"""Compile first-party browser modules using server Chromium, without executing them."""

import json
import socket
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    if socket.gethostname() != "VM-0-12-ubuntu":
        raise SystemExit("仅允许指定开发服务器运行")
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "backend/chihuitong/acceptance_assets").glob("*.js"))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        results = []
        for source in files:
            error = page.evaluate(
                "source => {try { new Function(source); return null; } catch(e) { return e.message; }}",
                source.read_text(),
            )
            results.append({"module": source.name, "error": error})
        browser.close()
    print(json.dumps(results, ensure_ascii=False))
    if any(item["error"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
