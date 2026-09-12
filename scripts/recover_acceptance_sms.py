#!/usr/bin/env python3
"""Recover only legacy disabled-template simulation jobs through the platform UI."""

import json
import os
from pathlib import Path
import re
import socket
import time

from playwright.sync_api import sync_playwright

ROOT = Path('/home/ubuntu/ChiHuiTong')
if socket.gethostname() != 'VM-0-12-ubuntu':
    raise SystemExit('Only authorized development server')
os.umask(0o077)
runtime = ROOT/'runtime/acceptance'
cfg = json.loads((runtime/'environment.json').read_text())
assert cfg['CHT_ACCEPTANCE_SIMULATED_EXTERNALS'] == 'true'
assert cfg['CHT_WECHAT_PAY_ENABLED'] == 'false'
assert cfg['CHT_ENVIRONMENT'] == 'development'
assert cfg['CHT_DB_NAME'] == 'chihuitong_acceptance'
assert cfg['CHT_SMS_BACKEND'] == 'chihuitong.acceptance.AcceptanceSMS'
creds = json.loads((runtime/'access.json').read_text())
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(http_credentials=creds, viewport={'width':1440,'height':1000})
    page = context.new_page()
    page.goto('https://dev-public.chihui-ai.com/chihuitong/platform/', wait_until='networkidle')
    page.get_by_role('button', name='获取验证码', exact=True).click()
    page.get_by_role('button', name='查看测试短信箱', exact=True).click()
    message = page.get_by_text('本次验证码：', exact=False)
    message.wait_for()
    code = re.search(r'本次验证码：(\d{6})', message.inner_text()).group(1)
    page.get_by_label('验证码', exact=True).fill(code)
    page.get_by_role('button', name='登录', exact=True).click()
    page.get_by_role('button', name='退出登录', exact=True).wait_for()
    def failed():
        return page.evaluate("async()=>await CHT.api('/api/v1/jobs?status=failed&page_size=100')")['results']
    old = failed()
    assert len(old) <= 9
    assert all(x['kind']=='sms.business' and x['last_error_code']=='sms_template_unavailable' for x in old)
    page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^系统任务$')).click()
    page.get_by_role('tab', name=re.compile('^失败')).click()
    for _ in old:
        page.locator('.arco-table-tr').filter(has_text='sms_template_unavailable').first.get_by_role('button', name='详情', exact=True).click()
        page.get_by_role('button', name='重试任务', exact=True).click()
        page.get_by_label('操作原因', exact=True).fill('REQ-045已启用显式模拟模板，恢复旧模板未启用任务；无真实发送')
        with page.expect_response(lambda response: '/jobs/' in response.url and response.url.endswith('/retry')) as retried:
            page.locator('.arco-modal:visible').get_by_role('button', name='保存', exact=True).click()
        assert retried.value.status == 200
        page.get_by_role('button', name='关闭详情', exact=True).click()
        page.wait_for_timeout(400)
    deadline = time.monotonic()+100
    while time.monotonic() < deadline:
        rows = page.evaluate("async()=>await CHT.api('/api/v1/jobs?page_size=100')")['results']
        targets = [x for x in rows if x['id'] in {j['id'] for j in old}]
        if all(x['status']=='done' for x in targets) and len(targets)==len(old):
            break
        page.wait_for_timeout(1000)
    else:
        raise RuntimeError('Simulation jobs did not recover; inspect aggregate status')
    page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^工作台$')).click()
    page.wait_for_timeout(600)
    result = {'recovered_simulation_jobs':len(old),'via_platform_ui':True,'no_real_sms':True,'original_jobs_retained':True}
    (runtime/'sms-recovery.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    page.get_by_role('button', name='退出登录', exact=True).click()
    browser.close()
