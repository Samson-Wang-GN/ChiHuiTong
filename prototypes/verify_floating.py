"""Real Document Picture-in-Picture browser test; no real appointments or push."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = 'http://127.0.0.1:8765'
ROOT = Path(__file__).resolve().parent


def verify():
    with sync_playwright() as p:
        browser=p.chromium.launch()
        context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
        page=context.new_page();page.set_default_timeout(8000)
        errors=[]
        context.on('page',lambda tab:tab.on('pageerror',lambda e:errors.append(str(e))))
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'/clinic/')
        expect(page.get_by_role('button',name='开启悬浮工作台',exact=True)).to_be_visible()
        with context.expect_page() as event:
            page.get_by_role('button',name='开启悬浮工作台',exact=True).click()
        floating=event.value
        floating.set_viewport_size({'width':400,'height':520})
        floating.wait_for_selector('.floating-count strong')
        assert page.evaluate('documentPictureInPicture.window.document.body.className')=='floating-document'
        before=int(floating.locator('.floating-count strong').inner_text())
        assert '138' not in floating.locator('body').inner_text()
        assert '客户甲' not in floating.locator('body').inner_text()
        page.get_by_role('button',name='查看悬浮工作台',exact=True).click()
        assert len(context.pages)==2
        page.get_by_role('button',name='5秒后模拟新预约',exact=True).click()
        other=context.new_page();other.goto('about:blank');other.bring_to_front()
        expect(floating.locator('.floating-count strong')).to_have_text(str(before+1),timeout=12000)
        assert not floating.is_closed()
        assert '收到一条模拟新预约' in floating.locator('body').inner_text()
        floating.screenshot(path=str(ROOT/'clinic'/'floating-workbench.png'),full_page=True)
        page.screenshot(path=str(ROOT/'clinic'/'floating-launcher.png'),full_page=True)
        floating.get_by_role('button',name='去确认',exact=True).first.click()
        page.wait_for_selector('.arco-drawer')
        assert 'PIP-' in page.locator('.arco-drawer').inner_text()
        assert page.locator('.arco-table-tr').count()>0
        page.locator('.arco-drawer-close-icon').click()
        page.wait_for_selector('.arco-drawer',state='detached')
        floating.get_by_role('button',name='去确认',exact=True).first.click()
        page.wait_for_selector('.arco-drawer')
        page.locator('.arco-drawer').get_by_role('button',name='确认预约',exact=True).click()
        page.wait_for_selector('.arco-modal')
        page.locator('.arco-modal').get_by_role('button',name='确认预约',exact=True).click()
        page.wait_for_selector('.arco-modal',state='detached')
        expect(floating.locator('.floating-count strong')).to_have_text(str(before))
        # Drain remaining fictional tasks through existing confirmation, then verify empty state.
        for _ in range(before):
            floating.get_by_role('button',name='去确认',exact=True).first.click()
            page.locator('.arco-drawer').get_by_role('button',name='确认预约',exact=True).click()
            page.locator('.arco-modal').get_by_role('button',name='确认预约',exact=True).click()
            page.wait_for_selector('.arco-modal',state='detached')
        expect(floating.locator('.floating-count strong')).to_have_text('0')
        assert '暂无待确认预约' in floating.locator('body').inner_text()
        assert '收到一条模拟新预约' not in floating.locator('body').inner_text()
        before=0
        # Closing the view does not process the remaining appointments.
        floating.get_by_role('button',name='关闭悬浮窗',exact=True).click()
        expect(page.get_by_role('button',name='开启悬浮工作台',exact=True)).to_be_visible()
        with context.expect_page() as event:
            page.get_by_role('button',name='开启悬浮工作台',exact=True).click()
        floating=event.value
        expect(floating.locator('.floating-count strong')).to_have_text(str(before))
        page.get_by_role('button',name='5秒后模拟新预约',exact=True).click()
        page.get_by_role('button',name='取消延时模拟',exact=True).click()
        page.get_by_role('button',name='退出',exact=True).click()
        assert floating.is_closed() or page.wait_for_function('!documentPictureInPicture.window')
        print('real PiP, repeated opening, cross-tab delayed update, return/detail/confirm, close/reopen and logout passed',flush=True)
        for role in ['platform','resource','channel']:
            other.goto(BASE+'/'+role+'/')
            assert other.get_by_role('button',name='开启悬浮工作台',exact=True).count()==0
        # Capability and rejection failures must not create a fake in-page popup.
        for script,message in [("Object.defineProperty(window,'documentPictureInPicture',{value:undefined})",'当前环境不支持独立悬浮窗'),("Object.defineProperty(window,'documentPictureInPicture',{value:{requestWindow:()=>Promise.reject(new DOMException('Denied','NotAllowedError'))}})",'悬浮窗未能打开')]:
            test=context.new_page();test.add_init_script(script);test.goto(BASE+'/clinic/')
            test.get_by_role('button',name='开启悬浮工作台',exact=True).click()
            expect(test.locator('.floating-launcher')).to_contain_text(message)
            assert test.locator('.floating-content').count()==0
            test.close()
        page.goto(BASE+'/clinic/')
        with context.expect_page() as event:
            page.get_by_role('button',name='开启悬浮工作台',exact=True).click()
        floating=event.value
        floating.wait_for_selector('.floating-content')
        with floating.expect_event('close'):
            page.reload()
        page.wait_for_selector('.floating-launcher')
        assert floating.is_closed()
        page.set_viewport_size({'width':768,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print('role isolation, unsupported/rejected, refresh lifecycle, 768px and browser errors: 0',flush=True)
        browser.close()


if __name__=='__main__':
    verify()
