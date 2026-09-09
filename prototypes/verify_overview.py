"""Read-only analytics prototype: exact metrics, events, scopes, charts and XLSX exports."""
import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765'


def verify():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        page.set_default_timeout(8000)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def go(role):
            page.goto(f'{BASE}/{role}/#customers')
            page.reload()
            page.wait_for_selector('.overview-metrics')

        def select(label, value):
            page.locator('.flow-field').filter(has=page.get_by_text(label, exact=True)).locator('.arco-select').click()
            page.locator('.arco-select-option').filter(has_text=value).last.click()

        def button(name, scope=None):
            return (scope or page).get_by_role('button', name=name, exact=True)

        go('resource')
        expected = page.evaluate("PrototypeOverview.snapshot(PrototypeOverview.facts(PROTOTYPE.pages).cards,'2026-09-09').values")
        assert expected['customers'] == 15 and expected['purchased'] == 33
        assert expected['activated'] == 27 and expected['appointments'] == 14
        assert expected['redemptions'] == 7 and expected['units'] == 11
        assert expected['bookingPeople'] == 8 and expected['redeemedPeople'] == 6
        assert abs(expected['activationRate'] - 27 / 33 * 100) < 1e-9
        assert expected['redemptionRate'] == 75
        assert page.get_by_text('星海银行（演示）', exact=True).count() == 0

        # Snapshots preserve the past when appointments are later cancelled or redemptions reversed.
        result = page.evaluate("""() => {
          const A=PrototypeOverview;
          const c={id:'c',purchasedAt:'2026-08-31',customerId:'u',boundAt:'2026-08-31',activatedAt:'2026-09-01',appointments:[
            {id:'a',createdAt:'2026-09-02',changes:[{at:'2026-09-02',status:'待确认'},{at:'2026-09-03',status:'成功'},{at:'2026-09-04',status:'完成'},{at:'2026-09-05',status:'成功'},{at:'2026-09-06',status:'取消'}],redemptions:[{id:'r',at:'2026-09-04',units:2,revokedAt:'2026-09-05'}]}]};
          const v=d=>A.snapshot([c],d).values;
          const nil=A.snapshot([], '2026-09-09').values;
          const monthly=A.series([c],'activationRate','2026-08-31','2026-09-09','month','累计');
          const net=A.series([c],'appointments','2026-09-02','2026-09-06','day','本期净变化');
          return {aug:v('2026-08-31'),wait:v('2026-09-02'),success:v('2026-09-03'),done:v('2026-09-04'),reverse:v('2026-09-05'),cancel:v('2026-09-06'),nil,monthly,net,week:A.buckets('2026-08-30','2026-09-08','week'),duplicate:A.snapshot([c,{...c,id:'other',owner:'other'}],'2026-09-04').values};
        }""")
        assert result['aug']['activated'] == 0
        assert [result[k]['appointments'] for k in ['wait', 'success', 'done', 'reverse', 'cancel']] == [1, 1, 1, 1, 0]
        assert result['done']['units'] == 2 and result['reverse']['redemptions'] == 0
        assert result['nil']['activationRate'] is None
        assert [p['value'] for p in result['monthly']] == [0, 100]
        assert result['net'][-1]['value'] == -1
        assert result['week'] == [{'start': '2026-08-30', 'end': '2026-08-30'}, {'start': '2026-08-31', 'end': '2026-09-06'}, {'start': '2026-09-07', 'end': '2026-09-08'}]
        assert result['duplicate']['customers'] == 1 and result['duplicate']['purchased'] == 2
        print('exact counts / unique customers / 3 booking states / cancellation / reversal / cohort rates / week-month boundaries passed', flush=True)

        page.evaluate("""() => {
          const A=PrototypeOverview;
          const c={id:'auto-card',purchasedAt:'2026-09-01',customerId:'auto-user',boundAt:'2026-09-01',activatedAt:'2026-09-01',appointments:[{id:'auto-appt',createdAt:'2026-09-02',changes:[{at:'2026-09-02',status:'成功'},{at:'2026-09-05',status:'完成',completionSource:'系统超时处理'}],redemptions:[]}]};
          const result=A.snapshot([c],'2026-09-09').values;
          if(result.appointments!==1||result.redemptions!==0||result.units!==0||result.redemptionRate!==0)throw Error('auto completed is not redemption');
          if(A.details([c],'appointments','2026-09-09')[0].completionSource!=='系统超时处理')throw Error('missing completion source');
        }""")
        print('auto-completed counts appointment only, no redemption/units; completion source detail passed', flush=True)

        for role in ['resource', 'platform']:
            go(role)
            names = page.evaluate('Object.values(PrototypeOverview.metrics).map(m=>m[0])')
            for name in names:
                button(name + '趋势').click()
                drawer = page.locator('.arco-drawer').last
                drawer.locator('svg[role=img]').wait_for()
                for value in ['按周', '按月', '按天']:
                    select('趋势粒度', value)
                    assert drawer.locator('svg[role=img]').count() == 1
                page.locator('.arco-drawer-close-icon').last.click()
                drawer.wait_for(state='detached')
            print(role + ': all 13 metrics open daily/weekly/monthly charts', flush=True)
            page.screenshot(path=str(ROOT / role / 'overview.png'), full_page=True)

        # Platform union, not summing per-source customer counts.
        both = page.evaluate("PrototypeOverview.snapshot(PrototypeOverview.facts(PROTOTYPE.pages).cards,'2026-09-09').values")
        assert both['customers'] == 15 and both['purchased'] == 66
        select('客户资源方', '安和经纪（演示）')
        button('查询').click()
        assert '33 张' in button('有效采购数量趋势').inner_text()
        button('舒适洁牙权益 卡片激活率趋势').click()
        select('趋势粒度', '按月')
        select('比例明细范围', '分母')
        page.wait_for_timeout(300)
        page.locator('.arco-drawer .arco-alert').first.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        page.screenshot(path=str(ROOT / 'platform' / 'overview-trend.png'))
        drawer = page.locator('.arco-drawer').last
        # Full filtered denominator is 22 rows, not only the eight visible rows.
        button('下载Excel', drawer).last.click()
        with page.expect_download() as download:
            button('确定', page.locator('.arco-modal')).click()
        with zipfile.ZipFile(io.BytesIO(Path(download.value.path()).read_bytes())) as z:
            sheet = ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
            ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            assert len(sheet.findall('.//m:row', ns)) == 23
            text = ''.join(sheet.itertext())
            assert '星海银行' not in text and '安和经纪' in text
        page.locator('.arco-drawer-close-icon').last.click()
        drawer.wait_for(state='detached')
        button('重置条件').click()
        print('platform source filter / product drilldown / full denominator XLSX / scope passed', flush=True)

        # Live same-role approvals feed the overview; no cross-role propagation is inferred.
        live = page.evaluate("""() => {
          const p=PrototypeSales.migrate(PrototypeOperations.migrate(PrototypeWorkflows.migrate(JSON.parse(JSON.stringify(PROTOTYPE.pages)))));
          const A=PrototypeOverview,before=A.snapshot(A.facts(p).cards,'2026-09-09').values;
          const q=PrototypeSales.approve(p,'SALE-DEMO-FREE',180,'分析验证',true);
          const after=A.snapshot(A.facts(q.pages).cards,'2026-09-09').values;
          localStorage.setItem('chihuitong-prototype-v1-platform',JSON.stringify(q.pages));
          return {before,after};
        }""")
        assert live['after']['purchased'] == live['before']['purchased'] + 2
        assert live['after']['customers'] == live['before']['customers']
        assert live['after']['activated'] == live['before']['activated']
        page.reload()
        assert '68 张' in button('有效采购数量趋势').inner_text()
        assert page.evaluate("!!localStorage.getItem('chihuitong-prototype-v1-platform-before-0.22')")

        go('resource')
        # Inject forbidden data only in the isolated test browser and verify projection blocks it.
        safe = page.evaluate("""() => {
          const p=JSON.parse(JSON.stringify(PROTOTYPE.pages));
          p.find(x=>x.id==='overviewFacts').rows.push({...p.find(x=>x.id==='overviewFacts').rows[0],id:'forbidden',owner:'禁止访问机构'});
          return PrototypeOverview.facts(p).cards.every(c=>c.owner===PROTOTYPE.org)&&PrototypeOverview.facts(p,'channel','').cards.length===0;
        }""")
        assert safe
        select('销售方式', '不记名实体卡')
        button('查询').click()
        assert '18 张' in button('有效采购数量趋势').inner_text()
        button('重置条件').click()
        button('查看旧客户记录（只读）').click()
        page.locator('.arco-drawer').get_by_text('客户甲（演示）', exact=True).wait_for()
        page.locator('.arco-drawer-close-icon').click()
        page.wait_for_selector('.arco-drawer', state='detached')
        print('same-role sales projection / refresh / backup / read-only legacy / forbidden-source exclusion passed', flush=True)

        for state in ['加载中', '加载失败', '空状态']:
            page.locator('.review-controls .arco-select').click()
            page.locator('.arco-select-option').filter(has_text=state).last.click()
            if state == '加载失败':
                button('重试').click()
                page.wait_for_selector('.overview-metrics')
            if state == '空状态':
                assert '—' in button('卡片激活率趋势').inner_text()
                button('卡片激活率趋势').click()
                page.get_by_text('全部时间点分母为0，暂不绘制百分比曲线。', exact=True).wait_for()
                page.locator('.arco-drawer-close-icon').click()
                page.wait_for_selector('.arco-drawer', state='detached')
        page.locator('.review-controls .arco-select').click()
        page.locator('.arco-select-option').filter(has_text='正常').last.click()
        page.set_viewport_size({'width': 768, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT / 'resource' / 'overview-narrow.png'), full_page=True)
        button('客户预约率趋势').click()
        page.wait_for_timeout(400)
        box = page.locator('.arco-drawer').last.bounding_box()
        assert box['x'] >= -1 and box['x'] + box['width'] <= 769, box
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT / 'resource' / 'overview-trend-narrow.png'))
        assert not errors, errors
        print('loading / retry / zero denominator / narrow page and trend; browser errors: 0', flush=True)
        browser.close()


if __name__ == '__main__':
    verify()
