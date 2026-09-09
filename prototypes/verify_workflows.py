"""0.18原型：只读合页、门诊上下文、附件/续签审核和账单两条模拟收款路径。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE='http://127.0.0.1:8765'
ROOT=Path(__file__).resolve().parent

def verify():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},locale='zh-CN')
        page.set_default_timeout(8000)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def go(role,route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('.workspace h1')
        def button(name,root=None):
            return (root if root is not None else page).get_by_role('button',name=name,exact=True)
        def data(role):
            return page.evaluate(f"JSON.parse(localStorage.getItem('chihuitong-prototype-v1-{role}'))")
        def confirm():
            page.locator('.arco-modal').last.get_by_role('button',name='确定',exact=True).click()
            page.wait_for_selector('.arco-modal-simple',state='hidden')
        def tab(name):
            page.get_by_role('tab',name=name,exact=True).click()
        def screenshot(role,name):
            page.screenshot(path=str(ROOT/role/name))

        for role in ['platform','resource','channel','clinic']:
            go(role,'workbench')
            assert '额度' not in page.locator('body').inner_text()
            routes=page.evaluate('window.PROTOTYPE.pages.filter(p=>!p.hidden&&p.custom).map(p=>({id:p.id,title:p.title}))')
            for route in routes:
                go(role,route['id'])
                assert page.locator('h1').inner_text()==route['title']
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert '额度' not in page.locator('body').inner_text()
            print(role+': custom pages / no credit / layout passed',flush=True)

        for role,title in [('resource','合作合同与推广产品'),('channel','平台合作与推广产品')]:
            go(role,'contracts')
            assert page.locator('h1').inner_text()==title
            assert page.locator('.sidebar').get_by_text('合同授权产品',exact=True).count()==0
            for name in ['新增合同','登记合同','添加合同权益','编辑分配','启用授权','停用授权','发起续签']:
                assert button(name).count()==0
            page.get_by_text('合同授权推广产品',exact=True).wait_for()
            screenshot(role,'contract-overview.png')
        print('partner contract + schemes read-only pages passed',flush=True)

        go('channel','clinics')
        page.get_by_placeholder('搜索编号、名称或关键字').fill('明禾')
        button('详情').click()
        tab('推广产品')
        drawer=page.locator('.arco-drawer').last
        assert drawer.get_by_text('舒适洁牙权益',exact=True).count()==1
        assert drawer.get_by_text('儿童涂氟权益',exact=True).count()==1
        assert drawer.get_by_text('口腔检查权益',exact=True).count()==1
        item=drawer.locator('tr').filter(has_text='儿童涂氟权益')
        button('上线',item).click()
        button('下线',item).wait_for()
        button('下线',item).click()
        button('上线',item).wait_for()
        screenshot('channel','clinic-schemes.png')
        tab('合同与续签')
        button('发起续签').click()
        form=page.locator('.arco-drawer').last
        button('提交平台审核',form).click()
        form.get_by_text('请填写合同编号、有效日期、联系人和11位手机号，并上传可读取的签署附件。',exact=True).wait_for()
        button('使用演示附件',form).click()
        button('提交平台审核',form).click()
        page.wait_for_function("document.querySelectorAll('.arco-drawer').length===1")
        d=data('channel');clinic=next(r for r in next(p for p in d if p['id']=='clinics')['rows'] if '明禾' in r['name'])
        assert len(clinic['contractVersions'])==2
        assert clinic['contractVersions'][0]['status']=='已生效'
        assert clinic['contractVersions'][1]['status']=='待审核'
        assert clinic['contractVersions'][1]['start']=='2026-10-01'
        button('发起续签').click()
        page.get_by_text('已有待审核或待生效版本，请先处理现有版本。',exact=True).wait_for()
        page.locator('.arco-drawer-close-icon').last.click()
        assert page.get_by_placeholder('搜索编号、名称或关键字').input_value()=='明禾'
        page.reload()
        assert len(next(p for p in data('channel') if p['id']=='clinics')['rows'][0]['contractVersions'])>=1
        print('clinic context / all schemes / toggles / renewal / repeat guard passed',flush=True)

        button('录入签约门诊').click()
        button('保存门诊资料').click()
        page.get_by_text('请填写11位前台预约手机号。',exact=True).wait_for()
        for label,value in [('门诊名称','首签测试门诊（演示）'),('经营主体','测试经营主体（演示）'),('持证经营地址','演示路1号'),('门诊联系人','测试联系人'),('前台预约手机号','13800000001'),('负责业务员','演示业务员')]:
            page.get_by_label(label,exact=True).fill(value)
        button('补齐演示资质与照片').click()
        button('保存门诊资料').click()
        button('提交资料审核').click()
        tab('合同与续签');button('签订三方合同').click()
        page.get_by_label('合同编号',exact=True).fill('TEST-FIRST-001')
        button('使用演示附件').click();button('提交平台审核').click()
        c=next(r for r in next(p for p in data('channel') if p['id']=='clinics')['rows'] if r['name']=='首签测试门诊（演示）')
        assert c['qualification']=='待审核' and len(c['files'])==3
        assert c['contractVersions'][0]['status']=='待审核'
        tab('推广产品')
        button('上线').first.click()
        page.get_by_text('授权、门诊资质、有效三方合同或服务状态不满足，不能上线。',exact=True).wait_for()
        print('clinic creation / required fields / materials / first signing / pending blocks launch passed',flush=True)

        go('platform','clinics')
        page.get_by_placeholder('搜索编号、名称或关键字').fill('映禾')
        button('详情').click()
        tab('资料与资质')
        page.get_by_label('审核意见',exact=True).fill('演示资质照片清晰完整')
        button('资质审核通过').click()
        tab('合同与续签')
        button('通过合同审核').wait_for()
        assert page.locator('.arco-drawer .file-card').count()>=4
        image=page.locator('.arco-drawer .arco-image').first
        image.click()
        page.wait_for_selector('.arco-image-preview')
        page.keyboard.press('Escape')
        page.wait_for_selector('.arco-image-preview',state='hidden')
        assert button('通过合同审核').count(), page.locator('body').inner_text()
        page.get_by_label('合同审核意见',exact=True).fill('已核对全部签署及资质材料')
        screenshot('platform','tripartite-review.png')
        button('通过合同审核').click();confirm()
        assert button('通过合同审核').count()==0
        tab('资料与资质')
        page.locator('.arco-drawer-close-icon').last.click()
        clinic_row=page.locator('tr').filter(has_text='映禾口腔（演示）')
        clinic_row.get_by_role('button',name='下线',exact=True).click()
        page.get_by_label('上下线原因',exact=True).fill('演示临时暂停')
        page.get_by_role('button',name='确认下线',exact=True).click()
        clinic_row.get_by_role('button',name='上线',exact=True).click()
        page.get_by_label('上下线原因',exact=True).fill('已恢复接诊条件')
        page.get_by_role('button',name='确认上线',exact=True).click()
        print('platform complete material preview / qualification / contract review passed',flush=True)

        go('clinic','bills')
        button('详情').first.click()
        button('上传付款凭证').click()
        page.locator('.arco-modal input[type=file]').set_input_files({'name':'broken.png','mimeType':'image/png','buffer':b'not an image'})
        page.get_by_text('文件内容无法读取，请选择有效图片或PDF。',exact=True).wait_for()
        button('提交审核').click()
        page.get_by_text('请填写不超过剩余应付的付款金额、日期、付款方和可读取凭证。',exact=True).wait_for()
        button('使用演示附件').click()
        button('提交审核').click()
        page.wait_for_selector('.arco-modal',state='detached')
        b=next(p for p in data('clinic') if p['id']=='bills')['rows'][0]
        assert b['status']=='付款待确认' and b['confirmed']==0 and len(b['receipts'])==1
        button('微信扫码支付').click()
        page.get_by_text('线下凭证尚待审核，不能同时发起在线支付。',exact=True).wait_for()
        # Independent fixture: emulate platform returning this clinic's offline voucher, not cross-role syncing.
        page.evaluate("""() => {const key='chihuitong-prototype-v1-clinic';const d=JSON.parse(localStorage.getItem(key));const b=d.find(p=>p.id==='bills').rows[0];b.receipts[0].status='已退回';b.receipts[0].reason='演示退回';localStorage.setItem(key,JSON.stringify(d));}""")
        page.reload();button('详情').first.click()
        button('微信扫码支付').click()
        page.get_by_label('不可支付的二维码示意').wait_for()
        button('模拟查询：结果未知').click()
        b=next(p for p in data('clinic') if p['id']=='bills')['rows'][0]
        assert b['confirmed']==0 and b['attempts'][0]['status']=='结果待核实'
        button('模拟确认关闭/过期').click()
        button('重新生成演示二维码').click()
        screenshot('clinic','wechat-payment.png')
        button('模拟查询：支付成功').click()
        b=next(p for p in data('clinic') if p['id']=='bills')['rows'][0]
        assert b['confirmed']==b['amount'] and b['status']=='已结清'
        assert len([r for r in b['receipts'] if r['status']=='已通过'])==1
        assert button('模拟查询：支付成功').count()==0
        page.locator('.arco-modal-close-icon').click()
        assert button('微信扫码支付').count()==0
        screenshot('clinic','bill-receipts.png')
        print('offline upload / no false settlement / cross-channel block / unknown-close-retry-success passed',flush=True)

        go('platform','bills');button('详情').first.click()
        button('查看凭证').first.click()
        button('确认实际到账').click()
        page.get_by_text('请填写收款审核意见。',exact=True).wait_for()
        page.get_by_label('收款审核意见').fill('凭证交易信息待补充')
        button('退回凭证').click();confirm()
        assert button('确认实际到账').count()==0
        b=next(p for p in data('platform') if p['id']=='bills')['rows'][0]
        assert b['confirmed']==0 and b['receipts'][0]['status']=='已退回'
        print('platform receipt rejection and audit passed',flush=True)

        # Fixture simulates two independently submitted vouchers, not real transfers.
        for part in [0.4,0.6]:
            page.evaluate('''part => {const key='chihuitong-prototype-v1-platform';const d=JSON.parse(localStorage.getItem(key));const b=d.find(p=>p.id==='bills').rows[0];const r={...b.receipts[0],id:'PART-'+part,amount:Math.round(b.amount*part*100)/100,status:'待审核',reason:''};b.receipts.unshift(r);localStorage.setItem(key,JSON.stringify(d));}''',part)
            page.reload();button('详情').first.click();button('查看凭证').first.click()
            page.get_by_label('收款审核意见').fill('已核实本笔演示到账')
            button('确认实际到账').click();confirm()
            b=next(p for p in data('platform') if p['id']=='bills')['rows'][0]
            assert (b['status']=='已结清')==(part==0.6)
            assert button('确认实际到账').count()==0
        assert b['confirmed']==b['amount']
        print('partial receipt remains open / full receipt closes once passed',flush=True)

        go('clinic','bills')
        page.evaluate('''() => {const key='chihuitong-prototype-v1-clinic';const d=JSON.parse(localStorage.getItem(key));const b=d.find(p=>p.id==='bills').rows[0];b.confirmed=0;b.receipts=[];b.attempts=[{id:'MISMATCH',amount:b.amount,revision:b.revision-1,status:'待支付'}];localStorage.setItem(key,JSON.stringify(d));}''')
        page.reload();button('详情').first.click();button('微信扫码支付').click()
        button('模拟查询：支付成功').click()
        b=next(p for p in data('clinic') if p['id']=='bills')['rows'][0]
        assert b['confirmed']==0 and b['attempts'][0]['status']=='结果待核实'
        assert any(r['status']=='待处理' for r in b['history'])
        print('bill revision mismatch cannot settle passed',flush=True)

        go('channel','bills');button('详情').first.click()
        for name in ['上传付款凭证','微信扫码支付','确认实际到账']:
            assert button(name).count()==0
        button('记录催收').click()
        page.get_by_label('催收内容').fill('已电话提醒门诊处理本期账单（演示）')
        button('保存记录').click()
        assert any('电话提醒' in r['name'] for r in next(p for p in data('channel') if p['id']=='bills')['rows'][0]['history'])
        page.set_viewport_size({'width':768,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        go('resource','contracts')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print('read-only collection / 768px / browser errors: 0',flush=True)
        browser.close()

if __name__=='__main__':
    verify()
