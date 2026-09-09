"""REQ-030 local prototype transitions and browser flows; no live cross-role sync."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def go(role, route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.reload()
            page.wait_for_selector('h1')

        def button(name):
            return page.get_by_role('button', name=name, exact=True)

        def confirm():
            page.locator('.arco-modal').get_by_role('button', name='确认', exact=True).click()
            page.wait_for_selector('.arco-modal', state='detached')

        def data(role):
            return page.evaluate('(role)=>JSON.parse(localStorage.getItem("chihuitong-"+role+"-mini-v1"))', role)

        def login(role):
            go(role+'-mini', 'home')
            page.locator('.arco-checkbox').click()
            button('手机号授权登录（演示）' if role == 'customer' else '员工手机号授权登录（演示）').click()
            page.wait_for_selector('.count-grid')

        login('customer')
        page.evaluate("""() => {
          const O=PrototypeOverdue,c=x=>JSON.parse(JSON.stringify(x));
          const assert=(v,m)=>{if(!v)throw Error(m)};
          const base=()=>({id:'TEST',status:'成功',date:'2026-09-04',time:'12:00',held:2,used:0,quantity:2,fee:90,expiry:'2027-03-06'});
          const at=h=>new Date(Date.parse('2026-09-04T12:00:00+08:00')+h*3600000).toISOString();
          const rejects=(a,action,role)=>{let failed=false;try{O.act(a,action,role)}catch{failed=true}assert(failed,action+' must reject')};
          let a=base();O.check(a,at(23.999));assert(!O.active(a),'before24');
          O.check(a,at(24));assert(O.active(a)&&a.status==='成功','at24');
          O.check(a,at(71.999));assert(a.status==='成功','before72');
          O.check(a,at(72));assert(a.status==='完成'&&a.completionSource==='系统超时处理'&&a.held===2&&a.used===0&&!a.redemptionId,'at72 no fee');
          assert(!O.active(a)&&a.customerPending,'closed task / customer pending');
          let size=a.overdueHistory.length;O.check(a,at(90));assert(a.overdueHistory.length===size&&a.overdueTasks.length===1,'idempotent timer');
          let b=c(a);O.act(b,'restore','customer');assert(b.held===0&&b.status==='取消'&&!b.customerPending&&!b.redemptionId,'restore');rejects(b,'restore','customer');rejects(b,'redeem','clinic');
          b=c(a);O.act(b,'attended','customer');assert(b.overdueTasks.length===2&&O.active(b).status==='待补核销'&&!b.redemptionId&&b.held===2,'new supplement task');rejects(b,'attended','customer');rejects(b,'restore','customer');
          O.act(b,'redeem','clinic');assert(b.used===2&&b.held===0&&b.fee===90&&!O.active(b),'snapshot quantity and fee');rejects(b,'redeem','clinic');rejects(b,'restore','customer');
          b=base();O.act(b,'absent','clinic');assert(b.status==='取消'&&b.held===2&&b.customerPending,'clinic absence held');rejects(b,'redeem','clinic');O.act(b,'attended','customer');assert(b.conflict&&O.active(b).status==='异常搁置','contradiction');rejects(b,'restore','customer');rejects(b,'redeem','clinic');
          for(const extra of [{change:{date:'2026-09-09'}},{feedback:'已到诊'},{conflict:true}]){b=Object.assign(base(),extra);O.check(b,at(80));assert(b.status==='成功'&&b.held===2,'block auto with change/feedback/conflict');rejects(b,'absent','clinic');}
          b=base();b.status='待确认';O.check(b,at(80));assert(b.status==='待确认'&&!O.active(b),'pending separate');
          b=base();O.check(b,at(24));b.date='2026-09-08';O.rescheduled(b);O.check(b,at(80));assert(!O.active(b)&&b.status==='成功','reschedule clock reset');O.check(b,'2026-09-09T12:00:00+08:00');assert(O.active(b)&&b.overdueTasks.length===2,'new cycle overdue');
          b=c(a);b.expiry='2026-09-06';O.act(b,'redeem','clinic');assert(b.used===2,'valid appointment supports late scan');b=c(a);b.expiry='2026-09-03';rejects(b,'redeem','clinic');b.expiry='2026-09-06';O.act(b,'restore','customer');assert(b.expiry==='2026-09-06'&&b.held===0,'release not extend expired');
          b=c(a);b.frozen=true;rejects(b,'redeem','clinic');
          b=c(a);b.held=1;rejects(b,'redeem','clinic');rejects(b,'restore','customer');
          b=c(a);delete b.fee;rejects(b,'redeem','clinic');
          rejects(c(a),'redeem','customer');rejects(c(a),'restore','clinic');rejects(c(a),'absent','channel');
        }""")
        print('24/72 boundaries, task versions, snapshot fee, expired/frozen, mutual exclusion and roles passed', flush=True)
        assert button('处理预约 OD72').count() == 1
        assert button('处理预约 ODABS').count() == 1
        page.screenshot(path=str(ROOT/'customer-mini'/'overdue-home.png'), full_page=True)
        button('处理预约 OD72').click()
        assert '尚未核销' in page.locator('main').inner_text()
        assert button('已到诊，完成治疗').count() == 1
        page.screenshot(path=str(ROOT/'customer-mini'/'overdue-detail.png'))
        button('未到诊，申请恢复权益').click(); confirm()
        d = data('customer')
        assert next(a for a in d['appointments'] if a['id']=='OD72')['released']
        assert next(b for b in d['benefits'] if b['id']=='B-OD72')['held'] == 0
        go('customer-mini', 'home')
        assert button('处理预约 OD72').count() == 0
        assert button('处理预约 ODABS').count() == 1
        go('customer-mini', 'feedback/ODABS')
        button('未到诊，申请恢复权益').click(); confirm()
        assert next(b for b in data('customer')['benefits'] if b['id']=='B-ODABS')['held'] == 0
        # Explicit test handoff fixture, not a product cross-role synchronizer.
        go('customer-mini', 'feedback/OD24')
        button('已到诊，完成治疗').click(); confirm()
        attended = next(a for a in data('customer')['appointments'] if a['id']=='OD24')
        assert attended['overdueTasks'][-1]['status'] == '待补核销'
        assert attended['held'] == 1 and attended['used'] == 0

        login('clinic')
        before = data('clinic')
        go('clinic-mini', 'feedback/OD24')
        button('患者未到，取消预约').click(); confirm()
        d=data('clinic'); a=next(a for a in d['appointments'] if a['id']=='OD24')
        assert a['status']=='取消' and a['held']==1 and a['customerPending']
        assert d['redemptions']==before['redemptions']
        go('clinic-mini', 'cancel/V4')
        assert button('确认无法接诊').count() == 0
        go('clinic-mini', 'feedback/OD72')
        button('补核销').click()
        button('读取演示凭证').click()
        assert '60元' in page.locator('main').inner_text()
        page.locator('.arco-checkbox').click()
        button('确认核销').click(); confirm()
        d=data('clinic'); a=next(a for a in d['appointments'] if a['id']=='OD72')
        assert a['status']=='完成' and a['completionSource']=='门诊核销完成' and a['used']==1 and a['held']==0
        assert d['redemptions'][0]['amount']==60 and len(d['redemptions'])==len(before['redemptions'])+1
        # Transfer just the equivalent original appointment's feedback, using test-only data injection.
        page.evaluate("""a=>{let d=JSON.parse(localStorage.getItem('chihuitong-clinic-mini-v1'));let item=d.appointments.find(x=>x.id===a.id);Object.assign(item,{status:a.status,held:a.held,feedback:a.feedback,customerFeedback:a.customerFeedback,overdueTasks:a.overdueTasks,clinicFeedback:'',conflict:false});localStorage.setItem('chihuitong-clinic-mini-v1',JSON.stringify(d))}""", attended)
        go('clinic-mini', 'followups')
        page.get_by_role('tab', name='待补核销（1）', exact=True).click()
        button('处理预约 OD24').click()
        assert button('补核销').is_enabled()
        for width in [375, 390, 430]:
            page.set_viewport_size({'width': width, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT/'clinic-mini'/'overdue-supplement.png'))
        print('customer restore/home + clinic absence/supplement + explicit test handoff + mobile widths passed', flush=True)

        page.set_viewport_size({'width':1440,'height':900})
        go('clinic', 'tasks?type=followups')
        page.get_by_role('row').filter(has_text='OD24').get_by_role('button', name='立即处理').click()
        drawer=page.locator('.arco-drawer')
        drawer.get_by_role('button', name='患者未到，取消预约', exact=True).click(); confirm()
        a=page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-clinic')).find(p=>p.id==='appointments').rows.find(a=>a.id==='OD24')")
        assert a['status']=='取消' and a['held']==1 and a['clinicSettlement']=='未产生费用' and a['used']==0
        go('clinic','followups')
        page.get_by_role('tab',name='已关闭（3）',exact=True).click()
        page.screenshot(path=str(ROOT/'clinic'/'overdue-tasks.png'), full_page=True)
        page.get_by_role('row').filter(has_text='OD72').get_by_role('button',name='查看并处理').click()
        page.set_viewport_size({'width':768,'height':900});page.wait_for_timeout(400)
        rect=page.locator('.arco-drawer').bounding_box()
        assert rect['x']>=-1 and rect['x']+rect['width']<=769
        assert '尚未核销' in page.locator('.arco-drawer').inner_text()
        page.screenshot(path=str(ROOT/'clinic'/'overdue-narrow.png'))
        # Fresh isolated browser storage for the inline reschedule form.
        page.evaluate("localStorage.removeItem('chihuitong-prototype-v1-clinic')")
        go('clinic', 'followups')
        page.get_by_role('row').filter(has_text='OD24').get_by_role('button',name='查看并处理').click()
        drawer=page.locator('.arco-drawer')
        drawer.get_by_role('button',name='协商后改期',exact=True).click()
        drawer.get_by_role('button',name='确认改期',exact=True).click()
        assert '请确认已与客户协商一致' in drawer.inner_text()
        drawer.locator('.arco-checkbox').click()
        date_input=drawer.locator('.flow-field').filter(has=page.get_by_text('新的预约日期',exact=True)).locator('input')
        date_input.fill('2028-01-01');date_input.press('Enter')
        drawer.get_by_role('button',name='确认改期',exact=True).click()
        assert '不超过权益到期日' in drawer.inner_text()
        date_input.fill('2026-09-08');date_input.press('Enter')
        drawer.get_by_role('button',name='确认改期',exact=True).click()
        a=page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-clinic')).find(p=>p.id==='appointments').rows.find(a=>a.id==='OD24')")
        assert a['date']=='2026-09-08' and a['held']==1 and a['used']==0
        assert a['overdueManaged'] and all(t['status']=='已关闭' for t in a['overdueTasks'])
        assert a['overdueHistory'][-1]['name']=='按新的确认时间重新计时'
        print('inline reschedule agreement/expiry + retained reservation + new timer cycle passed',flush=True)
        for role in ['platform','resource','channel']:
            go(role,'appointments')
            assert '系统超时处理' in page.locator('main').inner_text()
            assert button('患者未到，取消预约').count()==0
        print('backend task action + appointment source labels + readonly roles passed',flush=True)
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    verify()
