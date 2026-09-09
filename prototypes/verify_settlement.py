"""0.20 monthly aggregation and recipient acknowledgement; synthetic local fixtures only."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765'


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def go(role, route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('.workspace h1')
        def button(name, root=None):
            return (root or page).get_by_role('button',name=name,exact=True)
        def data(role):
            return page.evaluate('r=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-"+r))',role)
        def statement(role, sid):
            return next(r for p in data(role) if p['id']=='earnings' for r in p['rows'] if r['id']==sid)
        def inject(role, record):
            # Test-only handoff: the prototype deliberately has no cross-role synchronization.
            page.evaluate('({role,record})=>{const key="chihuitong-prototype-v1-"+role;const p=JSON.parse(localStorage.getItem(key))||PrototypeOperations.migrate(PrototypeWorkflows.migrate(JSON.parse(JSON.stringify(PROTOTYPE.pages))));const e=p.find(p=>p.id==="earnings");e.rows=e.rows.filter(r=>r.id!==record.id);e.rows.unshift(record);localStorage.setItem(key,JSON.stringify(p))}', {'role':role,'record':record})
            page.reload();page.wait_for_selector('.workspace h1')
        def submit():
            button('提交',page.locator('.arco-modal').last).click()
        def close():
            page.locator('.arco-drawer-close-icon').last.click()
            page.wait_for_selector('.arco-drawer',state='hidden')
        def task(title):
            button('立即处理',page.locator('tr').filter(has_text=title)).click()

        for role in ['resource','channel']:
            go(role,'tasks?type=earnings')
            sid='DEMO-RECEIVE-'+role.upper()+'-JUL'
            task('确认本方收款')
            assert button('登记付款').count()==0
            button('确认收款').click();submit()
            assert page.locator('.arco-modal .arco-alert').count()>=2
            button('取消',page.locator('.arco-modal').last).click()
            button('反馈收款异常').click()
            page.get_by_label('处理说明').fill('演示：尚未收到款项，请核查银行流水')
            submit();page.wait_for_selector('.arco-modal',state='hidden')
            issue=statement(role,sid)
            assert issue['status']=='待确认收款' and len(issue['payments'])==1
            assert button('反馈收款异常').is_disabled()
            page.screenshot(path=str(ROOT/role/'receipt-issue.png'))
            close()
            go('platform','tasks?type=earnings');inject('platform',issue)
            task('核查合作方收款异常')
            assert button('确认收款').count()==0 and button('登记付款').count()==0
            button('回复收款异常').click()
            page.get_by_label('处理说明').fill('演示：已核查流水，请再次核实到账')
            submit();page.wait_for_selector('.arco-modal',state='hidden')
            reply=statement('platform',sid)
            assert reply['status']=='待确认收款' and reply['receiptIssues'][0]['status']=='已回复'
            assert button('登记付款').count()==0
            close()
            go(role,'tasks?type=earnings');inject(role,reply)
            task('确认本方收款');button('确认收款').click()
            page.locator('.arco-modal').get_by_text('已核实本单款项全额实际到账',exact=True).click()
            page.screenshot(path=str(ROOT/role/'confirm-receipt.png'))
            submit();page.wait_for_selector('.arco-modal',state='hidden')
            final=statement(role,sid)
            assert final['status']=='已完成' and final['receipt']['paymentId']==final['payments'][0]['id']
            assert final['receipt']['amountCents']==final['totalCents']
            assert final['receiptIssues'][0]['status']=='已关闭'
            assert button('确认收款').count()==0
            close();page.reload();page.wait_for_selector('.workspace h1')
            assert not page.locator('tr').filter(has_text='确认本方收款').count()
            assert sum(r['name']=='合作方确认收款' for r in statement(role,sid)['history'])==1
            print(role+': receipt / issue / platform reply / role boundaries / persistence passed',flush=True)

        go('platform','earnings')
        button('查看历史交易归集').click()
        button('模拟生成9月结算单').click()
        button('确定',page.locator('.arco-modal').last).click()
        page.wait_for_selector('.arco-modal',state='hidden')
        current=[r for p in data('platform') if p['id']=='earnings' for r in p['rows'] if r['id'].startswith('DEMO-SETTLE-')]
        assert len(current)==2
        assert sorted(r['totalCents'] for r in current)==[2400,3600]
        for s in current:
            assert len(s['items'])==2 and s['status']=='待对账确认'
            assert {t['date'][:7] for t in s['items']}=={'2026-07','2026-08'}
            assert all(t['clinicSettlement']=='已结清' and t['clinicSettledAt'].startswith('2026-09') for t in s['items'])
        button('模拟生成9月结算单').click();button('确定',page.locator('.arco-modal').last).click()
        page.wait_for_selector('.arco-modal',state='hidden')
        assert len([r for p in data('platform') if p['id']=='earnings' for r in p['rows'] if r['id'].startswith('DEMO-SETTLE-')])==2
        reasons=page.evaluate('p=>p.find(p=>p.id==="settlementPool").rows.map(t=>[t.id,PrototypeOperations.collectionReason(t,p)])',data('platform'))
        assert all(reason=='门诊未结清' for key,reason in reasons if key.endswith(('UNPAID','PARTIAL','REVIEW')))
        assert all(reason=='下期待归集' for key,reason in reasons if key.endswith('AFTER'))
        assert all(reason=='已入单' for key,reason in reasons if key.endswith(('HISTORY','RECENT','ASSIGNED')))
        page.screenshot(path=str(ROOT/'platform'/'monthly-collection.png'))
        print('historic paid-only aggregation / cutoff / independent parties / assigned-but-unpaid exclusion / idempotency passed',flush=True)
        for role in ['platform','resource','channel','clinic']:
            go(role,'appointments')
            assert page.get_by_text('门诊结算状态',exact=True).count()
            row=page.locator('tr').filter(has_text='DEMO-YY-HISTORY')
            assert '已结清' in row.inner_text()
            button('详情',row).click()
            assert '2026-09-05' in page.locator('.arco-drawer').inner_text()
            assert 'DEMO-CLINIC-HISTORY' in page.locator('.arco-drawer').inner_text()
            close()
            assert '未结清' in page.locator('tr').filter(has_text='DEMO-YY-UNPAID').inner_text()
        print('all backend appointment settlement fields passed',flush=True)
        go('clinic','bills')
        button('详情',page.locator('tr').filter(has_text='历史核销回款演示')).click()
        button('微信扫码支付').click();button('模拟查询：支付成功').click()
        page.locator('.arco-modal-close-icon').click()
        close();go('clinic','appointments')
        assert '已结清' in page.locator('tr').filter(has_text='DEMO-YY-UNPAID').inner_text()
        print('clinic full payment updates associated appointment settlement status passed',flush=True)
        # Old paid records cannot become received simply because the prototype was upgraded.
        go('resource','earnings')
        sid='DEMO-RECEIVE-RESOURCE-JUL';old=statement('resource',sid)
        old['status']='已付款';old.pop('receipt',None)
        old['payments'][0]['amountCents']=1
        inject('resource',old)
        migrated=statement('resource',sid)
        assert migrated['status']=='已付款' and not migrated.get('receipt')
        assert page.get_by_text('待确认收款',exact=True).count()
        go('resource','tasks?type=earnings');task('确认本方收款')
        button('确认收款').click()
        page.locator('.arco-modal').get_by_text('已核实本单款项全额实际到账',exact=True).click();submit()
        assert page.locator('.arco-modal .arco-alert').count()>=2
        assert not statement('resource',sid).get('receipt')
        print('old paid migration / incorrect payment amount blocked passed',flush=True)
        go('platform','earnings')
        assert button('核对归档').count()==0
        assert all(r.get('kind') in ['resource','channel'] for p in data('platform') if p['id']=='earnings' for r in p['rows'])
        migration=browser.new_page()
        migration.goto(BASE+'/platform/#earnings');migration.wait_for_selector('.workspace h1')
        migration.evaluate('()=>{const p=JSON.parse(JSON.stringify(PROTOTYPE.pages));p.find(p=>p.id==="earnings").rows.push({id:"OLD-SELF",kind:"platform",party:"旧平台自收款",name:"旧平台自收款",status:"已归档",items:[],payments:[],history:[]});localStorage.setItem("chihuitong-prototype-v1-platform",JSON.stringify(p))}')
        migration.reload();migration.wait_for_selector('.workspace h1')
        assert migration.get_by_text('旧平台自收款',exact=True).count()==0
        assert migration.evaluate('localStorage.getItem("chihuitong-prototype-v1-platform-before-self-statement-removal").includes("OLD-SELF")')
        migration.close()
        print('no platform self-payee statement / old records backed up and excluded passed',flush=True)
        assert not errors,errors
        browser.close()


if __name__=='__main__':
    verify()
