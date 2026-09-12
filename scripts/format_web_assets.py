#!/usr/bin/env python3
"""Server-only formatting in an isolated artifact directory, without Node or source mutation."""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import tarfile
import urllib.request
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ROOT = Path('/home/ubuntu/ChiHuiTong')
VERSION = '3.6.2'


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read(limit+1)
    if len(body) > limit:
        raise RuntimeError('Package size exceeds expected limit')
    return body


def main():
    release = Path(__file__).resolve().parents[1]
    if socket.gethostname() != 'VM-0-12-ubuntu' or release.parent != ROOT/'releases':
        raise SystemExit('Only verified server release')
    os.umask(0o077)
    report = ROOT/'test-results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+release.name[:12]+'-web-format')
    report.mkdir()
    metadata = json.loads(fetch('https://registry.npmjs.org/prettier/'+VERSION, 1024*1024))
    archive = fetch('https://registry.npmjs.org/prettier/-/prettier-'+VERSION+'.tgz', 25*1024*1024)
    integrity = 'sha512-'+base64.b64encode(hashlib.sha512(archive).digest()).decode()
    if metadata['version'] != VERSION or metadata['dist']['integrity'] != integrity:
        raise RuntimeError('Prettier package integrity mismatch')
    scripts = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as package:
        for name in ['standalone.js', 'plugins/babel.js', 'plugins/estree.js', 'plugins/postcss.js', 'plugins/html.js']:
            member = package.getmember('package/'+name)
            if not member.isfile() or member.size > 10*1024*1024:
                raise RuntimeError('Unexpected package entry')
            scripts[name] = package.extractfile(member).read().decode()
    assets = release/'backend/chihuitong/acceptance_assets'
    changes = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        for source in scripts.values():
            page.add_script_tag(content=source)
        for path in sorted(assets.iterdir()):
            if path.suffix not in {'.js', '.css', '.html'}:
                continue
            parser = {'.js':'babel', '.css':'css', '.html':'html'}[path.suffix]
            formatted = page.evaluate('async data => prettier.format(data.source, {parser:data.parser, plugins:prettierPlugins, singleQuote:true, printWidth:100})', {'source':path.read_text(), 'parser':parser})
            if path.suffix == '.js':
                page.evaluate('source => {new Function(source)}', formatted)
            (report/path.name).write_text(formatted)
            changes.append({'file':path.name, 'before':hashlib.sha256(path.read_bytes()).hexdigest(), 'after':hashlib.sha256(formatted.encode()).hexdigest()})
        browser.close()
    (report/'summary.json').write_text(json.dumps({'commit':release.name, 'formatter':'prettier@'+VERSION, 'integrity':integrity, 'files':changes}, indent=2))
    print('FORMAT_REPORT='+str(report/'summary.json'))


if __name__ == '__main__':
    main()
