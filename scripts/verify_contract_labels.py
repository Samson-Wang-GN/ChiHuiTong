#!/usr/bin/env python3
"""Server-only legacy prototype terminology smoke; not new-flow acceptance."""

import functools
import http.server
import json
import os
from pathlib import Path
import socket
import threading
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright


def main():
    root = Path('/home/ubuntu/ChiHuiTong')
    release = Path(__file__).resolve().parents[1]
    if socket.gethostname() != 'VM-0-12-ubuntu' or release.parent != root / 'releases':
        raise SystemExit('Only verified release on authorized development server')
    os.umask(0o077)
    report = root / 'test-results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-contract-labels')
    report.mkdir()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(release / 'prototypes'))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    result = {'commit': release.name, 'passed': False, 'roles': {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for name in ['clinic-mini/app.js', 'clinic-mini/finance.js', 'platform/institutions.js', 'shared/tasks.js', 'shared/workflows.js']:
                page.evaluate('source => { new Function(source) }', (release / 'prototypes' / name).read_text())
            for role in ['platform', 'resource', 'channel', 'clinic']:
                base = f'http://127.0.0.1:{server.server_port}/{role}/'
                page.goto(base)
                page.wait_for_selector('.workspace h1')
                routes = page.evaluate('window.PROTOTYPE.pages.filter(p => !p.hidden).map(p => p.id)')
                for route in routes:
                    page.goto(base + '#' + route)
                    page.wait_for_timeout(100)
                    assert '三方合同' not in page.locator('body').inner_text(), (role, route)
                result['roles'][role] = len(routes)
                page.screenshot(path=str(report / (role + '.png')), full_page=True)
            assert not errors, errors
            browser.close()
        result['passed'] = True
    finally:
        server.shutdown()
        server.server_close()
        (report / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print('LABEL_REPORT=' + str(report / 'summary.json'))


if __name__ == '__main__':
    main()
