"""REQ-031: institution-scoped contracts/products, legacy migration and task actions."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765/platform/'


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def go(route):
            page.goto(BASE + '#' + route)
            page.wait_for_selector('.workspace h1:visible')
            page.wait_for_timeout(400)

        def search(value):
            root = page.locator('.arco-drawer').last if page.locator('.arco-drawer').count() else page
            root.locator('input[placeholder="搜索编号、名称或关键字"]:visible').fill(value)

        go('institutions')
        menu = page.locator('.sidebar').inner_text()
        assert '合同管理' not in menu and '合同权益配置' not in menu and '推广产品配置' not in menu
        search('安和')
        assert page.locator('.workspace').get_by_role('button', name='合作合同', exact=True).count()==0
        page.get_by_role('button', name='详情', exact=True).click()
        page.get_by_text('安和经纪（演示） · 机构管理', exact=True).wait_for()
        assert page.locator('.arco-drawer .arco-tabs-line').count()>0
        page.get_by_role('tab', name='合作合同', exact=True).click()
        page.get_by_role('tab', name='合作合同', exact=True).wait_for()
        assert 'HT-XH-001' not in page.locator('.workspace').inner_text()
        assert page.get_by_role('button', name='登记合同', exact=True).is_disabled()
        page.locator('.arco-drawer-close-icon').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        page.get_by_role('heading', name='机构管理', exact=True).wait_for()
        assert page.locator('input[placeholder="搜索编号、名称或关键字"]:visible').input_value() == '安和'
        print('menus, institution scope and list filter preservation: passed', flush=True)

        go('contractSchemes?contract=HT-XH-001')
        page.get_by_text('当前范围：HT-XH-001', exact=True).wait_for()
        assert 'SQ-001' not in page.locator('.workspace').inner_text()
        go('contractSchemes')
        page.get_by_text('合同与推广产品配置已整合，请先选择机构。', exact=True).wait_for()
        go('institutions?institution=JG-001&section=products&contract=HT-XH-001')
        page.get_by_text('机构或合同范围不匹配，请重新选择；未加载其他机构配置。', exact=True).wait_for()

        result = page.evaluate("""() => {
          const p=JSON.parse(JSON.stringify(PROTOTYPE.pages)), I=PrototypeInstitutions;
          const cp=p.find(x=>x.id==='contracts'),tp=p.find(x=>x.id==='contractSchemes');
          const c=cp.rows.find(x=>x.id==='HT-AH-001');delete c.institutionId;c.note='保留原条款';
          cp.rows.push({...c,id:'ORPHAN',party:'未匹配机构'});
          I.migrate(p);
          const op={page:tp,action:{create:true},institutionId:'JG-001'};
          const blocked=I.guard(p,op,{contract:'HT-XH-001'});
          const ok=I.guard(p,op,{contract:'HT-AH-001'});
          const legacy=cp.rows.find(c=>c.id==='HT-XH-001');delete legacy.institutionId;legacy.party='尚待核实的原签约主体';
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));
          return {blocked,ok,id:c.institutionId,note:c.note,orphan:I.owner(p,cp.rows.at(-1))};
        }""")
        assert result['blocked'] and result['ok'] is None
        assert result['id'] == 'JG-001' and result['note'] == '保留原条款' and result['orphan'] is None
        page.reload()
        assert page.evaluate("!!localStorage.getItem('chihuitong-prototype-v1-platform-before-0.24')")
        print('legacy scoped URLs, fail-closed guard, migration and backup: passed', flush=True)

        # A new institution must not be constrained to the three static seed partners.
        page.evaluate("""() => {
          const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));
          p.find(x=>x.id==='institutions').rows.push({id:'JG-TEST',name:'测试保险机构',type:'保险公司',contact:'演示联系人',status:'正常'});
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));
        }""")
        go('institutions?institution=JG-TEST&section=contracts')
        page.reload()
        page.get_by_role('button', name='登记合同', exact=True).click()
        page.wait_for_timeout(400)
        form = page.locator('.arco-drawer:visible, .arco-modal:visible').last
        assert form.locator('.arco-select-disabled').count() == 2
        # Use rendered field keys to fill the original generic form without changing its schema.
        page.locator('.arco-form-item').filter(has_text='合同名称').locator('input').fill('测试保险合作合同')
        for label, value in [('生效日期', '2026-09-01'), ('到期日期', '2027-08-31')]:
            field = page.locator('.arco-form-item').filter(has_text=label).locator('input')
            field.fill(value)
            field.press('Enter')
        contact = page.locator('.arco-form-item').filter(has_text='联系').locator('input')
        contact.fill('13800000000')
        page.locator('input[type=file]').set_input_files({'name':'合同.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4 demo'})
        form.get_by_role('button', name='登记合同', exact=True).click()
        page.wait_for_timeout(300)
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        data = page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'))")
        contract = next(c for x in data if x['id']=='contracts' for c in x['rows'] if c.get('institutionId')=='JG-TEST')
        unmatched=next(c for x in data if x['id']=='contracts' for c in x['rows'] if c['id']=='HT-XH-001')
        assert not unmatched.get('institutionId') and unmatched['party']=='尚待核实的原签约主体'
        assert contract['party']=='测试保险机构' and contract['type']=='平台—资源方' and contract['status']=='待审核'
        go('tasks?type=contracts')
        search(contract['id'])
        page.get_by_role('button', name='立即处理', exact=True).click()
        page.get_by_role('button', name='审核生效', exact=True).click()
        page.get_by_placeholder('请输入处理原因').fill('机构合同审核通过')
        page.locator('.arco-modal:visible').get_by_role('button', name='审核生效', exact=True).click()
        page.wait_for_selector('.arco-modal', state='detached')
        assert '#tasks' in page.url
        data=page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'))")
        assert next(c for x in data if x['id']=='contracts' for c in x['rows'] if c['id']==contract['id'])['status']=='已生效'
        print('new institution locked contract registration and task-page approval: passed', flush=True)

        go('institutions?institution=JG-001&section=products')
        page.locator('.arco-drawer').last.get_by_role('button', name='添加推广产品', exact=True).click()
        page.locator('.arco-form-item').filter(has_text='合作方合同').locator('.arco-select').click()
        options=page.locator('.arco-select-option').all_inner_texts()
        assert options and all('HT-AH-001' in x for x in options), options
        page.keyboard.press('Escape')
        go('institutions?institution=JG-003&section=products')
        page.wait_for_function("document.querySelectorAll('.arco-message').length===0")
        page.wait_for_timeout(500)
        page.screenshot(path=str(ROOT/'platform'/'institution-products.png'), full_page=True)
        page.set_viewport_size({'width':768,'height':900})
        go('institutions?institution=JG-003&section=contracts')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.wait_for_timeout(500)
        page.screenshot(path=str(ROOT/'platform'/'institution-contracts-narrow.png'), full_page=True)
        assert page.locator('.arco-drawer').last.bounding_box()['width']<=768
        # Match the clinic detail container, then test list context and nested cancellation.
        page.set_viewport_size({'width':1440,'height':1000})
        go('clinics')
        page.get_by_role('button', name='详情', exact=True).first.click()
        page.wait_for_timeout(400)
        clinic_width=page.locator('.arco-drawer').last.bounding_box()['width']
        go('institutions?institution=JG-001&section=products')
        assert page.locator('.arco-drawer').last.bounding_box()['width']==clinic_width==1000
        page.locator('.arco-drawer').last.get_by_role('button', name='添加推广产品', exact=True).click()
        page.wait_for_timeout(400)
        page.get_by_placeholder('请输入变更原因').fill('取消测试未提交')
        page.locator('.arco-drawer-close-icon').last.click()
        page.locator('.arco-modal').get_by_role('button', name='取消', exact=True).click()
        assert page.get_by_placeholder('请输入变更原因').input_value()=='取消测试未提交'
        page.locator('.arco-drawer-close-icon').last.click()
        page.locator('.arco-modal').get_by_role('button', name='确定', exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)', state='detached')
        assert page.locator('.arco-drawer').count()==1
        assert page.get_by_role('tab',name='推广产品配置',exact=True).get_attribute('aria-selected')=='true'
        page.evaluate("""() => {
          const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));
          const list=p.find(p=>p.id==='institutions').rows;
          for(let n=0;n<18;n++)list.push({id:'PAGE-'+n,name:'分页机构'+n,type:'保险公司',contact:'演示联系人',status:'正常'});
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));
        }""")
        go('institutions')
        page.reload()
        search('分页机构')
        page.get_by_role('tab',name='正常（18）',exact=True).click()
        page.locator('.arco-pagination-item').filter(has_text='2').click()
        page.get_by_role('button',name='详情',exact=True).first.click()
        page.get_by_role('tab',name='推广产品配置',exact=True).click()
        page.locator('.arco-drawer-close-icon').click()
        page.wait_for_selector('.arco-drawer',state='detached')
        assert page.locator('.arco-pagination-item-active').inner_text()=='2'
        assert page.get_by_role('tab',name='正常（18）',exact=True).get_attribute('aria-selected')=='true'
        assert page.get_by_placeholder('搜索编号、名称或关键字').input_value()=='分页机构'
        page.get_by_role('button',name='详情',exact=True).first.click()
        assert page.get_by_role('tab',name='机构资料',exact=True).get_attribute('aria-selected')=='true'
        print('clinic-equivalent drawer / nested cancel protection / status-keyword-page preservation: passed',flush=True)
        assert not errors, errors
        print('own-contract options, screenshots, narrow layout and browser errors: passed', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
