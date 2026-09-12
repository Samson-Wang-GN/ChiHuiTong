#!/usr/bin/env python3
"""Real HTTPS and browser checks on the approved server. Never prints credentials/OTP."""

import json
import os
from pathlib import Path
import socket
import subprocess
import time
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
    report={'url':BASE+'/', 'deployed_commit':json.loads((runtime/'deployment.json').read_text())['commit'], 'verification_commit':Path(__file__).resolve().parents[1].name, 'checks':[], 'passed':False}
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
                page.on('pageerror',lambda error, captured=errors: captured.append(type(error).__name__))
                response=page.goto(BASE+'/'+role+'/',wait_until='networkidle')
                policy=response.headers.get('content-security-policy', '')
                assert "frame-src blob:" in policy and "object-src 'none'" in policy
                assert '{CSP}' not in policy and 'unsafe-eval' not in policy
                page.get_by_role('button',name='获取验证码',exact=True).click()
                page.get_by_role('button',name='查看测试短信箱',exact=True).click()
                message=page.get_by_text('本次验证码：',exact=False)
                message.wait_for()
                import re
                code=re.search(r'本次验证码：(\d{6})',message.inner_text()).group(1)
                page.get_by_label('验证码',exact=True).fill(code)
                if role=='clinic':
                    page.get_by_text('登录时开启预约提醒',exact=True).click()
                page.get_by_role('button',name='登录',exact=True).click()
                page.get_by_role('button',name='退出登录',exact=True).wait_for()
                page.wait_for_timeout(500)
                assert not page.locator('.arco-alert-error').count(), role+' workbench error'
                page.screenshot(path=str(output/(role+'-workbench.png')),full_page=True,animations='disabled')
                menu=page.locator('.sidebar .arco-menu-item')
                count=menu.count()
                for n in range(count):
                    menu.nth(n).click()
                    page.wait_for_timeout(500)
                    assert not page.locator('.arco-alert-error').count(), role+' menu '+str(n)
                title='预约管理' if role in {'platform','clinic'} else '预约与核销明细'
                menu.filter(has_text=re.compile('^'+title+'$')).click()
                page.locator('tbody tr').first.wait_for()
                assert page.locator('tbody tr').count()>0
                page.get_by_role('button',name='详情',exact=True).first.click()
                page.get_by_role('tab',name='预约资料',exact=True).wait_for()
                page.screenshot(path=str(output/(role+'-details.png')),full_page=True,animations='disabled')
                page.get_by_role('button',name='关闭详情',exact=True).click()
                page.locator('.arco-drawer-wrapper').wait_for(state='hidden')
                page.set_viewport_size({'width':768,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),role+' overflow'
                if role!='platform':
                    denied=page.evaluate("async()=>{try{await CHT.api('/api/v1/organizations');return 200;}catch(error){return error.status;}}")
                    assert denied==403
                page.get_by_role('button',name='退出登录',exact=True).click()
                page.get_by_role('button',name='登录',exact=True).wait_for()
                assert not errors, role+' browser script errors'
                report['checks'].append({'role':role,'menus':count,'login':True,'details':True,'logout':True,'script_errors':0})
                print('ROLE_PASSED='+role,flush=True)
                context.close()
            browser.close()
        for path in ['/','/study-system/']:
            response=urllib.request.urlopen('https://dev-public.chihui-ai.com'+path,timeout=20)
            assert response.status==200
            report['checks'].append({'existing_site':path,'status':response.status})
        sql="SELECT 'account',id::text FROM chihuitong_account UNION ALL SELECT 'appointment',id::text FROM chihuitong_appointment UNION ALL SELECT 'clinic_bill',id::text FROM chihuitong_clinicbill UNION ALL SELECT 'partner_bill',id::text FROM chihuitong_partnerbill ORDER BY 1,2"
        command=['/usr/lib/postgresql/16/bin/psql','-h',str(ROOT/'runtime'/'pgsocket'),'-p','55432','-d','chihuitong_acceptance','-Atc',sql]
        before=subprocess.run(command,check=True,capture_output=True,text=True,timeout=20).stdout
        subprocess.run(['sudo','-n','systemctl','restart','chihuitong-acceptance.service'],check=True,timeout=30)
        import base64
        authorization=base64.b64encode((creds['username']+':'+creds['password']).encode()).decode()
        ready=False
        for attempt in range(10):
            try:
                request=urllib.request.Request(BASE+'/api/v1/health',headers={'Authorization':'Basic '+authorization})
                with urllib.request.urlopen(request,timeout=5) as response:
                    ready=response.status==200
                if ready:break
            except urllib.error.URLError:
                time.sleep(0.5)
        assert ready,'acceptance service did not recover'
        after=subprocess.run(command,check=True,capture_output=True,text=True,timeout=20).stdout
        assert before==after,'persistent records changed after app restart'
        report['checks'].append({'app_restart':True,'persistent_record_ids_unchanged':True,'record_count':len(after.splitlines())})
        report['passed']=True
    finally:
        (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('ACCEPTANCE_REPORT='+str(output/'summary.json'))
        print('ACCEPTANCE_PASSED='+str(report['passed']))


if __name__=='__main__':
    main()
