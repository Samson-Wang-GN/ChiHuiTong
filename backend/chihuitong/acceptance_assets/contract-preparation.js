(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C,
    base = '/api/v1/';
  Object.assign(C.names, {
    generation: '生成版本',
    signed_generation: '签署件对应版本',
    kind: '合作类型',
    title: '模板名称',
  });
  Object.assign(C.labels, { submitted: '已提交审核', retired: '已被替代' });
  C.dialogs.preparations = ({ onClose }) =>
    h(
      C.Drawer,
      { title: '待签合同草稿', onClose },
      h(A.Alert, {
        type: 'info',
        content:
          '先完善合同项并生成下载，打印签署后上传照片，再提交审核。没有正式模板时仍可保存草稿。',
      }),
      h(C.List, {
        path: base + 'contract-preparations',
        columns: [
          C.column('number', '合同编号'),
          C.column('kind'),
          C.column('status'),
          C.column('generation'),
        ],
        actions: (r) => C.button('继续办理', () => C.open('preparation', { id: r.id })),
      }),
    );
  C.dialogs.preparation = function ({ id, onClose }) {
    const q = C.useChoices(base + 'contract-preparations/' + id),
      r = q.data;
    async function edit() {
      try {
        if (!r.payload.clinic) return C.open('agreementForm', { preparation: r });
        const row = r.payload.clinic_id
          ? await C.api(base + 'clinics/' + r.payload.clinic_id)
          : null;
        C.open('clinicForm', { joint: true, row, preparation: r });
      } catch (e) {
        A.Message.error(e.message);
      }
    }
    return h(
      C.Drawer,
      { title: '合同生成与签署', onClose },
      h(C.Error, { error: q.error, retry: q.reload }),
      r &&
        h(
          React.Fragment,
          null,
          h(A.Alert, {
            type: r.status === 'submitted' ? 'success' : 'info',
            content:
              r.status === 'submitted'
                ? '资料及签署件已提交，等待平台审核。'
                : '填写资料 → 生成并下载 → 打印签署 → 上传照片 → 提交审核。正式模板由平台配置；修改合同正文后必须重新生成并签署。',
          }),
          h(C.Facts, {
            data: r,
            fields: ['number', 'kind', 'status', 'generation', 'signed_generation'],
          }),
          r.print_changed && h(A.Alert, { type: 'warning', content: '资料中的合同内容已修改，原待签版仅供留档。请重新生成、打印并签署后再提交。' }),
          h(
            A.Space,
            { wrap: true, className: 'detail-actions' },
            r.status === 'draft' && C.button('完善 / 修改资料', edit),
            r.status === 'draft' &&
              C.button('生成待签合同', () =>
                C.action(
                  '生成待签合同',
                  base + 'contract-preparations/' + id + '/generate',
                  r.version,
                  {},
                  [],
                ),
              ),
            r.generated_file_id && !r.print_changed &&
              C.button('下载打印合同', () =>
                C.download(
                  base + 'files/' + r.generated_file_id,
                  r.number + '-v' + r.generation + '.pdf',
                ),
              ),
            r.status === 'draft' &&
              !r.print_changed &&
              r.generation > 0 &&
              C.button('上传门诊签署件', () =>
                C.form({
                  title: '上传门诊签署的完整合同',
                  hint: '请上传本生成版本的全部签署页；系统生成的未签署文件不能代替照片。',
                  fields: [
                    {
                      name: 'attachment_ids',
                      label: '签署照片 / 扫描件',
                      type: 'files',
                      purpose: 'contract',
                    },
                  ],
                  onSubmit: (v, key) =>
                    C.api(
                      base + 'contract-preparations/' + id + '/sign',
                      'POST',
                      { ...v, version: r.version, generation: r.generation },
                      key,
                    ),
                }),
              ),
            r.status === 'draft' &&
              C.button('提交审核', () =>
                C.action(
                  '提交门诊资料及合同审核',
                  base + 'contract-preparations/' + id + '/submit',
                  r.version,
                  {},
                  [],
                ),
              ),
            r.agreement_id &&
              C.button('查看审核进度', () => C.open('agreement', { id: r.agreement_id })),
          ),
          r.generated_file_id &&
            h(
              C.Panel,
              { title: r.print_changed ? '原生成版（仅供留档，请勿签署）' : '系统生成待签版' },
              h(C.Attachments, { ids: [r.generated_file_id] }),
            ),
          r.signed_ids.length > 0 &&
            h(
              C.Panel,
              {
                title:
                  r.signed_generation === r.generation && r.signed_generation > 0
                    ? '当前版签署件'
                    : '原签署件（内容已修改，请重新生成并签署）',
              },
              h(C.Attachments, { ids: r.signed_ids }),
            ),
          h(C.Logs, { type: 'contractpreparation', id }),
        ),
    );
  };
  function templateForm(row = {}) {
    C.form({
      title: '发布正式合同模板',
      initial: row,
      hint: '仅填写已获平台认可的正文。占位符示例：{{number}}、{{platform_name}}、{{subject_name}}；还支持platform_credit_code、subject_credit_code、starts_at、ends_at、payment_mode、settlement_cycle、products、stores、contact_name、contact_phone。签字/盖章位置应写入正文。发布新版本不改写已经生成的合同。',
      fields: [
        {
          name: 'kind',
          label: '适用类型',
          type: 'select',
          options: C.options({ single: '单店现付', chain: '连锁后付' }),
        },
        { name: 'title', label: '合同标题' },
        { name: 'platform_name', label: '平台法定签约名称' },
        { name: 'platform_credit_code', label: '平台统一社会信用代码' },
        { name: 'body', label: '认可的完整合同正文', type: 'textarea', max: 30000 },
        { name: 'confirmed', label: '确认范本已获平台认可，可用于实际签署', type: 'boolean' },
      ],
      onSubmit: (v, key) => C.api(base + 'contract-templates', 'POST', v, key),
    });
  }
  C.dialogs.contractTemplates = ({ onClose }) =>
    h(
      C.Drawer,
      { title: '合同模板配置', onClose },
      h(A.Alert, {
        type: 'warning',
        content: '尚无默认合同正文。请先取得认可的正式范本再发布；不要将测试内容用于实际签署。',
      }),
      C.button('发布新模板版本', () => templateForm()),
      h(C.List, {
        path: base + 'contract-templates',
        columns: [C.column('title'), C.column('kind'), C.column('status'), C.column('created_at')],
        actions: (r) => C.button('查看 / 另存新版本', () => templateForm(r)),
      }),
    );
})();
