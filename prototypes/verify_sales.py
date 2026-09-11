"""0.21 销售原型专项：全部为隔离浏览器中的虚构数据，不执行真实支付。"""
import io
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent


def verify():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def go(role, route='sales'):
            page.goto(f'{BASE}/{role}/#{route}')
            page.reload()
            page.wait_for_selector('.workspace h1')
            if route == 'sales':
                page.get_by_role('tab', name='销售订单', exact=True).click()

        def data():
            return page.evaluate("JSON.parse(localStorage.getItem('chihuitong-prototype-v1-'+PROTOTYPE.role))")

        def sales():
            return next(p for p in data() if p['id'] == 'sales')['rows']

        def button(text, scope=None):
            return (scope or page).get_by_role('button', name=text, exact=True)

        def select(label, value):
            page.locator('.flow-field').filter(has=page.get_by_text(label, exact=True)).locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=value).last.click()

        def detail(identifier):
            page.locator('.status-tabs').first.get_by_placeholder('搜索编号、名称或关键字').fill(identifier)
            button('详情', page.locator('tr').filter(has_text=identifier)).first.click()
            page.wait_for_selector('.arco-drawer')

        def submit_action(label, check=None, reference=None, attachment=False):
            button(label).click()
            modal = page.locator('.arco-modal')
            modal.get_by_label('处理说明', exact=True).fill('虚构采购审核测试')
            if reference:
                modal.locator('input.arco-input').fill(reference)
            if attachment:
                button('使用演示附件', modal).click()
            if check:
                modal.get_by_text(check, exact=True).click()
            button('提交', modal).click()
            modal.wait_for(state='detached')

        go('resource')
        assert page.locator('.sidebar').get_by_text('推广产品销售', exact=True).count() == 1
        assert page.evaluate("PROTOTYPE.pages.filter(p=>['imports','orders','cards'].includes(p.id)).every(p=>p.hidden&&!p.create&&!p.actions.length)")
        for route in ['imports', 'orders', 'cards']:
            go('resource', route)
            assert page.locator('.workspace h1').inner_text() == '推广产品销售'
        page.get_by_role('tab', name='历史批次记录', exact=True).click()
        button('详情').first.click()
        assert button('整批回滚').count() == 0
        page.locator('.arco-drawer-close-icon').click()
        go('resource')

        # 不记名：无上传，无客户字段，零元直接待审核，100张不生成卡片。
        button('新建销售订单').click()
        button('下一步').click()
        assert button('上传客户Excel').count() == 0
        assert page.get_by_label('客户手机号', exact=True).count() == 0
        button('下一步').click()
        select('推广产品', '舒适洁牙权益')
        select('来源展示名', '安和保险客户福利')
        assert float(page.get_by_label('单卡采购价（元）', exact=True).input_value()) == 0
        button('提交销售订单').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        physical = sales()[0]
        assert physical['quantity'] == 100 and physical['totalCents'] == 0 and physical['status'] == '待审核'
        assert not physical['cards'] and not physical['customers']

        # 记名单客：真实录入，手机号格式统一，收费在审核前付款。
        button('新建销售订单').click()
        select('销售方式', '记名非实体卡')
        select('客户录入方式', '单个客户')
        button('下一步').click()
        page.get_by_label('资源方客户编号（选填）', exact=True).fill('000042')
        page.get_by_label('客户姓名', exact=True).fill('客户甲（演示）')
        page.get_by_label('客户手机号', exact=True).fill('+86 138 0000 0011')
        page.get_by_label('客户开卡张数', exact=True).fill('3')
        button('下一步').click()
        select('推广产品', '舒适洁牙权益')
        select('来源展示名', '安和保险客户福利')
        page.get_by_label('单卡采购价（元）', exact=True).fill('1.25')
        button('提交销售订单').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        single = sales()[0]
        assert single['totalCents'] == 375 and single['status'] == '待付款'
        assert single['customers'][0]['phone'] == '13800000011'
        detail(single['id'])
        submit_action('上传采购付款凭证', '已在线下向平台全额付款', 'TEST-PAID-SINGLE', True)
        single = next(o for o in sales() if o['id'] == single['id'])
        assert single['status'] == '付款待确认' and single['confirmedCents'] == 0
        assert button('确认采购收款').count() == 0
        go('resource')

        # 批量Excel：实际下载模板并上传，支持常见deflate；损坏/公式拒绝。
        button('新建销售订单').click()
        select('销售方式', '记名非实体卡')
        button('下一步').click()
        with page.expect_download() as download:
            button('下载客户Excel模板').click()
        template = Path(download.value.path()).read_bytes()
        compressed = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(template)) as src, zipfile.ZipFile(compressed, 'w', zipfile.ZIP_DEFLATED) as dest:
            for info in src.infolist():
                dest.writestr(info.filename, src.read(info.filename))
        page.locator('input[type=file]').set_input_files({'name': '虚构客户.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': compressed.getvalue()})
        page.get_by_text('虚构客户.xlsx', exact=True).wait_for()
        button('确认列对应关系').click()
        button('下一步').click()
        select('推广产品', '舒适洁牙权益')
        select('来源展示名', '安和保险客户福利')
        page.get_by_label('单卡采购价（元）', exact=True).click()
        page.wait_for_timeout(400)
        page.screenshot(path=str(ROOT / 'resource' / 'sales-wizard.png'), full_page=True)
        button('提交销售订单').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        batch = sales()[0]
        assert batch['quantity'] == 3 and len(batch['customers']) == 2 and batch['status'] == '待审核'
        checks = page.evaluate("""async () => {
          const p=PROTOTYPE.pages, S=PrototypeSales;
          const conflict=S.inspect([{name:'错误姓名',phone:'13800000011',quantity:1}],p)[0].error;
          const duplicate=S.inspect([{name:'甲',phone:'13800000099',quantity:1},{name:'甲',phone:'13800000099',quantity:1}],p)[1].error;
          const bad=await S.readExcel(new File(['bad'],'bad.xlsx')).then(()=>false,()=>true);
          const z=PrototypeExcel.workbook([{name:'x',rows:[['错误列'],[1]]}]);
          const header=await S.readExcel(new File([z],'bad.xlsx')).then(()=>false,()=>true);
          const numbers=[];
          for(const title of ['资源方客户编号','客户编号','会员编号']){
            const bytes=PrototypeExcel.workbook([{name:'x',rows:[[title,'姓名','手机号','开卡数量'],['000042','虚构甲','13800000091',1]]}]);
            numbers.push((await S.readExcel(new File([bytes],'numbers.xlsx')))[0].customerNo);
          }
          return {conflict,duplicate,bad,header,numbers};
        }""")
        assert checks['conflict'] and checks['duplicate'] and checks['bad'] and checks['header']
        assert checks['numbers'] == ['000042'] * 3
        print('three resource sale routes / price cents / real XLSX import / validation passed', flush=True)

        # 交接使用测试夹具注入，不代表原型有跨角色同步。
        go('platform')
        page.evaluate("""orders=>{
          const p=PrototypeSales.migrate(PrototypeOperations.migrate(PrototypeWorkflows.migrate(JSON.parse(JSON.stringify(PROTOTYPE.pages)))));
          p.find(x=>x.id==='sales').rows.push(...orders);
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));
        }""", [single, batch, physical])
        page.reload()
        detail(single['id'])
        button('确认采购收款').click()
        modal = page.locator('.arco-modal')
        modal.get_by_label('处理说明', exact=True).fill('缺少到账确认必须阻断')
        button('提交', modal).click()
        modal.get_by_text('请核实全额实际到账及全部可读凭证。', exact=True).wait_for()
        modal.get_by_text('已核实本单采购款全额实际到账', exact=True).click()
        button('提交', modal).click()
        modal.wait_for(state='detached')
        submit_action('审核通过并开卡', '已核对产品授权、采购价格与全部客户资料')
        issued = next(o for o in sales() if o['id'] == single['id'])
        assert len(issued['cards']) == 3 and all(c['status'] == '待领取' for c in issued['cards'])
        assert issued['customers'][0]['customerId'] == 'SC-001'
        assert issued['customers'][0]['customerNo'] == '000042'
        go('platform')
        detail(batch['id'])
        submit_action('审核通过并开卡', '已核对产品授权、采购价格与全部客户资料')
        created = next(p for p in data() if p['id'] == 'salesCustomers')['rows']
        assert len(created) == 2 and created[1]['registered'] is False
        go('platform')
        detail(physical['id'])
        submit_action('审核通过并开卡', '已核对产品授权、采购价格与全部客户资料')
        first = next(o for o in sales() if o['id'] == physical['id'])
        assert len(first['cards']) == 100 and first['range']['count'] == 100
        page.screenshot(path=str(ROOT / 'platform' / 'sales-order.png'), full_page=True)
        submit_action('登记制作寄送', reference='演示物流 TEST-POST-001')

        # 业务函数级阻断：非零未付款、重复开卡、授权/来源、整数、姓名冲突；号段不重用。
        result = page.evaluate("""id=>{
          const S=PrototypeSales,p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));
          const copy=()=>JSON.parse(JSON.stringify(p)),list=x=>x.find(p=>p.id==='sales').rows;
          const bad=(fn)=>{const x=copy(),o=list(x).find(r=>r.id==='SALE-DEMO-FREE');fn(o,x);return !!S.approve(x,o.id,180,'test',true).error;};
          const unpaid=bad(o=>{o.unitCents=100;o.totalCents=200;});
          const mismatch=bad(o=>o.customers[0].name='其他姓名');
          const source=bad(o=>o.source='其他资源方品牌');
          const auth=bad((o,x)=>x.find(p=>p.id==='contractSchemes').rows.forEach(t=>t.status='已停用'));
          const quantity=bad(o=>o.quantity=1.5);
          const repeat=!!S.approve(p,id,180,'test',true).error;
          const x=copy(),previous=list(x).find(r=>r.id===id);previous.status='已取消';previous.cards.forEach(c=>c.status='已作废');
          const next={...JSON.parse(JSON.stringify(previous)),id:'RANGE-NEXT',range:null,cards:[],status:'待审核',quantity:5};list(x).push(next);
          const r=S.approve(x,next.id,180,'test',true),allocated=r.pages&&list(r.pages).find(o=>o.id===next.id);
          return {unpaid,mismatch,source,auth,quantity,repeat,range:allocated?.range.start>previous.range.end};
        }""", physical['id'])
        assert all(result.values()), result
        print('platform full payment / named match-create / unique ranges / guards passed', flush=True)

        # 外部编号仅留存：同编号不同客户不合并，编号不同/空不拆分已有客户。
        identifiers = page.evaluate("""() => {
          const S=PrototypeSales, p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));
          const run=customers=>{
            const x=structuredClone(p),o=x.find(r=>r.id==='sales').rows.find(r=>r.id==='SALE-DEMO-FREE');
            o.customers=customers;o.quantity=customers.length;
            const result=S.approve(x,o.id,180,'编号边界虚构测试',true);
            if(result.error)throw Error(result.error);
            const order=result.pages.find(r=>r.id==='sales').rows.find(r=>r.id===o.id);
            return {order,customers:result.pages.find(r=>r.id==='salesCustomers').rows};
          };
          const item=(customerNo,phone='13800000011',name='客户甲（演示）')=>({customerNo,phone,name,quantity:1});
          const same=run([item('DIFFERENT')]),empty=run([item('')]);
          const separate=run([item('SC-001','13800000091','虚构丙'),item('SC-001','13800000092','虚构丁')]);
          const ids=separate.order.customers.map(r=>r.customerId);
          return {
            same:same.order.customers[0].customerId==='SC-001',
            empty:empty.order.customers[0].customerId==='SC-001',
            separate:ids[0]!==ids[1]&&ids.every(id=>id!=='SC-001'&&separate.customers.some(c=>c.id===id)),
            cards:separate.order.cards.every(c=>ids.includes(c.customerId)),
            retained:separate.order.customers.every(c=>c.customerNo==='SC-001'),
            conflict:!!S.inspect([item('SC-001','13800000011','错误姓名')],p)[0].error
          };
        }""")
        assert all(identifiers.values()), identifiers
        print('external customer numbers never link / generated platform IDs / card links passed', flush=True)

        # 领取后不能取消；停止申请须平台处理，只停止尚未领取。
        issued['cards'][0]['status'] = '已领取'
        go('resource')
        page.evaluate("""o=>{const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-resource'));p.find(x=>x.id==='sales').rows=p.find(x=>x.id==='sales').rows.filter(r=>r.id!==o.id).concat([o]);localStorage.setItem('chihuitong-prototype-v1-resource',JSON.stringify(p));}""", issued)
        page.reload()
        detail(issued['id'])
        button('申请取消订单').click()
        modal = page.locator('.arco-modal')
        modal.get_by_label('处理说明', exact=True).fill('测试禁止取消')
        button('提交', modal).click()
        modal.get_by_text('已有客户领取或激活，不能整单取消。', exact=True).wait_for()
        button('取消', modal).click()
        submit_action('申请停止剩余未领取', '已核实操作范围及影响')
        stopped = next(o for o in sales() if o['id'] == issued['id'])
        assert stopped['status'] == '停止待审核' and stopped['cards'][1]['status'] == '待领取'
        go('platform')
        page.evaluate("""o=>{const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));p.find(x=>x.id==='sales').rows=p.find(x=>x.id==='sales').rows.filter(r=>r.id!==o.id).concat([o]);localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));}""", stopped)
        go('platform', 'tasks?type=sales')
        row = page.locator('tr').filter(has_text=issued['id'])
        button('立即处理', row).click()
        submit_action('停止剩余未领取', '已核实操作范围及影响')
        stopped = next(o for o in sales() if o['id'] == issued['id'])
        assert [c['status'] for c in stopped['cards']] == ['已领取', '已停止', '已停止']
        assert page.locator('.workspace h1').inner_text() == '待处理任务'
        print('claimed cancellation blocked / stop approval preserves claimed / direct tasks passed', flush=True)

        # 收费拒绝后的退款登记；保留全部采购款事实，不能反向充当收益付款。
        go('platform')
        detail('SALE-DEMO-PAID')
        submit_action('确认采购收款', '已核实本单采购款全额实际到账')
        submit_action('审核不通过')
        rejected = next(o for o in sales() if o['id'] == 'SALE-DEMO-PAID')
        assert rejected['refundStatus'] == '待退款' and not rejected['cards']
        submit_action('登记线下退款', '已在线下全额退款给原采购方', 'REFUND-TEST-001', True)
        refunded = next(o for o in sales() if o['id'] == 'SALE-DEMO-PAID')
        assert refunded['refund']['amountCents'] == 2000 and refunded['confirmedCents'] == 2000
        assert refunded['refundStatus'] == '已登记退款'
        assert page.evaluate("!!localStorage.getItem('chihuitong-prototype-v1-platform-before-0.21')")

        # 实体卡已激活取消阻断；取消审核仅作废未激活卡，号段原件保留。
        first['cards'][0]['status'] = '已激活'
        go('resource')
        page.evaluate("""o=>{const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-resource'));p.find(x=>x.id==='sales').rows=p.find(x=>x.id==='sales').rows.filter(r=>r.id!==o.id).concat([o]);localStorage.setItem('chihuitong-prototype-v1-resource',JSON.stringify(p));}""", first)
        page.reload()
        detail(first['id'])
        button('申请取消订单').click()
        modal = page.locator('.arco-modal')
        modal.get_by_label('处理说明', exact=True).fill('实体卡已激活测试')
        button('提交', modal).click()
        modal.get_by_text('已有客户领取或激活，不能整单取消。', exact=True).wait_for()
        button('取消', modal).click()
        first['cards'][0]['status'] = '未激活'
        first['status'] = '取消待审核'
        go('platform')
        page.evaluate("""o=>{const p=JSON.parse(localStorage.getItem('chihuitong-prototype-v1-platform'));p.find(x=>x.id==='sales').rows=p.find(x=>x.id==='sales').rows.filter(r=>r.id!==o.id).concat([o]);localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(p));}""", first)
        page.reload()
        detail(first['id'])
        submit_action('审核取消', '已核实操作范围及影响')
        cancelled = next(o for o in sales() if o['id'] == first['id'])
        assert cancelled['status'] == '已取消' and all(c['status'] == '已作废' for c in cancelled['cards'])
        assert cancelled['range'] == first['range']
        print('paid rejection / refund evidence / activated physical cancellation guard / cancel retains ranges / backup passed', flush=True)

        for role in ['resource', 'platform']:
            go(role)
            page.set_viewport_size({'width': 768, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / role / 'sales-narrow.png'), full_page=True)
        assert not errors, errors
        print('narrow viewport passed; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
