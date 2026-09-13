"""Synthetic snapshot UI checks, called only by the disposable server Web runner."""

import json

from playwright.sync_api import expect

from web_workflows import close, menu, read


def exercise(pages, report):
    channel, platform = pages['channel'], pages['platform']
    original = read(channel, '/api/v1/clinics')['results'][0]
    clinic_id = original['id']
    path = '/api/v1/clinics/' + clinic_id
    # Deliberate UI transport fixture, not a claim of real Tencent validation.
    picture = (report / 'synthetic-proof.png').read_bytes()
    requests = []

    def fake_map(route):
        requests.append(route.request.post_data_json)
        route.fulfill(status=200, content_type='image/png', body=picture)

    for page in [channel, platform]:
        page.route('**/profile-map', fake_map)

    def call(page, endpoint, data):
        return page.evaluate('([p, b]) => CHT.api(p, "POST", b)', [endpoint, data])

    def open_detail():
        close(channel)
        channel.evaluate('(id) => CHT.open("clinic", {id})', clinic_id)

    def submit(longitude):
        current = read(channel, path)
        profile = dict(current['profile'])
        profile['location'] = {
            'status': 'confirmed', 'confirmed': True, 'coordinate_system': 'GCJ-02',
            'longitude': longitude, 'latitude': '39.900000', 'source': 'map_manual',
            'address_snapshot': ''.join(profile.get(k, '') for k in ['province', 'city', 'district', 'address']),
        }
        return call(channel, path + '/profile-changes', {'profile': profile, 'version': current['version']})

    def review(change, approved):
        call(platform, '/api/v1/profile-changes/' + change['id'] + '/review', {
            'version': change['version'], 'approved': approved, 'reason': '合成地图版本回归',
        })

    try:
        menu(channel, '门诊管理')
        open_detail()
        expect(channel.get_by_text('当前生效资料尚无定位，请补充定位并提交审核。', exact=True)).to_be_visible()
        assert channel.locator('.saved-location').count() == 0
        close(channel)
        first = submit('116.300000')
        open_detail()
        expect(channel.get_by_text('新位置已确认，等待平台审核；当前生效资料尚无定位，暂不能准确按距离推荐。', exact=True)).to_be_visible()
        expect(channel.get_by_alt_text('本次申请位置腾讯地图')).to_be_visible()
        assert read(channel, path)['profile']['location']['status'] == 'unconfirmed'
        close(channel)
        review(first, False)
        open_detail()
        expect(channel.get_by_text('当前生效资料尚无定位，请补充定位并提交审核。', exact=True)).to_be_visible()
        close(channel)
        second = submit('116.300000')
        review(second, True)
        open_detail()
        expect(channel.get_by_alt_text('当前生效位置腾讯地图')).to_be_visible()
        close(channel)
        third = submit('116.400000')
        open_detail()
        expect(channel.get_by_text('新位置已确认，等待平台审核；当前仍使用原生效位置。', exact=True)).to_be_visible()
        expect(channel.locator('.saved-location img')).to_have_count(2)
        close(channel)
        platform.evaluate('([row, clinic]) => CHT.open("profileChange", {row, clinic})', [third, read(platform, path)])
        expect(platform.get_by_alt_text('原资料位置腾讯地图')).to_be_visible()
        expect(platform.get_by_alt_text('本次申请位置腾讯地图')).to_be_visible()
        assert any(r.get('snapshot') == 'before' and r.get('change_id') == third['id'] for r in requests)
        assert any(r.get('snapshot') == 'after' and r.get('change_id') == third['id'] for r in requests)
        platform.locator('.location-comparison').screenshot(path=str(report / 'map-comparison-synthetic.png'))
        platform.set_viewport_size({'width': 768, 'height': 1000})
        assert platform.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        panels = platform.locator('.location-comparison > *')
        assert panels.nth(1).bounding_box()['y'] > panels.nth(0).bounding_box()['y']
        platform.set_viewport_size({'width': 1440, 'height': 1000})
        close(platform)
        # Fail once, retry only on a user action; saved data remains unchanged.
        failed = {'once': True}

        def fail_once(route):
            if failed['once']:
                failed['once'] = False
                route.fulfill(status=503, content_type='application/json', body=json.dumps({'message': '合成地图加载失败', 'code': 'map_unavailable'}))
            else:
                fake_map(route)

        channel.unroute('**/profile-map', fake_map)
        channel.route('**/profile-map', fail_once)
        open_detail()
        expect(channel.get_by_text('合成地图加载失败', exact=True)).to_be_visible()
        channel.get_by_role('button', name='重新加载', exact=True).click()
        expect(channel.locator('.saved-location img')).to_have_count(2)
        assert read(channel, path)['profile']['location']['longitude'] == '116.300000'
        close(channel)
        review(third, False)
        (report / 'map-view-checks.json').write_text(json.dumps({'passed': True, 'synthetic_map_transport': True, 'pending_approved_rejected_states': True, 'snapshot_comparison': True, 'narrow_layout': True, 'failure_retry_preserves_data': True}))
    finally:
        close(channel)
        close(platform)
        channel.unroute('**/profile-map')
        platform.unroute('**/profile-map')
