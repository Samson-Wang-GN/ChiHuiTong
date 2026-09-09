"""REQ-033: independent role fixtures; no cross-role application synchronization."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent

def verify():
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(8000)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def go(role,route):
            page.goto(f'http://127.0.0.1:8765/{role}/#{route}')
            page.wait_for_selector('.workspace h1')
            page.wait_for_timeout(250)
            page.evaluate('()=>{const key="chihuitong-prototype-v1-"+PROTOTYPE.role;if(!localStorage.getItem(key))localStorage.setItem(key,JSON.stringify(PrototypeClinicInfo.migrate(PrototypeWorkflows.migrate(structuredClone(PROTOTYPE.pages))))) }')
            page.reload()
            page.wait_for_selector('.workspace h1')
        def button(label):
            root=page.locator('.arco-drawer').last if page.locator('.arco-drawer').count() else page
            return root.get_by_role('button',name=label,exact=True)
        def data(role):
            return page.evaluate('role=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-"+role)).find(p=>p.id===(role==="clinic"?"profile":"clinics")).rows[0]',role)
        for role in ['channel','clinic']:
            go(role,'clinics' if role=='channel' else 'profile')
            original=data(role)
            variants=page.evaluate('c=>{const C=PrototypeClinicInfo;const values={name:"改名（演示）",subject:"新主体",address:"演示市景明路28号",hours:"10:00–19:00",businessContact:"负责人",phone:"13800000088",cover:{name:"新展示.png",url:"data:image/png;base64,aA=="},location:{longitude:116.32,latitude:39.98,address:c.address,coordinateSystem:"GCJ-02",status:"已确认（演示）"},files:[...(c.files||[]),PrototypeWorkflows.sample("补充照片","门诊照片")]};return Object.entries(values).map(([key,value])=>{const target=structuredClone(c);const d={...target,[key]:value};if(key==="businessContact")d.businessPhone="13800000077";const before=JSON.stringify(C.snapshot(target));const error=C.commit(target,d);return {key,error,unchanged:JSON.stringify(C.snapshot(target))===before,pending:C.waiting(target)}})}',original)
            assert all(v['error'] is None and v['unchanged'] and v['pending'] for v in variants),variants
            if role=='channel':button('详情').first.click()
            button('维护门诊资料').click()
            assert page.get_by_label('待确认时限（小时）',exact=True).count()==0
            button('提交变更审核').click()
            page.get_by_text('资料没有变化，无需提交。',exact=True).wait_for()
            assert page.evaluate('c=>PrototypeClinicInfo.commit(c,{...c,timeout:99})',original)=='门诊待确认时限仅平台可修改。'
            page.get_by_label('前台预约手机号',exact=True).fill('13800000099')
            button('提交变更审核').click()
            page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
            submitted=data(role)
            assert submitted['phone']==original['phone'] and submitted['status']==original['status']
            change=submitted['profileChanges'][0]
            assert change['after']['phone']=='13800000099' and change['status']=='待审核'
            assert submitted.get('infoVersion',0)==original.get('infoVersion',0)
            assert button('维护门诊资料').is_disabled()
            assert page.evaluate('c=>PrototypeClinicInfo.commit(c,{...c,phone:"13800000088"})',submitted)=='已有资料待审核，请等待平台处理后再修改。'
            assert page.evaluate('c=>PrototypeClinicInfo.reviewChange(c,c.profileChanges[0].id,true,"越权")',submitted)=='只有平台可审核门诊资料变更。'
            page.reload()
            page.wait_for_selector('.workspace h1')
            assert data(role)['profileChanges'][0]['status']=='待审核'
            # Independent rejection fixture tests the recipient's resubmit UX.
            page.evaluate('role=>{const key="chihuitong-prototype-v1-"+role;const p=JSON.parse(localStorage.getItem(key));const c=p.find(x=>x.id===(role==="clinic"?"profile":"clinics")).rows[0];c.profileChanges[0].status="审核不通过";c.profileChanges[0].reason="请核对联系电话";localStorage.setItem(key,JSON.stringify(p))}',role)
            page.reload()
            page.wait_for_selector('.workspace h1')
            if role=='channel':button('详情').first.click()
            button('维护门诊资料').click()
            assert page.get_by_label('前台预约手机号',exact=True).input_value()=='13800000099'
            page.get_by_label('前台预约手机号',exact=True).fill('13800000098')
            button('提交变更审核').click()
            page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
            resubmitted=data(role)
            assert resubmitted['phone']==original['phone']
            assert len(resubmitted['profileChanges'])==2
            assert resubmitted['profileChanges'][1]['reason']=='请核对联系电话'
            print(role+': readonly timeout / unchanged effective profile / pending lock / rejected resubmit passed',flush=True)
        go('platform','tasks?type=clinics')
        row=page.locator('tr').filter(has_text='审核门诊资料变更')
        row.get_by_role('button',name='立即处理',exact=True).click()
        button('详情').first.click()
        page.get_by_text('提交时生效资料',exact=True).wait_for()
        page.get_by_text('申请的新资料',exact=True).wait_for()
        button('退回资料变更').click()
        page.get_by_text('请填写审核意见。',exact=True).wait_for()
        page.get_by_label('变更审核意见',exact=True).fill('联系人信息需要补充')
        before=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform")).find(p=>p.id==="clinics").rows.find(c=>c.id==="MZ-CHANGE-DEMO")')
        page.locator('.arco-drawer').last.screenshot(path=str(ROOT/'platform'/'clinic-change-review.png'))
        button('退回资料变更').click()
        after=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform")).find(p=>p.id==="clinics").rows.find(c=>c.id==="MZ-CHANGE-DEMO")')
        assert after['phone']==before['phone'] and after['profileChanges'][0]['status']=='审核不通过'
        assert page.evaluate('c=>{const a=structuredClone(c);a.profileChanges[0].status="待审核";a.infoVersion=2;return PrototypeClinicInfo.reviewChange(a,a.profileChanges[0].id,true,"通过")}',before)=='生效资料版本已变化，请退回后重新提交。'
        result=page.evaluate('c=>{c.timeout=48;const id=c.profileChanges[0].id;const error=PrototypeClinicInfo.reviewChange(c,id,true,"核实无误");const repeat=PrototypeClinicInfo.reviewChange(c,id,true,"重复");return {c,error,repeat}}',before)
        assert result['error'] is None and result['c']['phone']=='13800000089' and result['c']['timeout']==48
        assert result['repeat']=='申请已处理或不存在，请刷新。'
        assert result['c']['status']==before['status'] and result['c']['contractVersions']==before['contractVersions']
        # Reopen an independent pending fixture to exercise approval in the real UI.
        page.evaluate('c=>{const key="chihuitong-prototype-v1-platform";const pages=JSON.parse(localStorage.getItem(key));const rows=pages.find(p=>p.id==="clinics").rows;rows[rows.findIndex(r=>r.id===c.id)]=c;localStorage.setItem(key,JSON.stringify(pages))}',before)
        page.reload()
        page.wait_for_selector('.workspace h1')
        page.locator('tr').filter(has_text='审核门诊资料变更').get_by_role('button',name='立即处理',exact=True).click()
        button('详情').first.click()
        page.get_by_label('变更审核意见',exact=True).fill('已核对全部变更资料')
        button('通过资料变更').click()
        accepted=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform")).find(p=>p.id==="clinics").rows.find(c=>c.id==="MZ-CHANGE-DEMO")')
        assert accepted['phone']=='13800000089' and accepted['profileChanges'][0]['status']=='审核通过'
        page.set_viewport_size({'width':768,'height':900})
        assert page.locator('.arco-drawer').last.bounding_box()['width']<=768
        page.screenshot(path=str(ROOT/'platform'/'clinic-change-review-narrow.png'))
        assert not errors,errors
        print('platform task rejection / full materials / approval / duplicate / revision / timeout preservation passed; browser errors 0',flush=True)
        browser.close()

if __name__=='__main__':verify()
