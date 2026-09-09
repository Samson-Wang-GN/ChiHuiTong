"""两个独立小程序浏览器原型的页面、移动布局及业务模拟验证。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE='http://127.0.0.1:8765'
ROOT=Path(__file__).resolve().parent


def verify():
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':390,'height':844},locale='zh-CN')
        page.set_default_timeout(8000)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))

        def go(role,route):
            page.goto(f'{BASE}/{role}-mini/#{route}')
            page.wait_for_selector('.phone')

        def button(name):
            return page.get_by_role('button',name=name,exact=True)

        def confirm():
            page.locator('.arco-modal').get_by_role('button',name='确认',exact=True).click()
            page.wait_for_selector('.arco-modal',state='detached')

        def data(role):
            return page.evaluate(f"JSON.parse(localStorage.getItem('chihuitong-{role}-mini-v1'))")

        for role in ['customer','clinic']:
            go(role,'home')
            login='手机号授权登录（演示）' if role=='customer' else '员工手机号授权登录（演示）'
            button(login).click()
            assert page.get_by_role('alert').count()>0
            page.locator('.arco-checkbox').click()
            if role=='clinic':
                page.locator('.arco-select').click()
                page.locator('.arco-select-option').filter(has_text='已开通管理员').click()
            button(login).click()
            page.wait_for_selector('.count-grid')
            page.screenshot(path=str(ROOT/f'{role}-mini'/'preview.png'))
            routes=page.evaluate('window.MINI.routes')
            for route in routes:
                go(role,route)
                assert page.locator('h1').count()>0,(role,route)
                assert '舒适洁牙权益' not in page.locator('main').inner_text(),(role,route)
                assert '种植牙抵用权益' not in page.locator('main').inner_text(),(role,route)
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),(role,route)
            print(f'{role}: {len(routes)} routes and mobile layout passed',flush=True)

        go('customer','benefit/B1')
        assert '舒适洁牙服务' in page.locator('main').inner_text()
        button('确认领取').click();confirm()
        b=next(b for b in data('customer')['benefits'] if b['id']=='B1')
        assert b['total']==2 and b['state']=='已领取' and b['expiry']=='2027-03-06'
        page.reload()
        assert button('确认领取').count()==0
        go('customer','activate')
        page.get_by_placeholder('CARD-001').fill('CARD-VOID')
        button('读取演示卡片').click()
        page.get_by_role('alert').wait_for()
        page.get_by_placeholder('CARD-001').fill('CARD-001')
        button('读取演示卡片').click()
        button('确认激活到我的账号').click();confirm()
        assert sum(b['id']=='CARD-B1' for b in data('customer')['benefits'])==1
        go('customer','activate')
        page.get_by_placeholder('CARD-001').fill('CARD-001')
        button('读取演示卡片').click()
        page.get_by_text('该卡已激活，不能再次激活。',exact=True).wait_for()

        go('customer','clinics/B2')
        assert '青禾口腔' not in page.locator('main').inner_text()
        button('不授权，手动选地区').click()
        assert '已拒绝定位' in page.locator('main').inner_text()
        go('customer','booking/B2/M1')
        page.locator('input[type=date]').fill('2028-01-01')
        button('提交意向预约').click()
        page.get_by_role('alert').wait_for()
        page.locator('input[type=date]').fill('2026-09-08')
        button('提交意向预约').click()
        d=data('customer');a=d['appointments'][0]
        assert a['status']=='待确认' and next(b for b in d['benefits'] if b['id']=='B2')['held']==1
        go('customer','booking/B2/M1')
        assert button('提交意向预约').count()==0
        go('customer','reschedule/A1')
        page.locator('input[type=date]').fill('2026-09-11')
        button('提交改期申请').click()
        a=next(a for a in data('customer')['appointments'] if a['id']=='A1')
        assert a['date']=='2026-09-09' and a['change']['date']=='2026-09-11'
        go('customer','reschedule/A1')
        assert button('提交改期申请').count()==0
        go('customer','feedback/A1')
        assert '尚未到预约时间' in page.locator('main').inner_text()
        d=data('customer');a=next(a for a in d['appointments'] if a['id']=='A1')
        assert a['status']=='成功' and next(b for b in d['benefits'] if b['id']=='B3')['held']==1
        go('customer','appointment/A2')
        button('取消预约').click();confirm()
        assert next(b for b in data('customer')['benefits'] if b['id']=='B6')['held']==0
        go('customer','edit-profile')
        assert page.locator('input[disabled]').input_value()=='13800000011'
        go('customer','credential/B2')
        page.screenshot(path=str(ROOT/'customer-mini'/'credential.png'))
        print('customer claim / activation / eligibility / booking / change request / cancellation passed',flush=True)

        go('clinic','confirm/V2')
        before=data('clinic')
        button('确认预约时间').click()
        assert next(a for a in data('clinic')['appointments'] if a['id']=='V2')['status']=='成功'
        assert data('clinic')['redemptions']==before['redemptions']
        go('clinic','feedback/V4')
        button('记录双方反馈冲突').click();confirm()
        a=next(a for a in data('clinic')['appointments'] if a['id']=='V4')
        assert a['status']=='成功' and a['held']==1 and a['feedback']=='双方反馈冲突'
        go('clinic','reschedule/V1')
        button('确认改期').click()
        page.get_by_role('alert').wait_for()
        page.locator('.arco-checkbox').click()
        button('确认改期').click()
        go('clinic','change-request/V3')
        button('同意本次改期').click()
        a=next(a for a in data('clinic')['appointments'] if a['id']=='V3')
        assert a['date']=='2026-09-10' and 'change' not in a

        go('clinic','scan')
        for code in ['VISIT-EXPIRED','VISIT-OTHER','VISIT-FROZEN']:
            page.get_by_placeholder('VISIT-001').fill(code)
            button('读取演示凭证').click()
            page.get_by_role('alert').wait_for()
            assert button('确认核销').count()==0
        page.get_by_placeholder('VISIT-001').fill('VISIT-001')
        button('读取演示凭证').click()
        button('确认核销').click()
        page.get_by_text('请先确认客户已完成约定服务',exact=True).wait_for()
        page.locator('.arco-checkbox').click()
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=str(ROOT/'clinic-mini'/'scan.png'))
        button('确认核销').click();confirm()
        d=data('clinic');r=d['redemptions'][0]
        a=next(a for a in d['appointments'] if a['id']=='V1')
        assert a['status']=='完成' and a['held']==0 and a['used']==1 and r['amount']==60
        go('clinic','scan')
        page.get_by_placeholder('VISIT-001').fill('VISIT-001')
        button('读取演示凭证').click()
        page.get_by_text('本次预约已经核销，不能重复扣减',exact=True).wait_for()
        go('clinic','revoke/'+r['id'])
        button('提交撤销').click()
        page.get_by_text('请填写撤销原因',exact=True).wait_for()
        page.get_by_placeholder('请输入错误核销的原因').fill('演示误操作')
        button('提交撤销').click();confirm()
        d=data('clinic');a=next(a for a in d['appointments'] if a['id']=='V1')
        assert a['status']=='成功' and a['held']==1 and a['used']==0
        assert d['redemptions'][0]['status']=='已撤销' and len(d['reversals'])==1
        go('clinic','revoke/'+r['id'])
        page.get_by_placeholder('请输入错误核销的原因').fill('重复撤销')
        button('提交撤销').click()
        page.get_by_text('该核销已经撤销，不能重复恢复权益',exact=True).wait_for()
        go('clinic','revoke/R2')
        page.get_by_placeholder('请输入错误核销的原因').fill('已结清误核销')
        button('提交撤销').click()
        assert '账单已完成结算，不能撤销' in page.locator('main').inner_text()
        assert next(r for r in data('clinic')['redemptions'] if r['id']=='R2')['status']=='已核销'
        go('clinic','bills')
        page.locator('.arco-select').click()
        page.locator('.arco-select-option').filter(has_text='逾期待处理').click()
        go('clinic','home')
        assert '账单已逾期' in page.locator('main').inner_text()
        assert '门诊临时下线' not in page.locator('main').inner_text()
        go('clinic','appointment/V1')
        assert button('前往扫码核销').count()==1
        print('clinic confirmation / agreed change / verification / idempotency / reversal accounting passed',flush=True)

        # 登出后未开通和停用手机号不得进入员工工作区。
        go('clinic','profile');button('退出登录').click()
        page.locator('.arco-checkbox').click()
        for identity in ['手机号未开通','员工账号已停用']:
            page.locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=identity).click()
            button('员工手机号授权登录（演示）').click()
            page.get_by_role('alert').wait_for()
            assert not data('clinic')['logged']
        assert data('customer')['logged']
        for width in [375,430]:
            page.set_viewport_size({'width':width,'height':844})
            go('customer','benefits')
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert not errors,errors
        print('login boundary / separate sessions / 375 and 430px passed; browser errors: 0',flush=True)
        browser.close()


if __name__=='__main__':
    verify()
