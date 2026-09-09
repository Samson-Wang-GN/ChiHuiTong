"""REQ-032 browser and pure-rule tests; all files and institutions are fictitious."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8765'


def verify():
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(8000)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))

        def go(role,route):
            page.goto(f'{BASE}/{role}/#{route}')
            page.wait_for_selector('.workspace h1')
            page.wait_for_timeout(350)

        def button(name):
            root=page.locator('.arco-drawer').last if page.locator('.arco-drawer').count() else page
            return root.get_by_role('button',name=name,exact=True)

        for role,route in [('channel','clinics'),('clinic','profile')]:
            go(role,route)
            page.evaluate('()=>{const key="chihuitong-prototype-v1-"+PROTOTYPE.role;if(!localStorage.getItem(key))localStorage.setItem(key,JSON.stringify(PrototypeClinicInfo.migrate(PrototypeWorkflows.migrate(structuredClone(PROTOTYPE.pages))))) }')
            page.reload()
            page.wait_for_selector('.workspace h1')
            # Exercise original upload/map draft paths; approved changes have a dedicated suite.
            page.evaluate('role=>{const key="chihuitong-prototype-v1-"+role;const p=JSON.parse(localStorage.getItem(key));p.find(x=>x.id===(role==="clinic"?"profile":"clinics")).rows[0].qualification="草稿";localStorage.setItem(key,JSON.stringify(p))}',role)
            page.reload()
            page.wait_for_selector('.workspace h1')
            if role=='channel':
                button('详情').first.click()
            button('维护门诊资料').click()
            page.wait_for_timeout(400)
            page.get_by_label('前台预约手机号',exact=True).fill('123')
            button('保存门诊资料').click()
            page.get_by_text('请填写11位前台预约手机号。',exact=True).wait_for()
            page.get_by_label('前台预约手机号',exact=True).fill('13800000088')
            page.get_by_label('门诊业务联系人',exact=True).fill('测试业务联系人')
            button('保存门诊资料').click()
            page.get_by_text('门诊业务联系人与联系人电话请一起填写，或一起留空待补充。',exact=True).wait_for()
            page.get_by_label('联系人电话',exact=True).fill('010-12345678')
            # Upload an actual PNG generated from a screenshot of a synthetic UI area.
            png=page.locator('.arco-drawer-header').last.screenshot()
            image_input=page.locator('.arco-drawer').last.locator('input[type=file][accept=".png,.jpg,.jpeg"]')
            image_input.set_input_files({'name':'展示图.png','mimeType':'image/png','buffer':png})
            button('替换展示图片').wait_for()
            image_input.set_input_files({'name':'损坏.jpg','mimeType':'image/jpeg','buffer':b'not an image'})
            page.get_by_text('图片无法解码，原图片未更换。',exact=True).wait_for()
            assert button('替换展示图片').count()==1
            button('按地址在地图中定位（演示）').click()
            button('确认门诊位置（演示）').click()
            page.get_by_text('请在地图上核对当前地址和门诊入口，并勾选确认。',exact=True).wait_for()
            assert page.get_by_label('经度（演示校正）',exact=True).count()==0
            assert page.evaluate("()=>!PrototypeClinicInfo.validPoint({longitude:181,latitude:39,coordinateSystem:'GCJ-02'})")
            map_view=page.get_by_role('group',name='门诊入口示意地图',exact=True)
            map_view.click(position={'x':220,'y':210})
            page.locator('.arco-checkbox').filter(has_text='已在地图上核对门诊入口（演示）').click()
            button('确认门诊位置（演示）').click()
            page.get_by_text('位置已确认，请保存门诊资料；移动点位后需要重新确认。',exact=True).wait_for()
            # Keyboard and pointer adjustments invalidate the previous confirmation.
            map_view.focus()
            map_view.press('ArrowRight')
            page.get_by_text('当前点位尚未确认，不能用于位置推荐。',exact=True).wait_for()
            assert not page.locator('.arco-checkbox input').last.is_checked()
            before_zoom=page.get_by_test_id('clinic-map-coordinates').inner_text()
            button('放大地图').click()
            button('缩小地图').click()
            assert page.get_by_test_id('clinic-map-coordinates').inner_text()==before_zoom
            marker=page.get_by_test_id('clinic-map-marker')
            marker.scroll_into_view_if_needed()
            box=marker.bounding_box()
            page.mouse.move(box['x']+box['width']/2,box['y']+15)
            page.mouse.down()
            page.mouse.move(box['x']+box['width']/2+28,box['y']+38,steps=5)
            page.mouse.up()
            assert page.get_by_test_id('clinic-map-coordinates').inner_text()!=before_zoom
            button('选择门诊楼入口（示意）').click()
            page.locator('.arco-checkbox').filter(has_text='已在地图上核对门诊入口（演示）').click()
            button('确认门诊位置（演示）').click()
            page.locator('.clinic-location-section').screenshot(path=str(ROOT/role/'clinic-location-map.png'))
            button('保存门诊资料').click()
            page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
            data=page.evaluate('(role)=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-"+role))',role)
            c=next(p for p in data if p['id']==route)['rows'][0]
            assert c['phone']=='13800000088' and c['businessPhone']=='010-12345678' and c['cover']['name']=='展示图.png'
            assert c['location']['status']=='已确认（演示）' and c['infoVersion']==1
            assert abs(c['location']['longitude']-116.3196)<0.000001
            if role=='channel':
                assert c['qualification']=='草稿' and c['contractVersions']
            public=page.evaluate('c=>PrototypeClinicInfo.publicData(c)',c)
            assert 'businessPhone' not in public and 'businessContact' not in public
            assert page.locator('.clinic-display-cover img').first.evaluate('(img)=>getComputedStyle(img).objectFit')=='cover'
            page.screenshot(path=str(ROOT/role/'clinic-info-desktop.png'))
            page.reload()
            page.wait_for_selector('.workspace h1')
            if role=='channel':button('详情').first.click()
            button('维护门诊资料').click()
            page.wait_for_timeout(400)
            assert page.get_by_label('前台预约手机号',exact=True).input_value()=='13800000088'
            page.get_by_label('持证经营地址',exact=True).fill('无法解析的新地址')
            assert page.get_by_role('group',name='门诊入口示意地图',exact=True).count()==0
            button('按地址在地图中定位（演示）').click()
            page.get_by_text('真实地图尚未接入：此地址没有演示候选。请核对地址后重试，不能用默认坐标替代。',exact=True).wait_for()
            button('移除展示图片').click()
            button('保存门诊资料').click()
            page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
            c=page.evaluate('(role)=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-"+role)).find(p=>p.id===(role==="channel"?"clinics":"profile")).rows[0]',role)
            assert c['location'] is None and c['cover'] is None and c['qualification']=='草稿'
            assert len(c['infoHistory'])==2 and c['infoHistory'][-1]['before']['location']
            assert page.evaluate('c=>PrototypeClinicInfo.publicData(c).location',c) is None
            blocked=page.evaluate('c=>{c.id="OTHER";c.channel="其他渠道";return PrototypeClinicInfo.commit(c,{...c,phone:"13800000099"})}',c)
            assert blocked=='只能维护本门诊或本渠道管理的门诊。'
            button('维护门诊资料').click()
            page.set_viewport_size({'width':768,'height':900})
            page.wait_for_timeout(400)
            assert page.locator('.arco-drawer').last.bounding_box()['width']<=768
            page.screenshot(path=str(ROOT/role/'clinic-info-narrow.png'))
            page.set_viewport_size({'width':1440,'height':1000})
            print(role+': upload/decode/preserve/remove, contacts, geocode confirmation/invalidation, scope, history and narrow passed',flush=True)


        go('channel','clinics')
        button('录入签约门诊').click()
        assert button('按地址在地图中定位（演示）').is_disabled()
        for label,value in [('门诊名称','地图新建门诊（演示）'),('经营主体','测试口腔公司'),('持证经营地址','演示市景明路28号'),('门诊联系人','演示接待'),('前台预约手机号','13800000077'),('负责业务员','演示业务员')]:
            page.get_by_label(label,exact=True).fill(value)
        upload=page.locator('.arco-drawer').last.locator('input[type=file][accept=".png,.jpg,.jpeg"]')
        upload.set_input_files({'name':'渠道新建展示.png','mimeType':'image/png','buffer':png})
        button('替换展示图片').wait_for()
        button('按地址在地图中定位（演示）').click()
        button('选择门诊楼入口（示意）').click()
        page.locator('.arco-checkbox').filter(has_text='已在地图上核对门诊入口（演示）').click()
        button('确认门诊位置（演示）').click()
        page.set_viewport_size({'width':768,'height':900})
        page.get_by_role('group',name='门诊入口示意地图').scroll_into_view_if_needed()
        page.screenshot(path=str(ROOT/'channel'/'clinic-map-create-narrow.png'))
        assert page.get_by_role('group',name='门诊入口示意地图').bounding_box()['width']<768
        button('保存门诊资料').click()
        page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
        created=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-channel")).find(p=>p.id==="clinics").rows.find(c=>c.name==="地图新建门诊（演示）")')
        assert created['cover']['name']=='渠道新建展示.png'
        assert created['location']['status']=='已确认（演示）' and created['qualification']=='草稿'
        button('维护门诊资料').click()
        upload=page.locator('.arco-drawer').last.locator('input[type=file][accept=".png,.jpg,.jpeg"]')
        upload.set_input_files({'name':'渠道替换展示.png','mimeType':'image/png','buffer':png})
        page.wait_for_function('()=>document.querySelector(".clinic-display-cover img")')
        page.wait_for_timeout(200)
        button('保存门诊资料').click()
        page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
        stored=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-channel")).find(p=>p.id==="clinics").rows.find(c=>c.name==="地图新建门诊（演示）")')
        assert stored['cover']['name']=='渠道替换展示.png'
        button('维护门诊资料').click()
        button('移除展示图片').click()
        page.get_by_role('group',name='门诊入口示意地图').click(position={'x':120,'y':100})
        page.locator('.arco-drawer').last.locator('.arco-drawer-close-icon').click()
        page.locator('.arco-modal').get_by_role('button',name='确定',exact=True).click()
        page.wait_for_selector('input[aria-label="前台预约手机号"]',state='detached')
        retained=page.evaluate('()=>JSON.parse(localStorage.getItem("chihuitong-prototype-v1-channel")).find(p=>p.id==="clinics").rows.find(c=>c.name==="地图新建门诊（演示）")')
        assert retained==stored
        page.set_viewport_size({'width':1440,'height':1000})
        print('channel create image/map persistence, image replacement, narrow map and cancelled edits passed',flush=True)

        go('platform','clinics')
        button('详情').first.click()
        assert page.get_by_text('门诊业务联系人',exact=True).count()
        assert not page.get_by_role('button',name='维护门诊资料',exact=True).count()
        assert not errors, errors
        print('platform review visibility; browser errors: 0',flush=True)
        browser.close()


if __name__=='__main__':verify()
