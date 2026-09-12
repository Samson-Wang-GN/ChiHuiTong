"""Real browser operations across the four isolated synthetic institution sessions."""

import re


def dialog(page):
    modals = page.locator('.arco-modal:visible')
    return modals.last if modals.count() else page.locator('.arco-drawer-wrapper').last


def field(page, label):
    return dialog(page).locator('.arco-form-item').filter(
        has=page.locator('.arco-form-label-item', has_text=label)
    ).first


def fill(page, label, value):
    field(page, label).locator('input,textarea').first.fill(str(value))


def select(page, label, option=None):
    field(page, label).locator('.arco-select').click()
    options = page.locator('.arco-select-popup:visible .arco-select-option')
    if option is None:
        options.first.click()
    else:
        options.filter(has_text=re.compile('^'+re.escape(option)+'$')).click()


def menu(page, title):
    page.locator('.sidebar .arco-menu-item').filter(has_text=re.compile('^'+re.escape(title)+'$')).click()


def close(page):
    while page.get_by_role('button', name='关闭详情', exact=True).count():
        page.get_by_role('button', name='关闭详情', exact=True).last.click()
        page.wait_for_timeout(250)


def read(page, path):
    return page.evaluate('path => window.CHT.api(path)', path)


def upload(page, report):
    with page.expect_response(lambda response: response.url.endswith('/api/v1/files') and response.request.method == 'POST') as response:
        dialog(page).locator('input[type=file]').set_input_files(report/'synthetic-proof.png')
    assert response.value.status == 201
    dialog(page).get_by_role('button', name='查看附件 1', exact=True).wait_for()


def date_field(page, label, value):
    page.wait_for_timeout(400)
    element = field(page, label).locator('input').first
    element.click()
    element.fill(value)
    element.press('Enter')
    element.press('Tab')


def exercise(pages, report, worker):
    resource, platform, clinic = pages['resource'], pages['platform'], pages['clinic']
    completed = []
    try:
        # Resource creates a physical procurement order entirely through the wizard.
        menu(resource, '推广产品销售')
        resource.get_by_role('button', name='创建销售订单', exact=True).click()
        resource.get_by_role('button', name='下一步', exact=True).click()
        fill(resource, '开卡张数', 3)
        resource.get_by_role('button', name='下一步', exact=True).click()
        select(resource, '推广产品')
        select(resource, '对客户展示的权益来源')
        resource.get_by_role('button', name='提交开卡订单', exact=True).click()
        resource.get_by_text('本批卡号段', exact=True).wait_for(state='hidden')
        resource.get_by_role('tab', name='订单资料', exact=True).wait_for()
        orders = read(resource, '/api/v1/sales-orders')['results']
        created = orders[0]
        assert created['quantity'] == 3 and created['mode'] == 'physical'
        assert created['status'] == 'pending_approval'
        close(resource)
        completed.append('resource physical sales wizard')

        # Platform reviews the newly submitted order and sees the persistent number range.
        menu(platform, '推广产品销售')
        platform.get_by_role('button', name='刷新', exact=True).click()
        platform.get_by_role('button', name='订单详情', exact=True).first.click()
        platform.get_by_role('button', name='审核开卡', exact=True).click()
        fill(platform, '操作原因', '合成端到端回归审核，未发生实际采购')
        dialog(platform).get_by_role('button', name='保存', exact=True).click()
        platform.get_by_text('本批卡号段', exact=True).wait_for()
        issued = read(platform, '/api/v1/sales-orders/'+created['id'])
        assert issued['status'] == 'issued'
        assert int(issued['number_range']['last'])-int(issued['number_range']['first']) == 2
        close(platform)
        completed.append('platform approval and unique card range')

        # Named single-customer order with optional profile fields.
        resource.get_by_role('button', name='创建销售订单', exact=True).click()
        select(resource, '销售方式', '记名非实体卡 · 单卡销售')
        resource.get_by_role('button', name='下一步', exact=True).click()
        fill(resource, '客户姓名', '合成单客回归')
        fill(resource, '客户手机号', '13800000888')
        fill(resource, '开卡张数', 2)
        fill(resource, '资源方客户编号', 'SOURCE-NOT-PLATFORM-ID')
        fill(resource, '年龄', 30)
        fill(resource, '职业', '合成回归')
        resource.get_by_role('button', name='下一步', exact=True).click()
        select(resource, '推广产品')
        select(resource, '对客户展示的权益来源')
        resource.get_by_role('button', name='提交开卡订单', exact=True).click()
        resource.get_by_role('tab', name='客户名单', exact=True).click()
        resource.get_by_text('合成单客回归', exact=True).wait_for()
        close(resource)
        completed.append('named single sales with source customer number')

        # Excel is uploaded/parsed by the real server; deliberately ambiguous phone columns.
        resource.get_by_role('button', name='创建销售订单', exact=True).click()
        select(resource, '销售方式', '记名非实体卡 · 批量Excel')
        resource.get_by_role('button', name='下一步', exact=True).click()
        with resource.expect_response(lambda response: response.url.endswith('/api/v1/files') and response.request.method=='POST') as uploaded:
            dialog(resource).locator('input[type=file]').set_input_files(report/'synthetic-customers.xlsx')
        assert uploaded.value.status == 201
        resource.get_by_role('button', name='读取 Excel', exact=True).click()
        resource.get_by_text('等待读取', exact=True).wait_for()
        worker()
        resource.get_by_text('待确认列', exact=True).wait_for(timeout=15000)
        resource.get_by_role('button', name='识别列对应关系', exact=True).click()
        resource.get_by_text('以下字段存在多个候选列', exact=False).wait_for()
        phone_row = dialog(resource).locator('.arco-table-tr').filter(has_text='客户手机号（必填）')
        phone_row.locator('.arco-select').click()
        resource.locator('.arco-select-popup:visible .arco-select-option').filter(has_text=re.compile('^B · 手机号$')).click()
        resource.get_by_role('button', name='确认列对应并校验', exact=True).click()
        resource.get_by_text('正在校验', exact=True).wait_for()
        worker()
        resource.get_by_role('button', name='确认本次导入', exact=True).wait_for(timeout=15000)
        resource.get_by_role('button', name='确认本次导入', exact=True).click()
        resource.get_by_role('button', name='已确认导入', exact=True).wait_for()
        resource.get_by_role('button', name='下一步', exact=True).click()
        select(resource, '推广产品')
        select(resource, '对客户展示的权益来源')
        resource.get_by_role('button', name='提交开卡订单', exact=True).click()
        resource.get_by_role('tab', name='Excel导入依据', exact=True).wait_for()
        newest = read(resource, '/api/v1/sales-orders')['results'][0]
        assert newest['quantity'] == 5 and newest['entry'] == 'excel'
        close(resource)
        completed.append('Excel upload ambiguous column mapping validation and five-card order')

        # Clinic confirmation: read only identifies a seeded pending record, operation uses UI.
        pending = read(clinic, '/api/v1/appointments?status=pending')['results'][0]
        menu(clinic, '预约管理')
        clinic.locator('.arco-table-tr').filter(has_text=pending['customer_name']).get_by_role('button', name='详情', exact=True).click()
        clinic.get_by_role('button', name='确认预约', exact=True).click()
        dialog(clinic).get_by_role('button', name='确认预约', exact=True).click()
        clinic.wait_for_timeout(400)
        confirmed = read(clinic, '/api/v1/appointments/'+pending['id'])
        assert confirmed['status'] == 'success'
        close(clinic)
        completed.append('clinic appointment confirmation persisted')

        # Synthetic payment goes through payment service/ledger, with an explicit confirmation.
        menu(clinic, '门诊账单')
        clinic.get_by_role('button', name='详情', exact=True).first.click()
        clinic.get_by_role('button', name='微信扫码支付', exact=True).click()
        clinic.get_by_role('button', name='模拟微信支付成功', exact=True).click()
        dialog(clinic).get_by_role('button', name='保存', exact=True).click()
        clinic.wait_for_timeout(400)
        bills = read(clinic, '/api/v1/clinic-bills')['results']
        assert all(bill['status']=='settled' for bill in bills)
        close(clinic)
        completed.append('explicit simulated payment settles only current synthetic bill')

        # Each partner confirms its own monthly bill, platform records offline proof, partner receives.
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        for role in ['resource', 'channel']:
            partner = pages[role]
            menu(partner, '合作方结算单')
            partner.get_by_role('button', name='详情', exact=True).first.click()
            partner.get_by_role('button', name='确认对账', exact=True).click()
            dialog(partner).get_by_role('button', name='保存', exact=True).click()
            partner.wait_for_timeout(300)
            bill = read(partner, '/api/v1/partner-bills')['results'][0]
            assert bill['status'] == 'pending_payment'
            close(partner)
            menu(platform, '合作方结算单')
            platform.get_by_role('button', name='刷新', exact=True).click()
            platform.locator('.arco-table-tr').filter(has_text=bill['organization_name']).get_by_role('button', name='详情', exact=True).click()
            platform.get_by_role('button', name='登记付款并上传凭证', exact=True).click()
            date_field(platform, '付款时间', today+' 08:00')
            fill(platform, '付款流水号', 'SYNTHETIC-'+role)
            upload(platform, report)
            dialog(platform).get_by_role('button', name='登记已付款', exact=True).click()
            platform.wait_for_timeout(300)
            paid = read(platform, '/api/v1/partner-bills/'+bill['id'])
            assert paid['status'] == 'pending_receipt'
            assert len(paid['payment']['attachment_ids']) == 1
            close(platform)
            partner.get_by_role('button', name='刷新', exact=True).click()
            partner.get_by_role('button', name='详情', exact=True).first.click()
            partner.get_by_role('button', name='确认收款', exact=True).click()
            date_field(partner, '实际收款日期', today)
            dialog(partner).get_by_role('button', name='确认收款', exact=True).click()
            partner.wait_for_timeout(300)
            assert read(partner, '/api/v1/partner-bills/'+bill['id'])['status'] == 'completed'
            close(partner)
            completed.append(role+' monthly statement confirm platform proof and receipt')

        # Channel edits an approved clinic, platform rejects without overwriting published data.
        channel = pages['channel']
        original = read(channel, '/api/v1/clinics')['results'][0]
        menu(channel, '门诊管理')
        channel.get_by_role('button', name='详情', exact=True).first.click()
        channel.get_by_role('button', name='维护门诊资料', exact=True).click()
        fill(channel, '业务联系人', '合成变更待审核')
        channel.get_by_role('button', name='提交变更审核', exact=True).click()
        channel.wait_for_timeout(400)
        unchanged = read(channel, '/api/v1/clinics/'+original['id'])
        assert unchanged['profile']['business_contact'] == original['profile']['business_contact']
        close(channel)
        menu(platform, '门诊管理')
        platform.get_by_role('button', name='刷新', exact=True).click()
        platform.get_by_role('button', name='详情', exact=True).first.click()
        platform.get_by_role('tab', name='资料变更审核', exact=True).click()
        platform.get_by_role('button', name='对照详情', exact=True).first.click()
        platform.get_by_text('合成变更待审核', exact=True).first.wait_for()
        platform.get_by_role('button', name='审核资料', exact=True).click()
        select(platform, '审核结果', '退回修改')
        fill(platform, '操作原因', '合成回归：退回后必须保留此前生效资料')
        dialog(platform).get_by_role('button', name='保存', exact=True).click()
        platform.wait_for_timeout(400)
        assert read(platform, '/api/v1/clinics/'+original['id'])['profile']['business_contact'] == original['profile']['business_contact']
        changes = read(platform, '/api/v1/clinics/'+original['id']+'/profile-changes')['results']
        assert changes[0]['status'] == 'rejected'
        close(platform)
        completed.append('channel clinic amendment and platform rejection preserve published profile')

        # Geometry math is checked against center invariance and invertible pixel translation.
        point = platform.evaluate('() => CHT.mapPoint({latitude:39.9,longitude:116.3},17,0,0)')
        assert point == {'latitude':'39.900000', 'longitude':'116.300000'}
        restored = platform.evaluate('() => CHT.mapPoint(CHT.mapPoint({latitude:39.9,longitude:116.3},17,100,-100),17,-100,100)')
        assert abs(float(restored['latitude'])-39.9) < 0.000002
        assert abs(float(restored['longitude'])-116.3) < 0.000002
        for role, page in pages.items():
            page.screenshot(path=str(report/f'{role}-workflow.png'), full_page=True, animations='disabled')
    except Exception:
        for role, page in pages.items():
            # All sessions are authenticated; login challenges have already been cleared.
            page.screenshot(path=str(report/f'{role}-failure.png'), full_page=True, animations='disabled')
            (report/f'{role}-failure.html').write_text(page.locator('body').inner_html())
        raise
    finally:
        import json
        (report/'workflows.json').write_text(json.dumps(completed, ensure_ascii=False, indent=2))
