"""Real Document Picture-in-Picture in server Chromium under Xvfb, no browser API stubs."""

from web_workflows import menu, dialog, close, read


def exercise_reminder(page, fixture, report):
    menu(page, '工作台')
    page.wait_for_function('!!window.documentPictureInPicture?.window')
    pip = next(item for item in page.context.pages if item != page)
    page.context.new_cdp_session(pip).send('Emulation.clearDeviceMetricsOverride')
    pip.get_by_text('暂无待处理预约', exact=True).wait_for(timeout=15000)
    compact_height = pip.evaluate('innerHeight')
    (report/'reminder-dimensions.json').write_text(__import__('json').dumps({'compact':pip.evaluate('({width:innerWidth,height:innerHeight,outerWidth,outerHeight})')}))
    created = fixture()
    pip.get_by_text('有 1 条新预约', exact=True).wait_for(timeout=20000)
    pip.get_by_role('button', name='展开', exact=True).click()
    page.wait_for_timeout(500)
    (report/'reminder-dimensions.json').write_text(__import__('json').dumps({'compact_height':compact_height, 'expanded':pip.evaluate('({width:innerWidth,height:innerHeight,outerWidth,outerHeight})'), 'text':pip.locator('body').inner_text()}))
    pip.wait_for_function('innerHeight > '+str(compact_height))
    pip.get_by_role('button', name='去处理', exact=True).click()
    page.get_by_role('button', name='确认预约', exact=True).click()
    dialog(page).get_by_role('button', name='确认预约', exact=True).click()
    pip.get_by_text('暂无待处理预约', exact=True).wait_for(timeout=15000)
    assert read(page, '/api/v1/appointments/'+created['appointment_id'])['status'] == 'success'
    close(page)
    pip.get_by_role('button', name='收起', exact=True).click()
    pip.wait_for_function('innerHeight <= '+str(compact_height))
    assert not pip.is_closed()
    pip.screenshot(path=str(report/'clinic-pip-compact.png'))
    pip.close()
    menu(page, '工作台')
    page.get_by_text('提醒小窗未开启', exact=True).wait_for()
    fixture()
    page.wait_for_timeout(6000)
    assert len(page.context.pages) == 1
    with page.context.expect_page() as opened:
        page.get_by_role('button', name='开启预约提醒', exact=True).click()
    resumed = opened.value
    page.context.new_cdp_session(resumed).send('Emulation.clearDeviceMetricsOverride')
    resumed.get_by_text('有 1 条预约待确认', exact=True).wait_for(timeout=15000)
    resumed.get_by_role('button', name='展开', exact=True).click()
    resumed.screenshot(path=str(report/'clinic-pip-expanded.png'))
    (report/'reminder.txt').write_text('Real browser API: login auto-open, empty compact, new event, expand, process, collapse, manual close, no unsolicited reopen, manual resume passed.\n')
