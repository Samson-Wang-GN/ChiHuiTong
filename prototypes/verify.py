import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent

def verify():
    errors = []
    report = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        page.on('pageerror', lambda error: errors.append(str(error)))
        for role in ['platform', 'resource', 'channel', 'clinic']:
            page.goto(f'{BASE}/{role}/')
            page.wait_for_selector('.workspace h1')
            page.screenshot(path=str(ROOT / role / 'preview.png'), full_page=True)
            routes = page.evaluate('window.PROTOTYPE.pages.filter(p=>!p.hidden&&!p.custom).map(page => ({id:page.id,title:page.title}))')
            for route in routes:
                print(role + '/' + route['id'], flush=True)
                page.locator('.sidebar').get_by_text(route['title'], exact=True).click()
                page.wait_for_selector('.arco-table')
                assert page.locator('h1').inner_text() == route['title'], route
                page.get_by_role('button', name='详情', exact=True).first.click()
                page.wait_for_selector('.arco-drawer')
                page.locator('.arco-drawer-close-icon').click()
                page.wait_for_selector('.arco-drawer', state='detached')
            report.append({'role':role,'routes':len(routes),'render':'passed'})
        for route in ['imports', 'orders', 'cards']:
            page.goto(f'{BASE}/resource/#{route}')
            page.wait_for_selector('.workspace h1')
            assert page.locator('.workspace h1').inner_text() == '推广产品销售'
        report.append({'case':'legacy sales routes unified; cancellation guards in verify_sales.py','result':'passed'})
        page.goto(f'{BASE}/channel/#appointments')
        page.wait_for_selector('.arco-table')
        assert page.get_by_role('button', name='确认预约', exact=True).count() == 0
        assert page.get_by_role('button', name='改期', exact=True).count() == 0
        assert '13800000011' not in page.locator('body').inner_text()
        report.append({'case':'channel appointment readonly','result':'passed'})
        page.goto(f'{BASE}/clinic/#appointments')
        page.wait_for_selector('.arco-table')
        page.get_by_role('button', name='确认预约', exact=True).click()
        page.locator('.arco-modal').get_by_role('button', name='确认预约', exact=True).click()
        page.wait_for_selector('.arco-message-success')
        page.reload()
        page.wait_for_selector('.arco-table')
        assert page.get_by_role('button', name='确认预约', exact=True).count() == 0
        report.append({'case':'appointment confirmation persists','result':'passed'})
        page.goto(f'{BASE}/platform/#sales')
        page.wait_for_selector('.arco-table')
        assert page.get_by_role('button', name='新建销售订单', exact=True).count() == 0
        report.append({'case':'platform cannot purchase as resource; receipt/approval in verify_sales.py','result':'passed'})
        page.goto(f'{BASE}/clinic/#appointments')
        page.wait_for_selector('.arco-table')
        page.set_viewport_size({'width': 1280, 'height': 800})
        page.screenshot(path=str(ROOT / 'clinic' / 'appointments.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        report.append({'case':'1280px layout','result':'passed'})
        page.goto(f'{BASE}/resource/#appointments')
        page.wait_for_selector('.arco-table')
        page.get_by_placeholder('搜索编号、名称或关键字').fill('不存在的客户批次')
        page.get_by_text('没有符合条件的记录，请调整筛选条件', exact=True).wait_for()
        report.append({'case':'empty filtered state','result':'passed'})
        page.goto(f'{BASE}/channel/#clinics')
        page.wait_for_selector('.arco-table')
        page.get_by_role('button', name='录入签约门诊', exact=True).click()
        page.wait_for_selector('.arco-drawer')
        page.wait_for_timeout(600)
        page.screenshot(path=str(ROOT / 'channel' / 'onboarding.png'), full_page=True)
        report.append({'case':'long onboarding form drawer','result':'passed'})
        page.goto((ROOT / 'clinic' / 'index.html').as_uri())
        page.wait_for_selector('.workspace h1')
        report.append({'case':'offline file entry','result':'passed'})
        browser.close()
    assert not errors, errors
    print(json.dumps({'checks':report,'browser_errors':errors}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    verify()
