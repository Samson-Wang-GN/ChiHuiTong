"""REQ-046 focused UI checks using only synthetic files in the isolated Web database."""

import json
import re

from web_workflows import close, dialog, menu, read, select


def exercise(page, worker, report):
    results = []

    def begin():
        menu(page, '推广产品销售')
        page.get_by_role('button', name='创建销售订单', exact=True).click()
        select(page, '销售方式', '记名非实体卡 · 批量Excel')
        page.get_by_role('button', name='下一步', exact=True).click()

    def load(filename):
        with page.expect_response(lambda response: response.url.endswith('/api/v1/imports') and response.request.method=='POST') as created:
            dialog(page).locator('input[type=file]').set_input_files(report/filename)
        assert created.value.status == 201
        assert created.value.json()['status'] == 'mapping'
        page.get_by_text('原文件预览 · 前10条数据', exact=True).wait_for(timeout=15000)

    def next_validated():
        with page.expect_response(lambda response: '/imports/' in response.url and response.url.endswith('/mapping')) as configured:
            page.get_by_role('button', name='下一步', exact=True).click()
        assert configured.value.status == 200
        assert configured.value.json()['status'] == 'validated'
        page.get_by_role('button', name='提交开卡订单', exact=True).wait_for(timeout=15000)

    def finish(expected):
        select(page, '推广产品')
        select(page, '对客户展示的权益来源')
        page.get_by_role('button', name='提交开卡订单', exact=True).click()
        page.get_by_role('tab', name='Excel导入依据', exact=True).wait_for()
        order = read(page, '/api/v1/sales-orders')['results'][0]
        assert order['quantity'] == expected
        close(page)

    def choose(label, column):
        page.get_by_label(label+'对应列', exact=True).click()
        page.locator('.arco-select-popup:visible .arco-select-option').filter(has_text=re.compile('^'+re.escape(column)+'$')).click()

    try:
        begin()
        load('synthetic-no-dimension.xlsx')
        page.get_by_text('必填项已匹配，核对无误后点击底部“下一步”。', exact=True).wait_for()
        assert page.locator('.import-preview tbody .arco-table-tr').count() == 2
        assert page.get_by_label('工作表', exact=True).count() == 0
        page.screenshot(path=str(report/'excel-template-auto.png'), full_page=True)
        next_validated()
        finish(5)
        results.append('template without dimensions auto sheet/header/columns then one next; 2 customers5 cards')
        begin()
        load('synthetic-auto.xlsx')
        rows = page.locator('.import-preview tbody .arco-table-tr')
        assert rows.count() == 10
        assert '21' in rows.first.inner_text() and '30' in rows.last.inner_text()
        page.get_by_text('必填项已匹配，核对无误后点击底部“下一步”。', exact=True).wait_for()
        assert '手机号码' in page.get_by_label('客户手机号对应列', exact=True).inner_text()
        page.screenshot(path=str(report/'excel-auto-ten-rows.png'), full_page=True)
        page.get_by_text('工作表与表头设置（识别不准确时调整）', exact=True).click()
        page.get_by_label('表头行', exact=True).fill('2')
        page.get_by_label('表头行', exact=True).fill('20')
        page.get_by_text('必填项已匹配，核对无误后点击底部“下一步”。', exact=True).wait_for()
        assert page.locator('.import-preview tbody .arco-table-tr').count() == 10
        next_validated()
        page.get_by_role('button', name='上一步', exact=True).click()
        page.get_by_text('原文件预览 · 前10条数据', exact=True).wait_for()
        page.get_by_text('不读取数量列，每位客户使用统一数量', exact=True).click()
        page.get_by_label('每位客户开卡数量', exact=True).fill('2')
        next_validated()
        finish(24)
        results.append('automatic sheet/header20/ten rows/one-next; return-edit revalidated to24')

        begin()
        load('synthetic-missing.xlsx')
        page.get_by_role('button', name='下一步', exact=True).click()
        page.get_by_text('请先补全列对应关系：客户手机号、开卡张数', exact=True).first.wait_for()
        choose('客户手机号', 'A · 客户姓名')
        page.get_by_text('此列已对应其他字段，请重新选择', exact=True).first.wait_for()
        choose('客户手机号', 'B · 联络号码')
        page.get_by_text('不读取数量列，每位客户使用统一数量', exact=True).click()
        page.get_by_role('button', name='下一步', exact=True).click()
        assert page.get_by_role('button', name='提交开卡订单', exact=True).count() == 0
        page.get_by_label('每位客户开卡数量', exact=True).fill('3')
        page.screenshot(path=str(report/'excel-manual-mapping.png'), full_page=True)
        next_validated()
        finish(3)
        results.append('missing required mapping/duplicate source column blocked; explicit uniform3')

        begin()
        load('synthetic-invalid.xlsx')
        with page.expect_response(lambda response: response.url.endswith('/mapping')):
            page.get_by_role('button', name='下一步', exact=True).click()
        page.get_by_role('button', name='下载错误 Excel', exact=True).wait_for(timeout=15000)
        assert page.get_by_role('button', name='提交开卡订单', exact=True).count() == 0
        page.locator('.arco-upload-list-remove-icon').click()
        assert page.locator('.import-preview').count() == 0
        page.get_by_role('button', name='下一步', exact=True).click()
        page.get_by_text('请先上传文件，等待自动读取和匹配完成', exact=True).first.wait_for()
        load('synthetic-missing.xlsx')
        choose('客户手机号', 'B · 联络号码')
        page.get_by_text('不读取数量列，每位客户使用统一数量', exact=True).click()
        page.get_by_label('每位客户开卡数量', exact=True).fill('4')
        next_validated()
        finish(4)
        results.append('full-file validation errors block advance; remove/replace invalidates old batch')
        page.set_viewport_size({'width':768, 'height':1000})
        begin()
        load('synthetic-auto.xlsx')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(report/'excel-auto-narrow.png'), full_page=True)
        page.set_viewport_size({'width':1440, 'height':1000})
        next_validated()
        finish(12)
        results.append('768px preview and original-column horizontal scroll remain within drawer')
    except Exception:
        page.screenshot(path=str(report/'excel-focused-failure.png'), full_page=True)
        raise
    finally:
        (report/'excel-focused.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
