"""REQ-041 prototype checks. Run only via the approved server runner; synthetic data only."""
import io
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765'


def verify():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(10000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def btn(text):
            return page.get_by_role('button', name=text, exact=True)

        def select(label, text):
            page.locator('.flow-field').filter(has=page.get_by_text(label, exact=True)).locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=text).last.click()

        def start():
            page.goto(BASE + '/resource/#sales')
            page.reload()
            btn('新建销售订单').click()
            select('销售方式', '记名非实体卡')
            btn('下一步').click()

        def sample(label):
            btn(label).click()
            page.get_by_text(label + '.xlsx', exact=True).wait_for()

        def top():
            page.locator('.arco-drawer-body').evaluate('(e)=>e.scrollTop=0')

        def upload(data, filename='虚构导入.xlsx'):
            page.locator('input[type=file]').set_input_files({'name': filename, 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': data})

        start()
        sample('使用机构格式示例')
        assert page.get_by_text('九月福利名单', exact=True).count()
        assert page.locator('.import-mappings').inner_text().find('C · 客户名称') >= 0
        assert page.locator('.import-editor tr').filter(has_text='客户甲（演示）').inner_text().startswith('4')
        initial_customers = page.evaluate("PROTOTYPE.pages.find(p=>p.id==='salesCustomers').rows.length")
        btn('下一步').click()
        page.get_by_text('请先确认列对应关系。', exact=True).wait_for()
        page.get_by_text('保存为本机构导入格式', exact=True).click()
        btn('确认列对应关系').click()
        assert btn('列对应关系已确认').is_disabled()
        # Any mapping change invalidates previous confirmation, even before returning to step three.
        select('客户姓名 *', 'B · 购卡数量')
        assert btn('确认列对应关系').count() == 1
        btn('确认列对应关系').click()
        assert page.get_by_text('不同字段不能对应同一个Excel列。', exact=True).count() >= 1
        select('客户姓名 *', 'C · 客户名称')
        btn('确认列对应关系').click()
        assert initial_customers == page.evaluate("PROTOTYPE.pages.find(p=>p.id==='salesCustomers').rows.length")
        top()
        page.screenshot(path=str(ROOT / 'resource' / 'excel-mapping.png'), full_page=True)
        btn('下一步').click()
        select('推广产品', '舒适洁牙权益')
        select('来源展示名', '安和保险客户福利')
        page.get_by_label('单卡采购价（元）', exact=True).fill('1.25')
        btn('提交销售订单').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        order = page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-resource')).find(p=>p.id==='sales').rows[0]")
        assert order['quantity'] == 3 and order['totalCents'] == 375 and order['status'] == '待付款'
        assert order['importSnapshot']['sheet'] == '九月福利名单' and order['importSnapshot']['header'] == 3
        assert len(order['importSnapshot']['sha256']) == 64
        assert order['customers'][0]['sourceRow'] == 4 and order['customers'][0]['phone'] == '13800000011'
        assert not order['cards']
        print('UI mapping / explicit confirmation / original row / price / no issue before approval passed', flush=True)

        # Stored schema contains no customer values. Reordering retains mapping; other org cannot reuse.
        checks = page.evaluate("""async () => {
          const I=PrototypeImport, E=PrototypeExcel, org=PROTOTYPE.org;
          const saved=localStorage.getItem(I.formatKey(org));
          const book=await I.readWorkbook(new File([E.workbook([{name:'名单',rows:[['会员编号','客户名称','购卡数量','客户手机'],['X','客户甲（演示）',2,'13800000011']]}])],'reordered.xlsx'));
          const d=I.configure(book,'reordered.xlsx',0,1,org), other=I.configure(book,'reordered.xlsx',0,1,'其他机构（演示）');
          const changed=structuredClone(book);changed.sheets[0].rows[0].cells[3]='联系人号码';
          const updated=I.configure(changed,'changed.xlsx',0,1,org);
          const ambiguous=I.guess(['客户姓名','客户手机','业务员手机','购卡数量']);
          const duplicate=I.guess(['客户姓名','客户手机','客户手机','购卡数量']);
          const errors=PrototypeSales.inspect([{name:'甲',phone:'13800000019',quantity:''},{name:'乙',phone:'13800000020',quantity:-1},{name:'丙',phone:'13800000021',quantity:1.5}],PROTOTYPE.pages);
          return {safe:!saved.includes('13800000011')&&!saved.includes('客户甲'),reuse:d.notice.includes('已套用')&&d.mapping.phone==='3'&&!d.confirmed,isolated:!other.notice.includes('已套用'),changed:!updated.notice.includes('已套用'),ambiguous:!ambiguous.phone&&!duplicate.phone,errors:errors.every(r=>r.error)};
        }""")
        assert all(checks.values()), checks
        start()
        sample('使用缺数量列示例')
        btn('确认列对应关系').click()
        assert page.get_by_text('请选择“开卡数量”对应的Excel列。', exact=True).count()
        select('开卡数量来源', '全部客户统一数量')
        assert page.get_by_label('每人统一开卡数量（张）', exact=True).input_value() == ''
        btn('确认列对应关系').click()
        page.get_by_text('请明确填写每人1～500张的统一数量，不能留空。', exact=True).first.wait_for()
        page.get_by_label('每人统一开卡数量（张）', exact=True).fill('2')
        btn('确认列对应关系').click()
        btn('下一步').click()
        assert page.locator('.arco-descriptions').inner_text().find('4') >= 0
        btn('上一步').click()
        assert btn('列对应关系已确认').is_disabled()
        # Changing sheets/header clears confirmation; returning doesn't silently approve.
        sample('使用机构格式示例')
        select('工作表', '填写说明')
        assert btn('确认列对应关系').count() == 1
        select('工作表', '九月福利名单')
        select('表头所在行', '第 1 行')
        btn('下一步').click()
        page.get_by_text('请先确认列对应关系。', exact=True).wait_for()
        print('template reuse / org isolation / ambiguous labels / explicit uniform quantity / sheet-header reset passed', flush=True)

        sample('使用异常名单示例')
        page.locator('.import-editor').get_by_role('tab', name='异常', exact=False).click()
        with page.expect_download() as downloaded:
            btn('下载错误清单').click()
        with zipfile.ZipFile(downloaded.value.path()) as book:
            sheet = book.read('xl/worksheets/sheet1.xml').decode()
            assert sheet.count('<row ') == 6  # Five errors + header, including both duplicate rows.
            assert '手机号与姓名不一致' in sheet and '不会自动删除或累加' in sheet
        btn('确认列对应关系').click()
        btn('下一步').click()
        page.get_by_text('请先修正客户明细，异常数据不能提交。', exact=True).wait_for()
        page.locator('.import-editor').get_by_role('heading', name='3. 校验预览').scroll_into_view_if_needed()
        page.screenshot(path=str(ROOT / 'resource' / 'excel-errors.png'), full_page=True)
        page.set_viewport_size({'width': 768, 'height': 1000})
        sample('使用机构格式示例')
        top()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.arco-drawer').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth+1')
        page.screenshot(path=str(ROOT / 'resource' / 'excel-mapping-narrow.png'), full_page=True)
        page.set_viewport_size({'width': 1280, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

        # Actual ZIP variants: formula, macro, oversized, corrupted. Failed read must clear previous rows.
        with page.expect_download() as downloaded:
            btn('下载客户Excel模板').click()
        template = Path(downloaded.value.path()).read_bytes()

        def transform(kind):
            out = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(template)) as src, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dest:
                for name in src.namelist():
                    data = src.read(name)
                    if kind == 'formula' and name == 'xl/worksheets/sheet1.xml':
                        data = data.replace(b'<v>2</v>', b'<f>1+1</f><v>2</v>')
                    dest.writestr(name, data)
                if kind == 'macro':
                    dest.writestr('xl/vbaProject.bin', b'not-a-real-macro')
            return out.getvalue()

        for buffer, expected in [(transform('formula'), '公式'), (transform('macro'), '宏'), (b'broken', '无法读取Excel'), (b'0' * (1024 * 1024 + 1), '1MB')]:
            upload(buffer)
            page.locator('.import-editor .arco-alert').filter(has_text='读取失败').wait_for()
            assert expected in page.locator('.import-editor').inner_text()
            assert page.locator('.import-mappings').count() == 0
            btn('下一步').click()
            assert page.get_by_text('请先确认列对应关系。', exact=True).count()

        # Latest upload wins, even if the earlier file finishes late.
        page.evaluate("""() => {const I=PrototypeImport,read=I.readWorkbook;I.readWorkbook=read;window.__slowRead=File.prototype.arrayBuffer;File.prototype.arrayBuffer=async function(){if(this.name==='slow.xlsx')await new Promise(r=>setTimeout(r,500));return window.__slowRead.call(this);};}""")
        upload(template, 'slow.xlsx')
        upload(b'broken', 'newest.xlsx')
        page.wait_for_timeout(900)
        assert page.locator('.import-editor').inner_text().find('读取失败') >= 0
        assert page.locator('.import-mappings').count() == 0
        page.evaluate('File.prototype.arrayBuffer=window.__slowRead')
        print('error tabs / complete XLSX error export / formula-macro-size guards / upload race / responsive passed', flush=True)

        # Explicit fixture handoff only; platform never receives data automatically.
        page.goto(BASE + '/platform/#sales')
        page.wait_for_selector('.workspace h1')
        page.evaluate("""order=>{const key='chihuitong-prototype-v1-platform',p=JSON.parse(localStorage.getItem(key));p.find(x=>x.id==='sales').rows.unshift(order);localStorage.setItem(key,JSON.stringify(p));}""", order)
        page.reload()
        page.locator('.status-tabs').first.get_by_placeholder('搜索编号、名称或关键字').fill(order['id'])
        page.locator('tr').filter(has_text=order['id']).get_by_role('button', name='详情', exact=True).click()
        page.get_by_role('heading', name='Excel导入依据').scroll_into_view_if_needed()
        assert page.locator('.import-receipt').inner_text().find('九月福利名单') >= 0
        assert page.locator('.import-receipt .arco-select').count() == 0
        assert btn('审核通过并开卡').count() == 0  # Paid order has not been paid yet.
        page.screenshot(path=str(ROOT / 'platform' / 'excel-import-receipt.png'), full_page=True)
        assert not errors, errors
        print('platform immutable import receipt / unpaid guard; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
