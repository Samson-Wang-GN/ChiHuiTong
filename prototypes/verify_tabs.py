"""所有角色状态Tab、筛选、分页、状态迁移及导出范围验证。"""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent


def verify():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def go(role, route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('.status-tabs:visible')
            page.wait_for_timeout(300)

        def tab(state, count=None):
            name = re.compile('^' + re.escape(state) + '（') if count is None else f'{state}（{count}）'
            root=page.locator('.arco-drawer').last if page.locator('.arco-drawer').count() else page
            return root.get_by_role('tab', name=name, exact=count is not None).filter(visible=True)

        count = 0
        for role in ['platform', 'resource', 'channel', 'clinic']:
            go(role, 'appointments' if role in ['channel','clinic'] else 'sources' if role=='platform' else 'contracts')
            routes = page.evaluate('window.PROTOTYPE.pages.filter(p=>!p.hidden&&!p.custom).map(p=>({id:p.id,rows:p.rows}))')
            for route in routes:
                go(role, route['id'])
                tab('全部', len(route['rows'])).wait_for()
                assert page.get_by_label('状态筛选', exact=True).count() == 0
                states = list(dict.fromkeys(r['status'] for r in route['rows']))
                for state in states:
                    expected = sum(r['status'] == state for r in route['rows'])
                    tab(state, expected).click()
                    assert page.locator('.toolbar').get_by_text(f'共 {expected} 条', exact=True).count() == 1
                    statuses = page.locator('.status-tabs tbody .arco-tag').all_inner_texts()
                    assert statuses and all(s == state for s in statuses), (role, route['id'], statuses)
                count += 1
            print(f'{role}: all {len(routes)} lists and populated status tabs passed', flush=True)

        go('clinic', 'appointments')
        page.get_by_placeholder('搜索编号、名称或关键字').fill('客户甲')
        tab('取消', 0).click()
        page.get_by_text('没有符合条件的记录，请调整筛选条件', exact=True).wait_for()
        tab('全部').click()
        page.get_by_placeholder('搜索编号、名称或关键字').fill('客户甲')
        tab('全部', 1).wait_for()
        tab('成功', 0).click()
        assert page.get_by_placeholder('搜索编号、名称或关键字').input_value() == '客户甲'
        tab('待确认', 1).click()
        page.get_by_role('button', name='确认预约', exact=True).click()
        page.locator('.arco-modal').get_by_role('button', name='确认预约', exact=True).click()
        page.wait_for_selector('.arco-modal', state='detached')
        tab('待确认', 0).wait_for()
        assert tab('待确认').get_attribute('aria-selected') == 'true'
        tab('成功', 1).click()
        page.get_by_role('button', name='详情', exact=True).click()
        page.locator('.arco-drawer-close-icon').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        assert tab('成功').get_attribute('aria-selected') == 'true'
        page.get_by_role('button', name='重置', exact=True).click()
        tab('全部', 8).wait_for()
        print('zero state / keyword intersection / transition counts / detail context passed', flush=True)

        go('platform', 'contractSchemes?contract=HT-AH-001')
        tab('全部', 1).wait_for()
        tab('已停用', 0).click()
        tab('全部', 1).click()
        tab('全部', 1).wait_for()
        assert 'contract=HT-AH-001' in page.url
        assert 'SQ-002' not in page.locator('.workspace').inner_text()

        go('resource', 'appointments')
        page.get_by_placeholder('搜索编号、名称或关键字').fill('客户甲')
        page.get_by_role('button', name='导出数据', exact=True).click()
        with page.expect_download() as result:
            page.locator('.arco-modal').get_by_role('button', name='确定', exact=True).click()
        csv = Path(result.value.path()).read_text(encoding='utf-8-sig')
        assert '客户甲' in csv and '客户乙' not in csv
        print('contract scope retained / scoped customer export passed', flush=True)

        # 测试夹具仅改变这个浏览器上下文中的虚构记录，验证超过一页的场景。
        page.evaluate("""() => {
          const data=JSON.parse(JSON.stringify(window.PROTOTYPE.pages));
          const p=data.find(p=>p.id==='appointments'),seed=p.rows[0];
          p.rows=Array.from({length:20},(_,i)=>({...seed,id:'PAGE-'+i,name:'分页验证'+i,status:i<16?'待审核':'已入账'}));
          localStorage.setItem('chihuitong-prototype-v1-resource',JSON.stringify(data));
        }""")
        page.reload()
        page.wait_for_selector('.status-tabs:visible')
        page.locator('.arco-pagination-item').filter(has_text=re.compile('^2$')).click()
        assert page.locator('.arco-pagination-item-active').inner_text() == '2'
        tab('已入账').click()
        assert page.locator('.arco-pagination-item-active').inner_text() == '1'
        tab('全部').click()
        page.locator('.arco-pagination-item').filter(has_text=re.compile('^2$')).click()
        page.get_by_placeholder('搜索编号、名称或关键字').fill('分页验证1')
        assert page.locator('.arco-pagination-item-active').inner_text() == '1'
        print('status and keyword reset pagination passed', flush=True)

        go('clinic', 'appointments')
        page.wait_for_function("document.querySelectorAll('.arco-message').length === 0")
        page.screenshot(path=str(ROOT / 'clinic' / 'status-tabs.png'), full_page=True)
        page.set_viewport_size({'width': 768, 'height': 900})
        go('platform', 'institutions?institution=JG-001&section=contracts')
        tab('已终止', 0).click()
        assert tab('已终止').get_attribute('aria-selected') == 'true'
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.wait_for_timeout(600)
        page.screenshot(path=str(ROOT / 'platform' / 'status-tabs-narrow.png'), full_page=True)
        assert not errors, errors
        print(f'{count} lists; narrow overflow passed; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
