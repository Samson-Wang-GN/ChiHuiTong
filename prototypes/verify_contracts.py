"""合同方案与来源名增量原型验证；需先启动本机8765静态服务。"""
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
            page.wait_for_selector('.workspace h1')
            page.wait_for_timeout(400)

        def panel():
            return page.locator('.arco-drawer:visible').last if page.locator('.arco-drawer:visible').count() else page

        def select(label, value):
            page.locator('.arco-form-item').filter(has_text=label).locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=value).last.click()

        def edit(value):
            panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('SQ-001')
            panel().get_by_role('button', name='编辑分配', exact=True).click()
            page.get_by_placeholder('请输入分配值（比例填%，金额填元/次）').fill(str(value))
            page.get_by_placeholder('请输入变更原因').fill('合同补充条款评审')

        go('platform', 'institutions?institution=JG-001&section=contracts')
        panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('HT-AH-001')
        panel().get_by_role('button', name='推广产品配置', exact=True).click()
        page.get_by_text('当前范围：HT-AH-001', exact=True).wait_for()
        panel().get_by_role('button', name='详情', exact=True).click()
        drawer = page.locator('.arco-drawer').last
        drawer.get_by_text('单次核销分配试算', exact=True).wait_for()
        assert '12.00' in drawer.inner_text() and '18.00' in drawer.inner_text() and '30.00' in drawer.inner_text()
        page.wait_for_timeout(600)
        page.screenshot(path=str(ROOT / 'platform' / 'contract-allocation.png'), full_page=True)
        print('contract entry / mixed allocation 12+18+30: passed', flush=True)

        go('platform', 'institutions?institution=JG-001&section=products')
        edit(90)
        page.locator('.arco-drawer').last.get_by_role('button', name='编辑分配', exact=True).click()
        page.get_by_text('资源方与渠道方分配合计超过获客费，请调整合同分配。', exact=True).wait_for()
        select('分配方式', '按金额')
        page.get_by_placeholder('请输入分配值（比例填%，金额填元/次）').fill('15')
        page.locator('.arco-drawer').last.get_by_role('button', name='编辑分配', exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        page.reload()
        data = page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'))")
        term = next(r for p in data if p['id'] == 'contractSchemes' for r in p['rows'] if r['id'] == 'SQ-001')
        assert term['value'] == 15 and term['mode'] == '按金额' and term['version'] == 2
        assert next(p for p in data if p['id'] == 'audit')['rows'][0]['before']
        print('over-allocation blocked / fixed amount saved / version audit: passed', flush=True)

        panel().get_by_role('button', name='添加推广产品', exact=True).click()
        select('合作方合同', 'HT-AH-001')
        select('推广产品', '舒适洁牙权益')
        page.get_by_placeholder('请输入分配值（比例填%，金额填元/次）').fill('10')
        page.get_by_placeholder('请输入变更原因').fill('重复校验')
        page.locator('.arco-drawer').last.get_by_role('button', name='添加推广产品', exact=True).click()
        page.get_by_text('同一合作方在重叠合同期内不能重复授权同一方案。', exact=True).wait_for()
        select('推广产品', '种植牙抵用权益')
        page.locator('.arco-drawer').last.get_by_role('button', name='添加推广产品', exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('')
        page.get_by_text('方案未启用', exact=True).wait_for()
        print('duplicate blocked / added draft scheme remains unavailable: passed', flush=True)

        panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('SQ-001')
        panel().get_by_role('button', name='停用授权', exact=True).click()
        page.get_by_placeholder('请输入变更原因').fill('停止后续新增')
        page.locator('.arco-drawer').last.get_by_role('button', name='停用授权', exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        page.get_by_text('授权已停用', exact=True).wait_for()
        go('platform', 'sales')
        blocked = page.evaluate("""() => {
          const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));
          return PrototypeSales.approve(p,'SALE-DEMO-FREE',180,'合同权限复核',true).error;
        }""")
        assert '未授权' in blocked
        go('platform', 'institutions?institution=JG-001&section=products')
        panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('SQ-001')
        panel().get_by_role('button', name='启用授权', exact=True).click()
        page.get_by_placeholder('请输入变更原因').fill('恢复合作')
        page.locator('.arco-drawer').last.get_by_role('button', name='启用授权', exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        page.get_by_text('可开展新业务', exact=True).wait_for()
        print('disable blocks new import approval / re-enable: passed', flush=True)

        go('platform', 'institutions')
        panel().locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill('安和经纪')
        panel().get_by_role('button', name='详情', exact=True).click()
        panel().get_by_role('button', name='来源展示名', exact=True).click()
        page.get_by_text('当前范围：安和经纪（演示）', exact=True).wait_for()
        assert '星海银行信用卡礼遇' not in page.locator('.workspace').inner_text()
        panel().get_by_role('button', name='编辑展示名', exact=True).click()
        page.get_by_placeholder('请输入客户侧展示名称').fill('安和保险尊享礼遇')
        page.get_by_placeholder('请输入变更原因').fill('品牌展示调整')
        page.locator('.arco-modal').get_by_role('button', name='编辑展示名', exact=True).click()
        page.wait_for_selector('.arco-modal', state='detached')
        page.locator('.arco-table').get_by_text('安和保险尊享礼遇').wait_for()
        stored = page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'))")
        assert next(p for p in stored if p['id'] == 'imports')['rows'][0]['source'] == '安和保险客户福利'
        panel().get_by_role('button', name='停用', exact=True).click()
        page.get_by_placeholder('请输入处理原因').fill('停止后续选择')
        page.locator('.arco-modal').get_by_role('button', name='停用', exact=True).click()
        page.wait_for_selector('.arco-modal', state='detached')
        panel().get_by_role('button', name='启用', exact=True).click()
        page.get_by_placeholder('请输入变更原因').fill('重新开放')
        page.locator('.arco-modal').get_by_role('button', name='启用', exact=True).click()
        page.wait_for_selector('.arco-modal', state='detached')
        page.wait_for_function("document.querySelectorAll('.arco-message').length === 0")
        page.screenshot(path=str(ROOT / 'platform' / 'source-settings.png'), full_page=True)
        print('institution scoped source editing: passed', flush=True)

        for role in ['clinic']:
            go(role, 'offers')
            panel().get_by_role('button', name='上线优惠', exact=True).click()
            page.get_by_text('当前渠道合同未授权该方案，不能上线优惠。', exact=True).wait_for()
            assert page.locator('.arco-modal').count() == 0
        go('resource', 'sales')
        panel().get_by_role('button', name='新建销售订单', exact=True).click()
        panel().get_by_role('button', name='下一步', exact=True).click()
        panel().get_by_role('button', name='下一步', exact=True).click()
        page.locator('.flow-field').filter(has=page.get_by_text('推广产品', exact=True)).locator('.arco-select').click()
        options = page.locator('.arco-select-option').all_inner_texts()
        assert options == ['舒适洁牙权益'], options
        go('resource', 'contracts')
        page.evaluate("""() => {
          const data=JSON.parse(JSON.stringify(window.PROTOTYPE.pages));
          data.find(p=>p.id==='contracts').rows[0].end='2026-09-01';
          localStorage.setItem('chihuitong-prototype-v1-resource',JSON.stringify(data));
        }""")
        page.reload()
        go('resource', 'contractSchemes')
        page.get_by_text('当前没有生效合同；历史内容仍可查看，不能开展新增业务。', exact=True).wait_for()
        go('resource', 'sales')
        panel().get_by_role('button', name='新建销售订单', exact=True).click()
        panel().get_by_role('button', name='下一步', exact=True).click()
        panel().get_by_role('button', name='下一步', exact=True).click()
        page.locator('.flow-field').filter(has=page.get_by_text('推广产品', exact=True)).locator('.arco-select').click()
        assert page.locator('.arco-select-option').count() == 0
        print('resource authorized selection / channel and clinic unauthorized offer blocked: passed', flush=True)

        go('platform', 'schemes')
        page.evaluate("""() => {
          const old = JSON.parse(JSON.stringify(window.PROTOTYPE.pages)).filter(p=>p.id!=='contractSchemes');
          old.find(p=>p.id==='sources').rows[0].name='保留的本地展示名';
          old.find(p=>p.id==='schemes').rows[0].resourceShare=99;
          old.find(p=>p.id==='sources').actions=[];
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(old));
        }""")
        page.reload()
        page.locator('.sidebar').get_by_text('来源展示名配置', exact=True).click()
        page.locator('.arco-table').get_by_text('保留的本地展示名').wait_for()
        assert panel().get_by_role('button', name='编辑展示名', exact=True).count() > 0
        go('platform', 'institutions?institution=JG-001&section=products')
        page.get_by_text('HT-AH-001', exact=True).wait_for()
        print('old cached configuration upgraded without losing edited records: passed', flush=True)
        assert not errors, errors
        print('browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
