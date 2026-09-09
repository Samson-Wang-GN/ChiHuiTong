"""REQ-037 regression: local fictional UI and deterministic rule assertions."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        button = lambda name: page.get_by_role('button', name=name, exact=True)

        def go(role, route=''):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_timeout(250)

        def confirm():
            page.locator('.arco-modal').get_by_role('button', name='确认', exact=True).click()
            page.wait_for_selector('.arco-modal', state='detached')

        def data(role):
            return page.evaluate('(role)=>JSON.parse(localStorage.getItem("chihuitong-"+role+"-mini-v1"))', role)

        go('platform')
        page.evaluate("""() => {
          const R=PrototypeRules,O=PrototypeOverdue,ok=(v,m)=>{if(!v)throw Error(m)},reject=fn=>{let e=false;try{fn()}catch{e=true}ok(e,'expected rejection')};
          ok(R.cents('1.005')===101 && R.cents('-1.005')===-101,'half-up cents');
          const d=R.allocation('0.05',{mode:'按比例',value:10},{mode:'按金额',value:0.01});
          ok(d.sourceCents===1&&d.channelCents===1&&d.platformCents===3,'conservation');
          reject(()=>R.allocation(1,{mode:'按金额',value:1},{mode:'按金额',value:1}));
          ok(R.deadline('2026-09-01','月结')==='2026-09-06','monthly natural days');
          ok(R.deadline('2026-09-07','周结')==='2026-09-10','weekly excludes issue day');
          ok(R.deadline('2028-02-28','周结')==='2028-03-02','leap-year boundary');
          const rows=[{id:1,date:'2026-07-01'},{id:2,date:'2026-08-01',billId:'issued'},{id:3,date:'2026-09-01',cancelled:true},{id:4,date:'2026-10-01'}];
          ok(R.collectUnbilled(rows,'月结','2026-10-01').map(x=>x.id).join()==='1','backlog not issued/cancelled/future');
          reject(()=>R.collectUnbilled(rows,'月结','2026-09-07'));
          let a={id:'SPECIAL',status:'完成',completionSource:'系统超时处理',date:'2026-09-06',time:'10:00',expiry:'2026-09-06',held:1,used:0,quantity:1,fee:80,feeRuleVersion:'V2',customerFeedback:'已到诊'};
          O.act(a,'redeem','clinic');ok(a.feeSnapshot.amount===80&&a.preRedemption.completionSource==='系统超时处理','lock at redemption');
          const r={id:'R',status:'已核销',settled:false,quantity:1};O.reverse(a,r);
          ok(a.status==='完成'&&a.pendingRestore===1&&a.used===0&&a.held===0&&!O.active(a),'special reversal separate quantity');
          reject(()=>O.act(a,'redeem','clinic'));O.act(a,'restore','customer');ok(a.released&&!a.pendingRestore&&a.expiry==='2026-09-06','new request despite prior attended, no extension');reject(()=>O.act(a,'restore','customer'));
          ok(R.reversalError({status:'已核销',settled:true}), 'settled rejects');
          ok(R.reversalError({status:'已核销'},{payment:'结果未知'}),'unresolved rejects');
        }""")
        print('rounding, conservation, natural-day deadlines, backlog, reversal quantities and validity passed', flush=True)

        for role in ['platform', 'resource', 'channel', 'clinic']:
            go(role)
            button('退出').click()
            assert page.get_by_placeholder('填写演示密码，不要使用真实凭据').count() == 0
            button('进入演示后台').click()
            assert '请先获取有效验证码' in page.locator('body').inner_text()
            page.get_by_placeholder('预开通的演示手机号').fill('13800000001')
            button('获取验证码（演示）').click()
            page.get_by_placeholder('6位演示验证码').fill('000000')
            button('进入演示后台').click()
            assert page.locator('.login').count() == 1
            page.get_by_placeholder('6位演示验证码').fill('123456')
            if role == 'platform':
                page.screenshot(path=str(ROOT/'platform'/'phone-login.png'))
            button('进入演示后台').click()
            page.wait_for_selector('.workspace h1')
        print('four independent phone/code login demos passed', flush=True)

        go('platform', 'clinics')
        page.locator('tr').filter(has_text='明禾口腔（演示）').get_by_role('button', name='详情', exact=True).click()
        page.get_by_text('合同与续签', exact=True).click()
        page.get_by_label('变更审核意见', exact=True).fill('测试周结改月结，全部未出账纳入新周期')
        button('加载渠道申请示例（仅评审）').click()
        button('通过账期变更').click()
        assert '当前月结' in page.locator('.arco-drawer').inner_text()
        button('加载未出账交易示例').click()
        button('模拟按当前账期出账').click()
        stored=page.evaluate('JSON.parse(localStorage.getItem("chihuitong-prototype-v1-platform"))')
        bill=next(b for b in next(p for p in stored if p['id']=='bills')['rows'] if b['id'].startswith('CYCLE-BILL-'))
        assert bill['amount']==120 and len(bill['items'])==2 and bill['deadline']=='2026-10-06'
        button('模拟按当前账期出账').click()
        assert '无可出账交易，不重复生成' in page.locator('.arco-drawer').inner_text()
        page.screenshot(path=str(ROOT/'platform'/'cycle-change.png'), full_page=True)
        print('contract-cycle approval, old+new backlog, deadline and duplicate issuance UI passed', flush=True)

        for role in ['resource','channel']:
            go(role,'earnings')
            page.evaluate("""() => {
              let p=PrototypeWorkflows.migrate(structuredClone(PROTOTYPE.pages));p=PrototypeOperations.migrate(p);p=PrototypeSales.migrate(p);p=PrototypeManagement.migrate(p);
              const e=p.find(p=>p.id==='earnings'),base=structuredClone(e.rows.find(r=>r.items).items[0]);
              e.rows=[{id:'SCOPE-TEST',kind:PROTOTYPE.role,party:PROTOTYPE.org,totalCents:2400,status:'待对账确认',version:1,items:[{...base,id:'MY-T',ownerUserId:'USER-002',amountCents:1200},{...base,id:'SECRET-OTHER-T',ownerUserId:'OTHER',clinic:'其他门诊',clinicId:'OTHER',orderId:'OTHER',amountCents:1200}],history:[],payments:[],receiptIssues:[]}];
              localStorage.setItem('chihuitong-prototype-v1-'+PROTOTYPE.role,JSON.stringify(p));sessionStorage.setItem('chihuitong-demo-account-'+PROTOTYPE.role,'USER-002');
            }""")
            page.reload();page.get_by_text('本人收益明细',exact=True).wait_for()
            assert 'SECRET-OTHER-T' not in page.locator('body').inner_text()
            assert button('确认对账单').count()==0 and button('确认收款').count()==0
            button('下载Excel').click()
            with page.expect_download() as download:
                page.locator('.arco-modal').get_by_role('button',name='确定',exact=True).click()
            page.wait_for_selector('.arco-modal',state='detached')
            import zipfile
            with zipfile.ZipFile(download.value.path()) as z:
                xml=''.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.xml'))
                assert 'MY-T' in xml and 'SECRET-OTHER-T' not in xml and '完整单据金额' not in xml
            page.screenshot(path=str(ROOT/role/'own-statement-details.png'),full_page=True)
        print('salesperson own-details-only UI and scoped Excel; no whole statement actions passed',flush=True)

        page.set_viewport_size({'width':390,'height':844})
        go('clinic-mini')
        page.locator('.arco-select').click()
        page.get_by_text('已开通管理员', exact=True).last.click()
        page.locator('.arco-checkbox').click();button('员工手机号授权登录（演示）').click()
        page.evaluate("""() => {
          const d=JSON.parse(localStorage.getItem('chihuitong-clinic-mini-v1')),F=ClinicFinance;
          let rejected=false;try{F.reverse(d,'R2','test')}catch{rejected=true}if(!rejected)throw Error('settled reversal accepted');
          const pending=F.act(d,'start',{version:d.bill.version});rejected=false;try{F.reverse(pending,'R1','test')}catch{rejected=true}if(!rejected)throw Error('unresolved reversal accepted');
          const reversed=F.reverse(d,'R1','误核销');if(reversed.bill.amount!==540||reversed.bill.items.length!==9||reversed.bill.removed.length!==1||reversed.bill.version!==2)throw Error('bill revision incorrect');
          if(F.act(reversed,'start',{version:2}).bill.amount!==540)throw Error('revised payment amount');
          const empty=Mini.clone(d);empty.bill.items=[{id:'R1',amount:60}];empty.bill.amount=60;
          if(F.reverse(empty,'R1','test').bill.status!=='已取消')throw Error('zero bill should cancel, not paid');
        }""")
        go('clinic-mini','scan')
        page.get_by_placeholder('VISIT-001').fill('VISIT-ODLATE');button('读取演示凭证').click()
        assert '可核销' in page.locator('main').inner_text()
        page.get_by_label('模拟平台调价（仅评审，不是门诊业务操作）',exact=True).click()
        page.get_by_text('80元 / 调价后规则V2',exact=True).last.click()
        page.locator('.arco-checkbox').click();button('确认核销').click();confirm()
        d=data('clinic');r=d['redemptions'][0]
        assert r['amount']==80 and r['feeSnapshot']['ruleVersion']=='演示V2'
        go('clinic-mini','revoke/'+r['id'])
        page.get_by_placeholder('请输入错误核销的原因').fill('复核后撤销');button('提交撤销').click();confirm()
        assert data('clinic')['redemptions'][0]['status']=='已撤销'
        print('late redemption, current fee lock, unsettled bill revision and settled/payment guards passed', flush=True)

        go('customer-mini')
        page.locator('.arco-checkbox').click();button('手机号授权登录（演示）').click()
        button('处理预约 ODREV').click()
        assert button('未到诊，申请恢复权益').count()==0
        assert button('已到诊，完成治疗').count()==0
        page.screenshot(path=str(ROOT/'customer-mini'/'restore-after-reversal.png'),full_page=True)
        button('申请恢复权益').click();confirm()
        d=data('customer');a=next(a for a in d['appointments'] if a['id']=='ODREV');benefit=next(b for b in d['benefits'] if b['id']=='B-ODREV')
        assert a['released'] and not a['customerPending'] and benefit['pendingRestore']==0 and benefit['held']==0
        page.reload();assert button('申请恢复权益').count()==0
        go('customer-mini','appointment/ODLATE')
        assert page.locator('.qr-demo').count()==1
        for width in [375,390,430]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print('persistent restore message, one-time release, late-valid QR and mobile layout passed; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
