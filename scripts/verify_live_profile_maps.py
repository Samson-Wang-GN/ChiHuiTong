"""Read-only real HTTPS saved-map checks on the approved acceptance server."""

import json
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path('/home/ubuntu/ChiHuiTong')
BASE = 'https://dev-public.chihui-ai.com/chihuitong'


def main():
    if socket.gethostname() != 'VM-0-12-ubuntu':
        raise SystemExit('Only approved development server')
    os.umask(0o077)
    runtime = ROOT / 'runtime/acceptance'
    credentials = json.loads((runtime / 'access.json').read_text())
    key = json.loads((runtime / 'environment.json').read_text())['CHT_TENCENT_MAP_KEY']
    output = ROOT / 'test-results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-live-profile-maps')
    output.mkdir()
    report = {'passed': False, 'roles': [], 'business_writes': 0}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for role in ['platform', 'channel', 'clinic']:
                report['stage'] = role + '_login'
                context = browser.new_context(http_credentials=credentials, viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors, requests = [], []
                page.on('pageerror', lambda error: errors.append(type(error).__name__))
                page.on('request', lambda request: requests.append(request))
                page.goto(BASE + '/' + role + '/', wait_until='networkidle')
                page.get_by_role('button', name='获取验证码', exact=True).click()
                page.get_by_role('button', name='查看测试短信箱', exact=True).click()
                text = page.get_by_text('本次验证码：', exact=False)
                text.wait_for()
                code = re.search(r'本次验证码：(\d{6})', text.inner_text()).group(1)
                page.get_by_label('验证码', exact=True).fill(code)
                if role == 'clinic':
                    page.get_by_text('登录时开启预约提醒', exact=True).click()
                page.get_by_role('button', name='登录', exact=True).click()
                page.get_by_role('button', name='退出登录', exact=True).wait_for()
                clinics = page.evaluate('() => CHT.api("/api/v1/clinics")')['results']
                assert clinics
                clinic = clinics[0]
                changes = page.evaluate('(id) => CHT.api("/api/v1/clinics/" + id + "/profile-changes?status=pending")', clinic['id'])['results']
                report['stage'] = role + '_details'
                page.evaluate('(id) => CHT.open("clinic", {id})', clinic['id'])
                if changes and changes[0]['after'].get('location', {}).get('status') == 'confirmed':
                    expect(page.get_by_text('新位置已确认，等待平台审核；', exact=False)).to_be_visible()
                    pic = page.get_by_alt_text('本次申请位置腾讯地图')
                    expect(pic).to_be_visible(timeout=20000)
                    expect(pic).to_have_js_property('naturalWidth', 600)
                    pic.screenshot(path=str(output / (role + '-pending-map.png')))
                elif clinic['profile'].get('location', {}).get('status') == 'confirmed':
                    expect(page.get_by_alt_text('当前生效位置腾讯地图')).to_be_visible(timeout=20000)
                else:
                    raise AssertionError('No saved location available for real verification')
                page.get_by_role('button', name='关闭详情', exact=True).last.click()
                if changes:
                    report['stage'] = role + '_comparison'
                    page.evaluate('([row, clinic]) => CHT.open("profileChange", {row, clinic})', [changes[0], clinic])
                    for snapshot, title in [('before', '原资料位置'), ('after', '本次申请位置')]:
                        if changes[0][snapshot].get('location', {}).get('status') == 'confirmed':
                            expect(page.get_by_alt_text(title + '腾讯地图')).to_be_visible(timeout=20000)
                    page.locator('.location-comparison').screenshot(path=str(output / (role + '-comparison.png')))
                    page.set_viewport_size({'width': 768, 'height': 1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    page.get_by_role('button', name='关闭详情', exact=True).last.click()
                assert not errors
                assert key not in page.content()
                assert all(key not in request.url and 'apis.map.qq.com' not in request.url for request in requests)
                mutations = [request for request in requests if request.method == 'POST' and ('/profile-changes' in request.url or request.url.endswith('/review'))]
                assert not mutations
                report['roles'].append({'role': role, 'detail_map': True, 'comparison': bool(changes), 'key_private': True, 'script_errors': 0})
                page.get_by_role('button', name='退出登录', exact=True).click()
                context.close()
            browser.close()
        report['passed'] = True
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    finally:
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('LIVE_MAP_REPORT=' + str(output / 'summary.json'))
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
