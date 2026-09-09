"""0.19 browser, role workflow and real XLSX package checks (no real payment)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8765'

def verify():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},locale='zh-CN')
        page.set_default_timeout(8000)
        errors=[]
        def error(e):
            errors.append(str(e));print('BROWSER ERROR:',e.stack,flush=True)
        page.on('pageerror',error)
        def go(role,route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('.workspace h1')
        def button(name,root=None):
            return (root or page).get_by_role('button',name=name,exact=True)
        def confirm():
            page.locator('.arco-modal').last.get_by_role('button',name='确定',exact=True).click()
        def data(role):
            return page.evaluate('r=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-"+r))',role)
        go('platform','institutions')
        for role in ['platform','resource','channel','clinic']:
            go(role,'workbench')
            cards=page.locator('.task-card').count()
            for index in range(cards):
                go(role,'workbench');page.locator('.task-card').nth(index).click()
                assert '#tasks?type=' in page.url
                assert page.locator('h1').inner_text()=='待处理任务'
            print(role+': task links passed',flush=True)
        for role in ['resource','channel']:
            go(role,'tasks?type=earnings')
            button('立即处理',page.locator('tr').filter(has_text='确认本方对账单')).click()
            assert '#tasks?' in page.url
            assert button('登记付款').count()==0
            drawer=page.locator('.arco-drawer').last
            assert drawer.get_by_text('全部 13 笔',exact=False).count()
            button('详情',drawer).first.click()
            page.get_by_text('逐笔交易详情',exact=True).wait_for()
            page.locator('.arco-drawer-close-icon').last.click()
            page.wait_for_function("document.querySelectorAll('.arco-drawer').length===1")
            if role=='resource':
                with TemporaryDirectory(prefix='chihuitong-xlsx-') as directory:
                    button('下载Excel').click()
                    with page.expect_download() as download:
                        confirm()
                    file=Path(directory)/download.value.suggested_filename
                    download.value.save_as(str(file))
                    assert file.suffix=='.xlsx'
                    with ZipFile(file) as archive:
                        assert archive.testzip() is None
                        for name in archive.namelist(): ET.fromstring(archive.read(name))
                        root=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
                        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                        rs=root.findall('s:sheetData/s:row',ns)
                        assert len(rs)==14
                        assert sum(float(r.findall('s:c',ns)[7].find('s:v',ns).text) for r in rs[1:])==132
                        assert not root.findall('.//s:f',ns)
                        assert rs[1].findall('s:c',ns)[0].attrib['t']=='inlineStr'
                drawer.get_by_placeholder('搜索编号、名称或关键字').first.fill('撤销调整')
                with TemporaryDirectory(prefix='chihuitong-filter-') as directory:
                    button('下载Excel').click()
                    with page.expect_download() as download: confirm()
                    file=Path(directory)/'filtered.xlsx';download.value.save_as(str(file))
                    with ZipFile(file) as archive:
                        root=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
                        assert len(root.findall('s:sheetData/s:row',ns))==2
                drawer.get_by_placeholder('搜索编号、名称或关键字').first.fill('')
                page.locator('.arco-drawer .arco-table-content-scroll').evaluate_all('(nodes)=>nodes.forEach(n=>n.scrollLeft=0)')
                page.screenshot(path=str(ROOT/role/'statement-transactions.png'))
                print('real XLSX / all pages / filtered rows / negative adjustment / numeric totals passed',flush=True)
            button('确认对账单').click();button('提交',page.locator('.arco-modal')).click()
            page.get_by_text('请核对本方完整明细并勾选确认；只有本合作方可以确认。',exact=True).last.wait_for()
            page.locator('.arco-modal').get_by_text('已核对完整交易明细及金额，确认当前版本',exact=True).click()
            button('提交',page.locator('.arco-modal')).click()
            page.wait_for_selector('.arco-modal',state='hidden')
            s=next(r for p in data(role) if p['id']=='earnings' for r in p['rows'] if r.get('demo'))
            assert s['status']=='待付款' and not s['payments']
            page.locator('.arco-drawer-close-icon').last.click()
            assert not page.locator('tr').filter(has_text='确认本方对账单').get_by_role('button',name='立即处理').count()
            assert next(p for p in data(role) if p['id']=='tasks')['rows']
            page.reload();assert not page.locator('tr').filter(has_text='确认本方对账单').get_by_role('button',name='立即处理').count()
            print(role+': confirm in task page / history / no payment permission passed',flush=True)

        go('platform','tasks?type=earnings')
        row=page.locator('tr').filter(has_text='向合作方付款').first
        button('立即处理',row).click()
        assert button('确认对账单').count()==0
        button('登记付款').click();button('提交',page.locator('.arco-modal')).click()
        page.get_by_text('请填写准确的全额付款金额、有效日期、交易参考号、可读凭证，并确认已实际付款。',exact=True).last.wait_for()
        page.get_by_label('交易参考号',exact=True).fill('DEMO-BANK-001')
        button('使用演示附件').click()
        page.locator('.arco-modal').get_by_text('已在线下向本单收款机构全额付款，凭证与本笔交易一致',exact=True).click()
        page.get_by_label('付款金额（元）',exact=True).fill('1')
        button('提交',page.locator('.arco-modal')).click()
        assert not page.locator('.arco-modal-simple').count()
        page.get_by_label('付款金额（元）',exact=True).fill('198')
        page.screenshot(path=str(ROOT/'platform'/'partner-payment.png'))
        button('提交',page.locator('.arco-modal')).click();confirm()
        page.wait_for_selector('.arco-modal',state='hidden')
        s=next(r for p in data('platform') if p['id']=='earnings' for r in p['rows'] if r['id']=='DEMO-CHAN-AUG')
        assert s['status']=='待确认收款' and len(s['payments'])==1
        assert button('登记付款').count()==0
        page.locator('.arco-drawer-close-icon').last.click()
        assert not page.locator('tr').filter(has_text='向合作方付款').filter(has_text='待处理').count()
        print('platform payment / required voucher / exact amount / role guard / task completion passed',flush=True)

        go('platform','schemes')
        assert page.get_by_text('外部产品展示名称',exact=True).count()
        button('详情',page.locator('tr').filter(has_text='舒适洁牙权益')).click()
        button('编辑规则',page.locator('.arco-drawer').last).click()
        page.get_by_placeholder('请输入内部展示名称').fill('洁牙推广产品内部新名称')
        page.get_by_placeholder('请输入外部产品展示名称').fill('舒适洁牙服务新版')
        page.locator('.arco-modal .arco-select').first.click()
        page.get_by_text('洁牙券',exact=True).last.click()
        page.get_by_placeholder('请输入使用条件').fill('预约后使用，单次一份（演示）')
        button('编辑规则',page.locator('.arco-modal').last).click()
        page.get_by_placeholder('请输入内部展示名称').wait_for(state='hidden')
        d=data('platform');product=next(r for p in d if p['id']=='schemes' for r in p['rows'] if r['id']=='FA-001')
        assert product['name']=='洁牙推广产品内部新名称' and product['externalName']=='舒适洁牙服务新版'
        assert all(r['productName']=='舒适洁牙权益' for p in d if p['id']=='earnings' for s in p['rows'] if s.get('demo') for r in s['items'])
        assert page.evaluate('p=>PrototypeOperations.sameProduct(p,"舒适洁牙权益","洁牙推广产品内部新名称")',d)
        go('platform','institutions?institution=JG-001&section=products')
        assert page.get_by_text('洁牙推广产品内部新名称',exact=True).count()
        page.screenshot(path=str(ROOT/'platform'/'products-internal.png'))
        print('dual product names / stable identity / historic snapshot passed',flush=True)

        go('clinic','tasks?type=appointments')
        button('立即处理').first.click();button('确认预约').click()
        button('确认预约',page.locator('.arco-modal')).click()
        page.wait_for_selector('.arco-modal',state='hidden')
        assert '#tasks?' in page.url
        assert any(r['status']=='已处理' for p in data('clinic') if p['id']=='tasks' for r in p['rows'])
        go('channel','tasks?type=bills')
        button('立即处理').first.click();button('记录催收').click()
        page.get_by_label('催收内容').fill('演示已联系门诊付款')
        button('保存记录').click()
        page.wait_for_selector('.arco-modal',state='hidden')
        assert '#tasks?' in page.url
        assert any(r['status']=='已处理' for p in data('channel') if p['id']=='tasks' for r in p['rows'])
        go('channel','tasks')
        page.locator('.arco-drawer-close-icon').last.click()
        page.wait_for_selector('.arco-drawer',state='hidden')
        page.set_viewport_size({'width':768,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT/'channel'/'tasks-narrow.png'))
        print('clinic appointment / channel collection directly in tasks / narrow layout passed',flush=True)
        page.set_viewport_size({'width':1440,'height':1000})
        go('clinic','bills')
        button('详情',page.locator('tr').filter(has_text='逐笔演示')).click()
        with TemporaryDirectory(prefix='chihuitong-clinic-xlsx-') as directory:
            button('下载Excel').click()
            with page.expect_download() as download: confirm()
            file=Path(directory)/'clinic.xlsx';download.value.save_as(str(file))
            with ZipFile(file) as archive:
                root=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
                rs=root.findall('s:sheetData/s:row',ns)
                headers=[''.join(c.itertext()) for c in rs[0]]
                assert len(rs)==14 and '分配规则快照' not in headers
                clinic_index=headers.index('履约门诊')
                assert all(''.join(r.findall('s:c',ns)[clinic_index].itertext())=='明禾口腔（演示）' for r in rs[1:])
                amount_index=headers.index('费用金额（元）')
                assert sum(float(r.findall('s:c',ns)[amount_index].find('s:v',ns).text) for r in rs[1:])==660
        print('clinic bill XLSX / 13 transactions / 660 total / no partner allocation passed',flush=True)
        assert not errors,errors
        browser.close()

if __name__=='__main__':
    verify()
