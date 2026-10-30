"""Server browser regression: single submission and atomic joint activation."""

import json
import subprocess
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
            '经营地址':'合成测试路8号',
            '前台预约手机号':'13800000691', '业务联系人':'合成联系人', '业务联系人电话':'13800000692',
            '法定签约主体全称':'联合入驻合成主体', '统一社会信用代码':'91110000123456789A',
            '签约主体管理员姓名':'合成主体管理员', '签约主体管理员手机号':'13800000693',
            '门诊管理员姓名':'合成门店管理员', '门诊管理员手机号':'13800000694',
        }
        for label, value in values.items():
            fill(channel,label,value)
        select(channel, '省 / 直辖市', '北京市')
        channel.wait_for_timeout(350)
        select(channel, '城市', '北京市')
        channel.wait_for_timeout(350)
        select(channel, '区 / 县', '海淀区')
        for index, value in enumerate(('09:00', '18:00')):
            time_input = field(channel, '营业时间').locator('input').nth(index)
            time_input.fill(value)
            time_input.press('Enter')
        field(channel, '签约主体管理员姓名').get_by_role('button', name='与业务联系人相同').click()
        field(channel, '门诊管理员姓名').get_by_role('button', name='与业务联系人相同').click()
        for label in ['签约主体管理员姓名', '门诊管理员姓名']:
            assert field(channel, label).locator('input').input_value() == '合成联系人'
        for label in ['签约主体管理员手机号', '门诊管理员手机号']:
            assert field(channel, label).locator('input').input_value() == '13800000692'
        fill(channel, '业务联系人电话', '010-88888888')
        field(channel, '门诊管理员姓名').get_by_role('button', name='与业务联系人相同').click()
        assert field(channel, '门诊管理员手机号').locator('input').input_value() == '13800000692'
        fill(channel, '业务联系人电话', values['业务联系人电话'])
        for label in ['签约主体管理员姓名', '签约主体管理员手机号', '门诊管理员姓名', '门诊管理员手机号']:
            fill(channel, label, values[label])
        date_field(channel,'合同期限',(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d'))
        select(channel,'合同期限','1年')
        select(channel,'申请上线的推广产品','演示·洁牙推广产品')
        dialog(channel).get_by_text('合同期限',exact=True).click()
        for label in ['营业执照','医疗执业许可证']:
            with channel.expect_response(lambda r:r.url.endswith('/api/v1/files') and r.request.method=='POST') as response:
                field(channel,label).locator('input[type=file]').set_input_files(report/'synthetic-proof.png')
            assert response.value.status==201
            field(channel,label).get_by_role('button',name='查看附件 1',exact=True).wait_for()
        channel.screenshot(path=str(report/'joint-submission.png'),full_page=True)
        with channel.expect_response(lambda r:r.url.endswith('/api/v1/contract-preparations') and r.request.method=='POST') as response:
            dialog(channel).get_by_role('button',name='保存待签草稿',exact=True).click()
        assert response.value.status==201, response.value.text()
        result=response.value.json()
        draft=result.get('data',result)
        close(channel)
        # Missing real template must fail closed; synthetic template only in this disposable DB.
        menu(platform,'合同管理')
        platform.get_by_role('button',name='合同模板配置',exact=True).click()
        platform.get_by_role('button',name='配置合同收款及开票信息',exact=True).click()
        config_modal = platform.locator('.arco-modal:visible').last
        for label, value in [('收款主体', '合成收款主体'), ('收款信息', '合成收款方式'), ('开票安排', '合成开票说明')]:
            config_modal.locator('.arco-form-item').filter(has=platform.locator('.arco-form-label-item', has_text=label)).locator('input,textarea').first.fill(value)
        with platform.expect_response(lambda r:r.url.endswith('/contract-financial-profile') and r.request.method=='POST') as response:
            config_modal.get_by_role('button',name='保存',exact=True).click()
        assert response.value.status == 201, response.value.text()
        platform.get_by_role('button',name='发布新模板版本',exact=True).click()
        select(platform,'适用类型','单店现付')
        fill(platform,'合同标题','自动测试合成合同（禁止实际签署）')
        fill(platform,'平台法定签约名称','合成平台主体')
        fill(platform,'平台统一社会信用代码','91110000123456789B')
        fill(platform,'认可的完整合同正文','合同编号：{{number}}\n甲方：{{platform_name}}\n乙方：{{subject_name}}\n门店：{{stores}}\n产品：{{products}}\n期限：{{starts_at}}至{{ends_at}}\n付款方式：{{payment_mode}}\n生成日期：{{contract_date}}\n收款：{{receiving_name}} {{receiving_info}}\n税费：{{tax_terms}}\n开票：{{invoice_terms}}\n本文件仅为自动测试。\n甲方盖章：________\n乙方签字：________')
        select(platform,'确认范本已获平台认可，可用于实际签署','是')
        with platform.expect_response(lambda r:r.url.endswith('/contract-templates') and r.request.method=='POST') as response:
            dialog(platform).get_by_role('button',name='保存',exact=True).click()
        assert response.value.status==201
        close(platform)
        channel.get_by_role('button',name='待签合同草稿',exact=True).click()
        channel.get_by_role('button',name='继续办理',exact=True).first.click()
        channel.get_by_role('button',name='生成待签合同',exact=True).click()
        with channel.expect_response(lambda r:r.url.endswith('/generate') and r.request.method=='POST') as response:
            dialog(channel).get_by_role('button',name='保存',exact=True).click()
        assert response.value.status==200, response.value.text()
        channel.wait_for_timeout(400)
        with channel.expect_download() as download:
            channel.get_by_role('button',name='下载打印合同',exact=True).click()
        download.value.save_as(report/'generated-contract.pdf')
        pdf_text = ''.join(subprocess.check_output(['pdftotext', str(report/'generated-contract.pdf'), '-'], text=True).split())
        assert '合成收款主体' in pdf_text and '合成开票说明' in pdf_text and '费用含税' in pdf_text
        channel.get_by_role('button',name='上传门诊签署件',exact=True).click()
        with channel.expect_response(lambda r:r.url.endswith('/api/v1/files') and r.request.method=='POST') as response:
            field(channel,'签署照片 / 扫描件').locator('input[type=file]').set_input_files(report/'synthetic-proof.png')
        assert response.value.status==201
        field(channel,'签署照片 / 扫描件').get_by_role('button',name='查看附件 1',exact=True).wait_for()
        with channel.expect_response(lambda r:r.url.endswith('/sign') and r.request.method=='POST') as response:
            dialog(channel).get_by_role('button',name='保存',exact=True).click()
        assert response.value.status==200
        channel.wait_for_timeout(400)
        channel.get_by_role('button',name='提交审核',exact=True).click()
        with channel.expect_response(lambda r:r.url.endswith('/submit') and r.request.method=='POST') as response:
            dialog(channel).get_by_role('button',name='保存',exact=True).click()
        assert response.value.status==200, response.value.text()
        submitted=response.value.json()
        item=read(platform,'/api/v1/clinic-agreements/'+submitted['agreement_id'])
        close(channel)
        clinic_id=item['onboarding_clinic_id']
        assert read(channel,'/api/v1/clinics/'+clinic_id)['service_status']!='online'
        menu(platform,'合同管理')
        platform.locator('.workspace').get_by_role('button',name='刷新',exact=True).click()
        platform.locator('.workspace .arco-table-tr').filter(has_text=draft['number']).get_by_role('button',name='详情',exact=True).click()
        dialog(platform).get_by_text('门诊资料与资质',exact=True).wait_for()
        dialog(platform).get_by_text('合同推广产品',exact=True).wait_for()
        dialog(platform).get_by_text('演示·洁牙推广产品',exact=True).wait_for()
        assert dialog(platform).get_by_role('button',name='查看附件 1',exact=True).count()>=3
        platform.get_by_role('button',name='审核入驻申请',exact=True).click()
        dialog(platform).get_by_text('当前不能同步上线：请先登记原件收件及平台签署时间', exact=False).wait_for()
        assert field(platform, '同步上线').locator('input[type=checkbox]').is_disabled()
        dialog(platform).get_by_role('button',name='取消',exact=True).click()
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
        dialog(platform).get_by_text('已通过上线条件检查', exact=False).wait_for()
        select(platform, '审核结果', '退回')
        assert field(platform, '同步上线').locator('input[type=checkbox]').is_disabled()
        select(platform, '审核结果', '审核通过')
        field(platform,'同步上线').get_by_text('门诊同步上线',exact=True).click()
        fill(platform,'操作原因','合成合同与资料完整，一次审核上线')
        dialog(platform).get_by_role('button',name='提交审核',exact=True).click()
        platform.wait_for_timeout(500)
        store=read(platform,'/api/v1/clinics/'+clinic_id)
        assert (store['review_status'],store['service_status'])==('approved','online')
        assert read(platform,'/api/v1/clinic-agreements/'+item['id'])['status']=='approved'
        platform.screenshot(path=str(report/'joint-approved.png'),full_page=True)
        close(platform)
        menu(channel, '合同管理')
        channel.locator('.detail-actions .arco-select').first.click()
        channel.locator('.arco-select-popup:visible .arco-select-option').filter(has_text='门诊合同').last.click()
        channel.get_by_role('button', name='新增合同', exact=True).click()
        for label, value in {
            '法定签约主体全称': '合成连锁主体',
            '统一社会信用代码': '91110000123456789B',
            '签约主体管理员姓名': '合成管理员',
            '签约主体管理员手机号': '13800000695',
            '业务联系人': '合成联系人',
            '业务联系人电话': '13800000695',
        }.items():
            fill(channel, label, value)
        date_field(channel, '合同期限', (datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d'))
        select(channel, '合同期限', '1年')
        select(channel, '推广产品', '演示·洁牙推广产品')
        with channel.expect_response(lambda r:r.url.endswith('/api/v1/contract-preparations') and r.request.method=='POST') as response:
            dialog(channel).get_by_role('button',name='保存待签草稿',exact=True).click()
        assert response.value.status == 201, response.value.text()
        chain = response.value.json()
        chain = chain.get('data', chain)
        assert chain['payload']['term']['years'] == 1
        close(channel)
        (report/'joint-contract.json').write_text(json.dumps({'passed':True,'clinic_id':clinic_id,'agreement_id':item['id']},indent=2))
    except Exception:
        platform.screenshot(path=str(report/'joint-platform-failure.png'),full_page=True)
        channel.screenshot(path=str(report/'joint-channel-failure.png'),full_page=True)
        raise
