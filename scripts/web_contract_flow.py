"""Server browser regression: single submission and atomic joint activation."""

import json
from datetime import datetime, timedelta

from web_workflows import close, date_field, dialog, field, fill, menu, read, select


def exercise(pages, report):
    channel, platform = pages['channel'], pages['platform']
    try:
        close(channel)
        close(platform)
        menu(channel, '门诊管理')
        channel.get_by_role('button', name='单店入驻申请', exact=True).click()
        values = {
            '门诊名称':'联合入驻合成门诊', '经营主体':'联合入驻合成主体',
            '省 / 直辖市':'北京市', '城市':'北京市', '区 / 县':'海淀区',
            '经营地址':'合成测试路8号', '营业时间':'09:00-18:00',
            '前台预约手机号':'13800000691', '业务联系人':'合成联系人', '业务联系人电话':'13800000692',
            '法定签约主体全称':'联合入驻合成主体', '统一社会信用代码':'91110000123456789A',
            '签约主体管理员姓名':'合成主体管理员', '签约主体管理员手机号':'13800000693',
            '合同编号':'WEB-JOINT-001', '门诊管理员姓名':'合成门店管理员', '门诊管理员手机号':'13800000694',
        }
        for label, value in values.items():
            fill(channel,label,value)
        date_field(channel,'合同生效时间',(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d %H:%M'))
        date_field(channel,'合同到期时间',(datetime.now()+timedelta(days=365)).strftime('%Y-%m-%d %H:%M'))
        select(channel,'申请上线的推广产品','演示·洁牙推广产品')
        dialog(channel).get_by_text('合同编号',exact=True).click()
        for label in ['门诊已签署的完整合同','营业执照','医疗执业许可证']:
            with channel.expect_response(lambda r:r.url.endswith('/api/v1/files') and r.request.method=='POST') as response:
                field(channel,label).locator('input[type=file]').set_input_files(report/'synthetic-proof.png')
            assert response.value.status==201
            field(channel,label).get_by_role('button',name='查看附件 1',exact=True).wait_for()
        channel.screenshot(path=str(report/'joint-submission.png'),full_page=True)
        with channel.expect_response(lambda r:r.url.endswith('/api/v1/clinic-onboarding')) as response:
            dialog(channel).get_by_role('button',name='统一提交入驻审核',exact=True).click()
        assert response.value.status==201, response.value.text()
        result=response.value.json()
        item=result.get('data',result)
        close(channel)
        clinic_id=item['onboarding_clinic_id']
        assert read(channel,'/api/v1/clinics/'+clinic_id)['service_status']!='online'
        menu(platform,'合同管理')
        platform.locator('.workspace .arco-table-tr').filter(has_text='WEB-JOINT-001').get_by_role('button',name='详情',exact=True).click()
        dialog(platform).get_by_text('门诊资料与资质',exact=True).wait_for()
        dialog(platform).get_by_text('合同推广产品',exact=True).wait_for()
        dialog(platform).get_by_text('演示·洁牙推广产品',exact=True).wait_for()
        assert dialog(platform).get_by_role('button',name='查看附件 1',exact=True).count()>=3
        platform.get_by_role('button',name='审核入驻申请',exact=True).click()
        fill(platform,'操作原因','合成资料内容预审通过')
        dialog(platform).get_by_role('button',name='保存',exact=True).click()
        platform.wait_for_timeout(350)
        assert read(platform,'/api/v1/clinic-agreements/'+item['id'])['status']=='pending'
        platform.get_by_role('button',name='原件收签 / 寄回',exact=True).click()
        stamp=(datetime.now()-timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')
        date_field(platform,'平台收到原件时间',stamp)
        date_field(platform,'平台签署时间',stamp)
        with platform.expect_response(lambda r:r.url.endswith('/api/v1/files') and r.request.method=='POST') as response:
            field(platform,'双方签署完整合同').locator('input[type=file]').set_input_files(report/'synthetic-proof.png')
        assert response.value.status==201
        field(platform,'双方签署完整合同').get_by_role('button',name='查看附件 1',exact=True).wait_for()
        dialog(platform).get_by_role('button',name='保存',exact=True).click()
        platform.wait_for_timeout(350)
        platform.get_by_role('button',name='审核入驻申请',exact=True).click()
        select(platform,'完成最终审核并上线','是')
        fill(platform,'操作原因','合成合同与资料完整，一次审核上线')
        dialog(platform).get_by_role('button',name='保存',exact=True).click()
        platform.wait_for_timeout(500)
        store=read(platform,'/api/v1/clinics/'+clinic_id)
        assert (store['review_status'],store['service_status'])==('approved','online')
        assert read(platform,'/api/v1/clinic-agreements/'+item['id'])['status']=='approved'
        platform.screenshot(path=str(report/'joint-approved.png'),full_page=True)
        close(platform)
        (report/'joint-contract.json').write_text(json.dumps({'passed':True,'clinic_id':clinic_id,'agreement_id':item['id']},indent=2))
    except Exception:
        platform.screenshot(path=str(report/'joint-platform-failure.png'),full_page=True)
        channel.screenshot(path=str(report/'joint-channel-failure.png'),full_page=True)
        raise
