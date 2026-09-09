"""Institution identity, fail-closed data scope and object logs (fictional fixtures)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent

def verify():
    with sync_playwright() as p:
        b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(8000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def go(role,path):
            page.goto(f'http://127.0.0.1:8765/{role}/#{path}');page.wait_for_selector('.workspace h1')
        for role in ['resource','channel']:
            go(role,'accounts')
            page.get_by_role('button',name='编辑（初始管理员）',exact=True).click()
            assert page.get_by_label('身份',exact=True).get_attribute('aria-disabled')=='true' or page.locator('.arco-select-disabled').count()
            page.locator('.arco-modal').get_by_role('button',name='取消',exact=True).click()
            page.get_by_role('button',name='创建账号',exact=True).click()
            page.get_by_label('姓名',exact=True).fill('新增员工（演示）')
            page.get_by_label('登录手机号',exact=True).fill('13800000076')
            page.get_by_role('button',name='保存账号',exact=True).click()
            page.wait_for_selector('.arco-modal',state='detached')
            assert page.locator('tr').filter(has_text='新增员工（演示）').count()
            page.get_by_label('本机构演示账号',exact=True).click()
            page.get_by_text('陈宁（演示） · 业务员',exact=True).last.click()
            page.wait_for_timeout(200)
            assert page.evaluate('PrototypeManagement.session().role')=='业务员'
            page.reload();page.wait_for_selector('.workspace h1')
            assert page.evaluate('PrototypeManagement.session().role')=='业务员'
            fixture=[{'id':'clinics','rows':[{'id':'C1','name':'本人门诊','ownerUserId':'USER-002'},{'id':'C2','name':'其他门诊','ownerUserId':'OTHER'}]}, {'id':'sales','rows':[{'id':'O1','ownerUserId':'USER-002','cards':[{'id':'CARD1','customerId':'P1'}]},{'id':'O2','ownerUserId':'OTHER'}]}, {'id':'appointments','rows':[{'id':'A1','clinicId':'C1','orderId':'O1'},{'id':'A2','clinicId':'C2','orderId':'O2'}]}, {'id':'earnings','rows':[{'id':'B1','items':[{'clinicId':'C1','orderId':'O1'}]},{'id':'B2','items':[{'clinicId':'C1','orderId':'O1'},{'clinicId':'C2','orderId':'O2'}]}]}, {'id':'accounts','rows':[{'id':'USER-002','role':'业务员'},{'id':'OTHER','role':'管理员'}]}, {'id':'salesCustomers','rows':[{'id':'P1'},{'id':'P2'}]}]
            scoped=page.evaluate('p=>PrototypeManagement.project(p)',fixture)
            assert next(p for p in scoped if p['id']=='appointments')['rows']==fixture[2]['rows'][:1]
            assert [r['id'] for r in next(p for p in scoped if p['id']=='earnings')['rows']]==['B1','B2']
            assert all(r['scopeOnly'] and len(r['items'])==1 and 'payments' not in r for r in next(p for p in scoped if p['id']=='earnings')['rows'])
            checked=page.evaluate('p=>{const M=PrototypeManagement,v=M.project(p),n=structuredClone(v);n.find(p=>p.id==="appointments").rows[0].status="完成";const merged=M.merge(p,v,n);let error="";n.find(p=>p.id==="appointments").rows.push({id:"A2",status:"完成"});try{M.merge(p,v,n)}catch(e){error=e.message}return {merged,error}}',fixture)
            assert checked['merged'][2]['rows'][1]==fixture[2]['rows'][1]
            assert checked['error']=='不能更新范围外数据。'
            assert page.evaluate('PrototypeManagement.accountError([],null,{name:"越权",phone:"13800000077",role:"管理员"})')=='仅机构管理员可管理账号。'
            page.screenshot(path=str(ROOT/role/'staff-scope.png'))
            print(role+': protected initial admin, account creation, staff scope, mixed-bill own-detail projection and scoped merge passed',flush=True)
        go('platform','institutions')
        page.get_by_role('button',name='新增机构',exact=True).click()
        for label,value in [('机构名称','新建测试机构'),('联系人','演示联系人'),('联系手机号','13800000066'),('初始管理员姓名','首位管理员'),('初始管理员登录手机号','13800000065')]:
            page.locator('.arco-form-item').filter(has_text=label).locator('input').fill(value)
        field=page.locator('.arco-form-item').filter(has_text='机构类型')
        field.locator('.arco-select').click();page.get_by_text('保险公司',exact=True).last.click()
        page.locator('.arco-drawer').last.get_by_role('button',name='新增机构',exact=True).click()
        page.wait_for_selector('.arco-drawer:has(.arco-form)',state='detached')
        inst=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform")).find(p=>p.id==="institutions").rows.find(r=>r.name==="新建测试机构")')
        assert inst['adminAccount']['role']=='管理员' and inst['adminAccount']['platformCreated']
        go('platform','clinics')
        row=page.locator('tr').filter(has_text='明禾口腔（演示）')
        row.get_by_role('button',name='下线',exact=True).click()
        page.get_by_role('button',name='确认下线',exact=True).click()
        page.get_by_text('请填写上下线原因。',exact=True).wait_for()
        page.get_by_label('上下线原因',exact=True).fill('演示门诊整修')
        page.get_by_role('button',name='确认下线',exact=True).click()
        row.get_by_role('button',name='详情',exact=True).click()
        assert page.get_by_role('button',name='暂停接入新预约',exact=True).count()==0
        page.get_by_role('tab',name='操作记录',exact=True).click()
        page.get_by_text('演示门诊整修',exact=True).wait_for()
        page.screenshot(path=str(ROOT/'platform'/'clinic-operation-logs.png'))
        c=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform")).find(p=>p.id==="clinics").rows.find(r=>r.name==="明禾口腔（演示）")')
        assert c['operationLogs'][0]['action']=='门诊下线' and c['operationLogs'][0]['reason']=='演示门诊整修'
        for role,route in [('platform','earnings'),('clinic','bills'),('resource','sales')]:
            go(role,route)
            if role=='resource':
                page.get_by_label('本机构演示账号',exact=True).click();page.get_by_text('林晓（演示） · 管理员',exact=True).last.click();page.goto('http://127.0.0.1:8765/resource/#sales')
            page.get_by_role('button',name='详情',exact=True).first.click()
            page.get_by_role('heading',name='操作记录',exact=True).wait_for()
        assert not errors,errors
        print('platform initial-admin transaction, list offline modal and clinic/bill/statement/order logs passed; browser errors 0',flush=True)
        b.close()

if __name__=='__main__':verify()
