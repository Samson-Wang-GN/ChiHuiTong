#!/usr/bin/env python3
"""Low-volume real map UI verification on the authorized server; no clinic saves."""

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
        raise SystemExit('Only the authorized development server')
    os.umask(0o077)
    runtime = ROOT / 'runtime/acceptance'
    creds = json.loads((runtime / 'access.json').read_text())
    key = json.loads((runtime / 'environment.json').read_text())['CHT_TENCENT_MAP_KEY']
    output = ROOT / 'test-results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-map-browser')
    output.mkdir()
    report = {'passed': False, 'checks': [], 'clinic_changes_submitted': False}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for role in ['channel', 'resource']:
                context = browser.new_context(http_credentials=creds, viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
                page = context.new_page()
                urls, errors, previews, writes = [], [], [], []
                page.on('request', lambda request: urls.append(request.url))
                page.on('pageerror', lambda error: errors.append(type(error).__name__))

                def record(request):
                    if request.url.endswith('/clinics/map-preview'):
                        previews.append(request.post_data_json)
                    if request.method == 'POST' and (request.url.endswith('/clinics') or '/profile-changes' in request.url):
                        writes.append(True)

                page.on('request', record)
                page.goto(BASE + '/' + role + '/', wait_until='networkidle')
                page.get_by_role('button', name='获取验证码', exact=True).click()
                page.get_by_role('button', name='查看测试短信箱', exact=True).click()
                message = page.get_by_text('本次验证码：', exact=False)
                message.wait_for()
                code = re.search(r'本次验证码：(\d{6})', message.inner_text()).group(1)
                page.get_by_label('验证码', exact=True).fill(code)
                page.get_by_role('button', name='登录', exact=True).click()
                page.get_by_role('button', name='退出登录', exact=True).wait_for()
                if role == 'channel':
                    page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^门诊管理$')).click()
                    page.get_by_role('button', name='新增门诊', exact=True).click()
                    for label, value in [('省 / 直辖市', '北京市'), ('城市', '北京市'), ('区 / 县', '海淀区'), ('经营地址', '中关村大街1号')]:
                        page.get_by_label(label, exact=True).fill(value)
                    with page.expect_response(lambda r: r.url.endswith('/clinics/geocode'), timeout=30000) as response:
                        page.get_by_role('button', name='按地址定位', exact=True).click()
                    assert response.value.status == 200
                    assert key not in response.value.text()
                    pic = page.get_by_alt_text('腾讯地图真实底图，点击选择门诊位置')
                    expect(pic).to_be_visible(timeout=30000)
                    confirm = page.get_by_role('button', name='确认中心标记为门诊位置', exact=True)
                    expect(confirm).to_be_enabled()
                    assert pic.evaluate('(img) => img.complete && img.naturalWidth === 600')
                    initial = previews[-1].copy()
                    with page.expect_response(lambda r: r.url.endswith('/clinics/map-preview'), timeout=30000) as moved:
                        pic.click(position={'x': 380, 'y': 210})
                    assert moved.value.status == 200
                    expect(confirm).to_be_enabled()
                    assert previews[-1]['longitude'] != initial['longitude']
                    assert previews[-1]['latitude'] != initial['latitude']
                    expect(pic).to_be_visible()
                    pic.screenshot(path=str(output / 'public-place-map.png'), animations='disabled')
                    confirm.click()
                    expect(page.get_by_text('已确认门诊位置；地址改变后须重新定位。', exact=True)).to_be_visible()
                    assert key not in page.content()
                    page.get_by_role('button', name='取消', exact=True).last.click()
                    assert not writes
                    report['checks'].append({'channel_address_lookup': True, 'real_png': True, 'map_click_changes_coordinates': True, 'form_confirmation': True, 'cancel_without_saving': True})
                else:
                    denied = page.evaluate("""async () => {
                        const result = [];
                        for (const path of ['/api/v1/clinics/geocode', '/api/v1/clinics/map-preview']) {
                            try { await CHT.api(path, 'POST', {}); result.push(200); }
                            catch (error) { result.push(error.status); }
                        }
                        return result;
                    }""")
                    assert denied == [403, 403]
                    report['checks'].append({'resource_map_access_denied': True})
                assert not errors
                assert all(key not in url and 'apis.map.qq.com' not in url for url in urls)
                report['checks'].append({'role': role, 'browser_key_not_exposed': True, 'javascript_errors': 0})
                page.get_by_role('button', name='退出登录', exact=True).click()
                context.close()
            browser.close()
        report['passed'] = True
    except Exception as exc:
        # Browser exceptions may include request details; never emit raw exceptions.
        report['error_type'] = type(exc).__name__
    finally:
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('MAP_BROWSER_REPORT=' + str(output / 'summary.json'))
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
