"""REQ-036: mobile identities, bill interactions, inline rules and appointment code."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent
KEY = 'chihuitong-clinic-mini-v1'


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def go(role, route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('h1')

        def button(name):
            return page.get_by_role('button', name=name, exact=True)

        def confirm():
            page.locator('.arco-modal').get_by_role('button', name='确认', exact=True).click()
            page.wait_for_selector('.arco-modal', state='detached')

        def choose(label, value):
            page.locator('.field').filter(has=page.get_by_text(label, exact=True)).locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=value).click()

        def clinic_data():
            return page.evaluate('(key)=>JSON.parse(localStorage.getItem(key))', KEY)

        go('clinic-mini', 'home')
        page.locator('.arco-checkbox').click()
        button('员工手机号授权登录（演示）').click()
        assert clinic_data()['identity'] == '员工'
        for route in ['home', 'profile']:
            go('clinic-mini', route)
            assert button('账单与收款').count() == 0
            assert '合同到期' not in page.locator('main').inner_text()
        for route in ['bill', 'bills', 'credit', 'contract']:
            go('clinic-mini', route)
            assert '无权访问' in page.locator('main').inner_text()
            assert '600.00' not in page.locator('main').inner_text()
        page.reload()
        assert '无权访问' in page.locator('main').inner_text()
        page.evaluate("""() => {
          let rejected=false;try{ClinicFinance.act(JSON.parse(localStorage.getItem('chihuitong-clinic-mini-v1')),'start',{version:1})}catch{rejected=true}
          if(!rejected)throw Error('staff financial mutation allowed');
        }""")
        go('clinic-mini', 'profile');button('退出登录').click()
        choose('演示登录身份', '已开通管理员')
        page.locator('.arco-checkbox').click();button('员工手机号授权登录（演示）').click()
        go('clinic-mini', 'contract');assert 'HT-MH-DEMO' in page.locator('main').inner_text()
        go('clinic-mini', 'bill')
        page.evaluate("""() => {
          const d=JSON.parse(localStorage.getItem('chihuitong-clinic-mini-v1'));
          const legacy=Mini.clone(d);delete legacy.identity;
          if(ClinicFinance.migrate(legacy).logged)throw Error('legacy identity escalated');
          const rejects=(x,a,v)=>{let fail=false;try{ClinicFinance.act(x,a,v)}catch{fail=true}if(!fail)throw Error('invalid financial action accepted')};
          const x=Mini.clone(d);x.redemptions.find(r=>r.id==='R1').status='已撤销';rejects(x,'start',{version:1});
          const v={version:1,amount:600,date:'2026-02-30T10:00',payer:'演示',reference:'REF',files:[{url:'data:image/png;base64,AA==',verified:true}]};
          rejects(d,'voucher',v);rejects(d,'voucher',{...v,date:'2027-01-01T10:00'});
          const pending=ClinicFinance.act(d,'start',{version:1});rejects(pending,'start',{version:1});rejects(pending,'voucher',{...v,date:'2026-09-07T10:00'});
        }""")
        button('微信支付').click();confirm()
        assert clinic_data()['bill']['status'] == '待付款'
        assert button('上传付款凭证').is_disabled()
        button('模拟返回支付结果').click()
        assert clinic_data()['bill']['payment'] == '结果未知'
        choose('模拟服务端结果（仅评审）', '支付失败');button('模拟返回支付结果').click()
        assert clinic_data()['bill']['status'] == '待付款'
        button('上传付款凭证').click()
        button('提交平台审核').click();confirm()
        assert page.get_by_role('alert').count() > 0
        page.get_by_label('付款方', exact=True).fill('演示门诊经营主体')
        page.get_by_label('交易参考号', exact=True).fill('BANK-DEMO-001')
        page.locator('input[type=file]').set_input_files({'name':'invalid.png','mimeType':'image/png','buffer':b'invalid'})
        page.get_by_text('图片无法解码，请更换文件', exact=True).wait_for()
        # Known harmless image already in repository; never upload real payment data.
        page.locator('input[type=file]').set_input_files(str(ROOT/'customer-mini'/'credential.png'))
        button('移除凭证 1').wait_for()
        page.get_by_label('付款金额（元）', exact=True).fill('1')
        button('提交平台审核').click();confirm()
        page.get_by_text('请提交本账单全额600.00元付款凭证', exact=True).wait_for()
        page.get_by_label('付款金额（元）', exact=True).fill('600.00')
        button('提交平台审核').click();confirm()
        assert clinic_data()['bill']['status'] == '付款待审核'
        assert button('微信支付').is_disabled()
        assert button('审核通过').count() == 0
        page.reload();assert clinic_data()['bill']['status'] == '付款待审核'
        page.evaluate('scrollTo(0,0)');page.screenshot(path=str(ROOT/'clinic-mini'/'bill-voucher.png'), full_page=True)
        # Explicit independent platform rejection fixture, not cross-role synchronization.
        page.evaluate("""key=>{let d=JSON.parse(localStorage.getItem(key));d.bill.status='待付款';d.bill.submissions[0].status='审核退回';localStorage.setItem(key,JSON.stringify(d))}""", KEY)
        page.reload();assert button('上传付款凭证').is_enabled()
        button('微信支付').click();confirm()
        choose('模拟服务端结果（仅评审）', '支付取消');button('模拟返回支付结果').click()
        assert clinic_data()['bill']['status'] == '待付款'
        button('微信支付').click();confirm()
        choose('模拟服务端结果（仅评审）', '支付成功');button('模拟返回支付结果').click()
        assert clinic_data()['bill']['status'] == '已结清'
        assert clinic_data()['baseDebt'] == 0
        assert next(r for r in clinic_data()['redemptions'] if r['id']=='R1')['settled']
        assert button('微信支付').count() == 0
        page.evaluate("""() => {
          const d=JSON.parse(localStorage.getItem('chihuitong-clinic-mini-v1'));
          for(const change of [null,'staff','logged-out','version']){
            let x=Mini.clone(d),failed=false;if(change==='staff')x.identity='员工';if(change==='logged-out')x.logged=false;if(change==='version')x.bill.status='待付款';
            try{ClinicFinance.act(x,'start',{version:change==='version'?0:1})}catch{failed=true}
            if(!failed)throw Error('invalid payment accepted '+change);
          }
        }""")
        print('staff routes/mutations; admin voucher validation, pending, retry and payment outcomes passed', flush=True)

        go('customer-mini', 'home');page.locator('.arco-checkbox').click();button('手机号授权登录（演示）').click()
        go('customer-mini', 'benefits')
        assert button('查看权益').count() == 0
        assert page.get_by_text('使用规则', exact=True).count() > 0
        card = page.locator('.card').filter(has=page.get_by_text('B2', exact=True))
        card.get_by_role('button', name='预约门诊', exact=True).click()
        page.wait_for_url('**/#clinics/B2')
        go('customer-mini', 'benefits')
        for bid in ['B3','B4','B5']:
            assert page.locator('.card').filter(has=page.get_by_text(bid, exact=True)).get_by_role('button', name='预约门诊').is_disabled()
        page.screenshot(path=str(ROOT/'customer-mini'/'benefit-rules.png'), full_page=True)
        go('customer-mini', 'appointment/A1')
        assert page.locator('.qr-demo').count() == 1
        assert button('出示权益凭证').count() == 0
        assert 'DEMO-B3' in page.locator('main').inner_text()
        page.reload();assert 'DEMO-B3' in page.locator('main').inner_text()
        page.screenshot(path=str(ROOT/'customer-mini'/'appointment-code.png'), full_page=True)
        for route, count in [('appointment/A2',0),('appointment/OD72',1),('appointment/ODABS',0)]:
            go('customer-mini', route);assert page.locator('.qr-demo').count() == count, route
        for scene in ['cancel','redeemed','frozen','expired','released','change','conflict']:
            page.evaluate("""scene=>{
              const key='chihuitong-customer-mini-v1',d=JSON.parse(localStorage.getItem(key));
              const a=d.appointments.find(a=>a.id==='A1'),b=d.benefits.find(b=>b.id==='B3');
              Object.assign(a,{status:'成功',used:0,released:false,change:null,conflict:false});Object.assign(b,{state:'已领取',expiry:'2027-03-06',held:1});
              if(scene==='cancel')a.status='取消';if(scene==='redeemed')a.used=1;if(scene==='frozen')b.state='已冻结';if(scene==='expired')b.expiry='2026-01-01';if(scene==='released')a.released=true;if(scene==='change')a.change={date:'2026-09-10',time:'10:00'};if(scene==='conflict')a.conflict=true;
              localStorage.setItem(key,JSON.stringify(d));
            }""", scene)
            go('customer-mini','appointment/A1');page.reload();assert page.locator('.qr-demo').count() == 0, scene
        for width in [375,390,430]:
            page.set_viewport_size({'width':width,'height':844})
            for role,route in [('customer-mini','appointment/OD72'),('customer-mini','benefits'),('clinic-mini','bill'),('clinic-mini','contract')]:
                go(role,route);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width,route)
        print('inline rules, direct selected benefit booking, fixed inline QR and blocked states; 375/390/430px passed', flush=True)

        page.set_viewport_size({'width':1440,'height':900})
        go('clinic','accounts')
        if button('进入门诊后台').count():button('进入门诊后台').click()
        page.evaluate("""() => {
          const page=PROTOTYPE.pages.find(p=>p.id==='accounts');
          const options=page.create.fields.find(f=>f.key==='role').options;
          if(JSON.stringify(options)!==JSON.stringify(['管理员','员工']))throw Error('clinic role labels');
          const rows=[{id:'accounts',rows:[{role:'机构管理员'},{role:'业务操作员'},{role:'业务员'}]}];
          PrototypeManagement.migrate(rows);if(rows[0].rows.map(x=>x.role).join()!=='管理员,员工,员工')throw Error('legacy labels');
        }""")
        assert not errors, errors
        print('clinic backend role labels/legacy cache passed; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
