#!/usr/bin/env python3
"""Real HTTPS and browser checks on the approved server. Never prints credentials/OTP."""

import json
import os
from pathlib import Path
import socket
from datetime import datetime, timezone
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path('/home/ubuntu/ChiHuiTong')
BASE = 'https://dev-public.chihui-ai.com/chihuitong'


def main():
    if socket.gethostname() != 'VM-0-12-ubuntu':
        raise SystemExit('Only the authorized development server')
    os.umask(0o077)
    runtime=ROOT/'runtime'/'acceptance'
    creds=json.loads((runtime/'access.json').read_text())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=ROOT/'test-results'/f'{stamp}-acceptance-browser'
    output.mkdir()
    report={'url':BASE+'/', 'checks':[], 'passed':False}
    try:
        for url,expected in [(BASE+'/',401),('http://127.0.0.1:18243/api/v1/health',403)]:
            try:
                status=urllib.request.urlopen(url,timeout=20).status
            except urllib.error.HTTPError as exc:
                status=exc.code
            assert status==expected, (url,status,expected)
            report['checks'].append({'url':url,'status':status})
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for index,role in enumerate(['platform','resource','channel','clinic'],1):
                context=browser.new_context(http_credentials=creds, viewport={'width':1440,'height':900}, locale='zh-CN')
                page=context.new_page()
                errors=[]
                page.on('pageerror',lambda error: errors.append(type(error).__name__))
                page.goto(BASE+'/'+role+'/',wait_until='networkidle')
                page.get_by_role('button',name='获取验证码',exact=True).click()
                page.get_by_text('验证码已进入测试短信箱，请点击查看。',exact=True).wait_for()
                page.get_by_role('button',name='查看测试短信箱',exact=True).click()
                message=page.get_by_text('本次验证码：',exact=False)
                message.wait_for()
                import re
                code=re.search(r'本次验证码：(\d{6})',message.inner_text()).group(1)
                page.get_by_label('验证码',exact=True).fill(code)
                page.get_by_role('button',name='登录',exact=True).click()
                page.get_by_role('button',name='退出账号',exact=True).wait_for()
                page.wait_for_timeout(500)
                assert not page.locator('.arco-alert-error').count(), role+' workbench error'
                page.screenshot(path=str(output/(role+'-workbench.png')),full_page=True)
                menu=page.locator('nav button')
                count=menu.count()
                for n in range(count):
                    menu.nth(n).click()
                    page.wait_for_timeout(500)
                    assert not page.locator('.arco-alert-error').count(), role+' menu '+str(n)
                page.get_by_role('button',name='预约与履约',exact=True).click()
                page.locator('tbody tr').first.wait_for()
                assert page.locator('tbody tr').count()>0
                page.get_by_role('button',name='详情',exact=True).first.click()
                page.get_by_text('业务详情（真实接口结果）',exact=True).wait_for()
                page.screenshot(path=str(output/(role+'-details.png')),full_page=True)
                page.keyboard.press('Escape')
                page.set_viewport_size({'width':768,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),role+' overflow'
                page.get_by_role('button',name='退出账号',exact=True).click()
                page.get_by_role('button',name='登录',exact=True).wait_for()
                assert not errors, role+' browser script errors'
                report['checks'].append({'role':role,'menus':count,'login':True,'details':True,'logout':True,'script_errors':0})
                context.close()
            browser.close()
        for path in ['/','/study-system/']:
            response=urllib.request.urlopen('https://dev-public.chihui-ai.com'+path,timeout=20)
            assert response.status==200
            report['checks'].append({'existing_site':path,'status':response.status})
        report['passed']=True
    finally:
        (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('ACCEPTANCE_REPORT='+str(output/'summary.json'))
        print('ACCEPTANCE_PASSED='+str(report['passed']))


if __name__=='__main__':
    main()
