#!/usr/bin/env python3
"""Server-only disposable database and loopback gateway for real Web/API regression."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True

ROOT = Path('/home/ubuntu/ChiHuiTong')
PG = Path('/usr/lib/postgresql/16/bin')
PORT = 18244


def serve(release):
    from wsgiref.simple_server import WSGIRequestHandler, make_server
    sys.path.insert(0, str(release / 'backend'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    from django.core.wsgi import get_wsgi_application
    app = get_wsgi_application()
    from deploy_acceptance import CSP

    def gateway(env, start):
        # Private test gateway mirrors the approved HTTPS proxy's path/header handling.
        # It is loopback-only, separate from acceptance, never installed as a service.
        if not env['PATH_INFO'].startswith('/chihuitong/'):
            start('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Not found']
        env['PATH_INFO'] = env['PATH_INFO'][len('/chihuitong'):]
        env['HTTP_X_CHT_ACCEPTANCE'] = os.environ['CHT_ACCEPTANCE_PROXY_TOKEN']
        env['HTTP_AUTHORIZATION'] = env.get('HTTP_X_CHT_AUTHORIZATION', '')
        if env.get('HTTP_ORIGIN') == f'http://127.0.0.1:{PORT}':
            env['HTTP_ORIGIN'] = f'https://127.0.0.1:{PORT}'
        def secured_start(status, headers, exc_info=None):
            if any(key.lower()=='content-type' and value.startswith('text/html') for key,value in headers):
                headers.append(('Content-Security-Policy', CSP))
            return start(status, headers, exc_info)
        return app(env, secured_start)

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, format, *args):
            pass

    with make_server('127.0.0.1', PORT, gateway, handler_class=QuietHandler) as server:
        server.serve_forever()


def check_browser(report, release, worker, fixture, headed=False):
    from playwright.sync_api import sync_playwright
    result = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        pages = {}
        contexts = []
        for role, phone in [('platform', '13800000001'), ('resource', '13800000002'), ('channel', '13800000003'), ('clinic', '13800000004')]:
            context = browser.new_context(no_viewport=True) if headed else browser.new_context(viewport={'width':1440, 'height':1000})
            page = context.new_page()
            if headed:
                page.set_viewport_size({'width':1440, 'height':1000})
            pages[role] = page
            contexts.append(context)
            errors = []
            page.on('pageerror', lambda error, captured=errors: captured.append(str(error)))
            page.goto(f'http://127.0.0.1:{PORT}/chihuitong/{role}/')
            page.get_by_label('手机号', exact=True).fill(phone)
            page.get_by_role('button', name='获取验证码', exact=True).click()
            page.get_by_role('button', name='查看测试短信箱', exact=True).click()
            text = page.get_by_text('本次验证码：', exact=False)
            text.wait_for()
            import re
            code = re.search(r'本次验证码：(\d{6})', text.inner_text()).group(1)
            page.get_by_label('验证码', exact=True).fill(code)
            if role == 'clinic' and not headed:
                page.get_by_text('登录时开启预约提醒', exact=True).click()
            page.get_by_role('button', name='登录', exact=True).click()
            page.get_by_role('button', name='退出登录', exact=True).wait_for()
            if role == 'clinic' and headed:
                page.wait_for_function('!!window.documentPictureInPicture?.window')
            page.wait_for_function("!document.querySelector('.workspace .arco-spin-loading')")
            menu = page.locator('.sidebar .arco-menu-item')
            titles = menu.all_text_contents()
            for title in titles:
                page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^'+re.escape(title)+'$')).click()
                page.locator('.workspace h1').filter(has_text=title).wait_for()
                page.wait_for_timeout(250)
                if page.get_by_text('页面暂时无法显示', exact=True).count():
                    raise AssertionError(f'{role}/{title}: render boundary failure')
            if role == 'platform':
                page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^推广产品$')).click()
                page.get_by_role('button', name='新建推广产品', exact=True).click()
                drawer = page.locator('.arco-drawer-wrapper').last
                def fill(label, value):
                    drawer.locator('.arco-form-item').filter(has=page.locator('.arco-form-label-item', has_text=label)).locator('input,textarea').first.fill(value)
                fill('内部展示名称', '自动回归专用产品')
                fill('外部展示名称', '洁牙福利回归')
                fill('使用规则', '仅用于合成回归，不可兑换实际服务')
                drawer.get_by_role('button', name='保存', exact=True).click()
                drawer.wait_for(state='hidden')
                page.get_by_text('自动回归专用产品', exact=True).wait_for()
                page.locator('.sidebar .arco-menu-item').filter(has_text='机构管理').click()
                page.get_by_role('button', name='详情', exact=True).first.click()
                page.get_by_role('tab', name='来源展示名', exact=True).count()
                page.get_by_role('tab', name='合作合同', exact=True).click()
                page.get_by_role('button', name='关闭详情', exact=True).last.click()
            page.screenshot(path=str(report/f'{role}.png'), full_page=True, animations='disabled')
            page.set_viewport_size({'width':768, 'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), role+' narrow overflow'
            assert not errors, f'{role}: {errors}'
            result.append({'role':role, 'menus':titles, 'errors':errors})
            page.set_viewport_size({'width':1440, 'height':1000})
        from web_workflows import exercise
        exercise(pages, report, worker, fixture)
        if headed:
            from web_reminder import exercise_reminder
            exercise_reminder(pages['clinic'], fixture, report)
        for item in result:
            assert not item['errors'], f"{item['role']}: {item['errors']}"
        for page in pages.values():
            page.get_by_role('button', name='退出登录', exact=True).click()
            page.get_by_role('button', name='登录', exact=True).wait_for()
        for context in contexts:
            context.close()
        browser.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--headed', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux' or socket.gethostname() != 'VM-0-12-ubuntu' or os.getuid() == 0:
        raise SystemExit('Only approved development host as ubuntu')
    release = Path(__file__).resolve().parents[1]
    if release.parent != ROOT/'releases' or len(release.name) != 40:
        raise SystemExit('Only immutable verified release')
    if args.serve:
        serve(release)
        return
    import fcntl
    os.umask(0o077)
    lock = (ROOT/'runtime/web-tests.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = ROOT/'test-results'/f'{stamp}-{release.name[:12]}-web'
    report.mkdir()
    name = 'chihuitong_acceptance_web_'+secrets.token_hex(6)
    env = dict(os.environ, CHT_ENVIRONMENT='test', CHT_ACCEPTANCE_ENABLED='true', CHT_ACCEPTANCE_PROXY_TOKEN=secrets.token_urlsafe(48), CHT_SECRET_KEY=secrets.token_urlsafe(48), CHT_FIELD_KEYS=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), CHT_PHONE_INDEX_KEY=secrets.token_urlsafe(48), CHT_DB_NAME=name, CHT_DB_USER='ubuntu', CHT_DB_HOST=str(ROOT/'runtime/pgsocket'), CHT_DB_PORT='55432', CHT_ALLOWED_HOSTS='127.0.0.1,localhost', CHT_PRIVATE_STORAGE=str(report/'private-files'), CHT_SMS_BACKEND='chihuitong.acceptance.AcceptanceSMS', CHT_WECHAT_PAY_ENABLED='false', PYTHONDONTWRITEBYTECODE='1')
    dbargs = ['-h', env['CHT_DB_HOST'], '-p', '55432']
    env['CHT_ACCEPTANCE_SIMULATED_EXTERNALS'] = 'true'
    def run(command, **kwargs):
        return subprocess.run([str(x) for x in command], check=True, text=True, timeout=120, **kwargs)
    location = run([PG/'psql', *dbargs, '-d', 'postgres', '-Atc', 'SHOW data_directory'], capture_output=True).stdout.strip()
    if Path(location).resolve() != ROOT/'runtime/postgres':
        raise SystemExit('Unexpected PostgreSQL instance')
    summary = {'commit':release.name, 'passed':False, 'database':name, 'roles':[]}
    python = ROOT/'.venv-backend/bin/python'
    server = None
    print('WEB_REPORT='+str(report/'summary.json'), flush=True)
    run([PG/'createdb', *dbargs, name])
    try:
        with (report/'setup.log').open('w') as log:
            run([python, release/'scripts/web_fixture_files.py', report], stdout=log, stderr=subprocess.STDOUT)
            for command in [['migrate','--noinput'], ['initialize_configuration'], ['seed_acceptance'], ['initialize_simulation']]:
                run([python,'manage.py',*command], cwd=release/'backend', env=env, stdout=log, stderr=subprocess.STDOUT)
        def worker():
            with (report/'worker.log').open('a') as log:
                run([python,'manage.py','run_worker','--no-tick','--limit','100'], cwd=release/'backend', env=env, stdout=log, stderr=subprocess.STDOUT)
        def fixture(kind='new'):
            result = run([python, release/'scripts/web_business_fixture.py', kind], env=env, capture_output=True)
            return json.loads(result.stdout)
        with (report/'server.log').open('w') as log:
            server = subprocess.Popen([str(python),str(Path(__file__).resolve()),'--serve'], env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(40):
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1',PORT)) == 0:
                        break
                if server.poll() is not None:
                    raise RuntimeError('Test gateway failed; inspect server.log')
                time.sleep(.25)
            summary['roles'] = check_browser(report, release, worker, fixture, args.headed)
            summary['passed'] = True
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
        # The exact freshly-created test database only; never acceptance/dev/shared data.
        run([PG/'dropdb', *dbargs, name])
        summary['disposable_database_removed'] = True
        (report/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print('WEB_PASSED='+str(summary['passed']), flush=True)


if __name__ == '__main__':
    main()
