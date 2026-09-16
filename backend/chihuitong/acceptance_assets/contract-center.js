(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C,
    base = '/api/v1/';
  Object.assign(C.names, {
    subject_name: '签约主体',
    debtor_name: '付款责任主体',
    content_status: '内容预审',
    payment_mode: '付款方式',
    error_code: '待核实问题',
  });
  Object.assign(C.labels, {
    instant: '核销现付',
    postpaid: '账单后付',
    paid: '已付款待核销',
    closed: '已关闭',
    single: '独立单店',
    chain: '连锁总部',
  });
  const multi = (name, label, items, optional = false) => ({
    name,
    label,
    optional,
    render: () => h(A.Select, { mode: 'multiple', options: items }),
  });
  const productOptions = (items) => items.map((x) => ({ value: x.id, label: x.internal_name }));
  const dates = [
    { name: 'starts_at', label: '合同生效时间', type: 'date', time: true },
    { name: 'ends_at', label: '合同到期时间', type: 'date', time: true },
  ];
  const subjectFields = [
    { name: 'subject_name', label: '法定签约主体全称' },
    { name: 'subject_credit', label: '统一社会信用代码（18位）' },
    { name: 'subject_admin', label: '签约主体管理员姓名' },
    { name: 'subject_phone', label: '签约主体管理员手机号' },
  ];
  const subjectData = (v, kind) => ({
    name: v.subject_name,
    credit_code: v.subject_credit,
    kind,
    admin_name: v.subject_admin,
    admin_phone: v.subject_phone,
  });
  C.jointFields = (products, existing) => [
    ...(!existing ? subjectFields : []),
    { name: 'contract_starts', label: '合同生效时间', type: 'date', time: true },
    { name: 'contract_ends', label: '合同到期时间', type: 'date', time: true },
    multi('contract_products', '申请上线的推广产品', productOptions(products)),
  ];
  C.jointData = (v, row) => ({
    ...(!row ? { subject: subjectData(v, 'single') } : {}),
    agreement: {
      number: v.contract_number || '',
      starts_at: v.contract_starts ? C.iso(v.contract_starts) : '',
      ends_at: v.contract_ends ? C.iso(v.contract_ends) : '',
      payment_mode: 'instant',
      settlement_cycle: '',
      clinic_ids: [],
      product_ids: v.contract_products,
      attachment_ids: [],
      contact: { name: v.business_contact, phone: v.business_phone },
    },
  });

  C.pages.contracts = function () {
    const [kind, setKind] = React.useState(
      C.role === 'resource' ? 'resource' : C.role === 'channel' ? 'channel' : 'clinic',
    );
    const kinds =
      C.role === 'resource'
        ? { resource: '客户资源方合同' }
        : C.role === 'channel'
          ? { clinic: '门诊合同', channel: '本机构与平台合同' }
          : C.role === 'clinic'
            ? { clinic: '门诊合同' }
            : {
                clinic: '门诊合同',
                resource: '客户资源方合同',
                channel: '门诊渠道合同',
              };
    return h(
      C.Panel,
      {
        title: '合同管理',
        extra:
          ((C.role === 'platform') ||
            (C.role === 'channel' && kind === 'clinic')) &&
          h(
            A.Button,
            {
              type: 'primary',
              onClick: () =>
                C.open(kind === 'clinic' ? 'agreementForm' : 'partnerContractStart', { kind }),
            },
            '新增合同',
          ),
      },
      h(
        A.Space,
        { className: 'detail-actions' },
        ['platform', 'channel'].includes(C.role) && C.button('待签合同草稿', () => C.open('preparations', {})),
        C.role === 'platform' && C.button('合同模板配置', () => C.open('contractTemplates', {})),
        h('span', null, '合同类型'),
        h(A.Select, {
          value: kind,
          onChange: setKind,
          options: C.options(kinds),
          style: { width: 240 },
        }),
      ),
      h(A.Alert, {
        type: 'info',
        content:
          kind === 'clinic'
            ? '单店在门店管理提交一份入驻申请，资料和合同一起审核；连锁先审总部合同再逐店上线。续签沿用主体，不重复建档。'
            : '合同及推广产品条款集中管理；合作方只读查看各自与平台的合同。',
      }),
      h(C.List, {
        key: kind,
        path: base + 'contracts?kind=' + kind,
        search: true,
        columns: [
          C.column('number', '合同编号'),
          C.column('subject_name', '签约主体'),
          C.column('revision', '版本'),
          C.column(kind === 'clinic' ? 'status' : 'display_status'),
          C.column('ends_at', '到期时间'),
        ],
        actions: (r) =>
          C.button('详情', () =>
            C.open(kind === 'clinic' ? 'agreement' : 'contract', {
              id: r.id,
              canManage: C.role === 'platform',
            }),
          ),
      }),
    );
  };
  C.dialogs.partnerContractStart = function ({ kind, onClose }) {
    const q = C.useChoices(base + 'organizations?status=active&page_size=100');
    return h(C.FormDialog, {
      title: '选择合同合作方',
      onClose,
      fields: [
        {
          name: 'organization_id',
          label: '合作机构',
          type: 'select',
          options: (q.data?.results || [])
            .filter((x) =>
              kind === 'channel'
                ? x.kind === 'channel'
                : ['bank', 'insurance', 'broker'].includes(x.kind),
            )
            .map((x) => ({ value: x.id, label: x.name })),
        },
      ],
      onSubmit: (v) => C.contractForm(v.organization_id),
    });
  };
  C.Agreements = function ({ id }) {
    const q = C.useChoices(base + 'clinic-cooperations/' + id);
    return h(
      C.Panel,
      { title: '签约主体与适用合同' },
      h(C.Error, { error: q.error, retry: q.reload }),
      q.data && h(A.Typography.Paragraph, null, q.data.name),
      C.button('前往合同管理', () => C.navigate('contracts')),
      h(C.List, {
        path: base + 'clinic-cooperations/' + id + '/agreements',
        columns: [C.column('number'), C.column('status'), C.column('ends_at')],
        actions: (r) =>
          C.button('查看合同', () => C.open('agreement', { id: r.id, readOnly: true })),
      }),
    );
  };
  C.dialogs.agreementForm = function ({ subject, row, preparation, onClose }) {
    const subjects = C.useChoices(base + 'clinic-cooperations?page_size=100'),
      stores = C.useChoices(base + 'clinics?page_size=100'),
      products = C.useChoices(base + 'contracts/products?page_size=100');
    const [selected, setSelected] = React.useState(subject?.id || preparation?.payload.cooperation_id || 'new'),
      [kind, setKind] = React.useState(subject?.kind || preparation?.kind || 'chain');
    const chosen = (subjects.data?.results || []).find((x) => x.id === selected),
      actualKind = chosen?.kind || kind;
    const fields = [
      ...(!row && !subject
        ? [
            {
              name: 'subject_choice',
              label: '签约主体',
              render: () =>
                h(A.Select, {
                  options: [
                    { value: 'new', label: '首次合作，填写新主体' },
                    ...(subjects.data?.results || [])
                      .filter((x) => x.can_manage)
                      .map((x) => ({ value: x.id, label: x.name })),
                  ],
                  onChange: setSelected,
                }),
            },
          ]
        : []),
      ...(selected === 'new'
        ? [
            {
              name: 'subject_kind',
              label: '合作类型',
              render: () =>
                h(A.Select, {
                  options: C.options({ chain: '连锁总部' }),
                  onChange: setKind,
                }),
            },
            ...subjectFields,
          ]
        : []),
      ...(row ? [{ name: 'number', label: '合同编号' }] : []),
      ...dates,
      { name: 'contact_name', label: '业务联系人' },
      { name: 'contact_phone', label: '业务联系人电话' },
      ...(actualKind === 'chain'
        ? [
            {
              name: 'settlement_cycle',
              label: '结算周期',
              type: 'select',
              options: C.options({ monthly: '月结', weekly: '周结' }),
            },
          ]
        : []),
      multi(
        'clinic_ids',
        '覆盖门店（草稿可暂不选）',
        (stores.data?.results || [])
          .filter(
            (x) =>
              x.cooperation_id === selected ||
              (!x.cooperation_id && x.contract_policy === 'bilateral'),
          )
          .map((x) => ({ value: x.id, label: x.profile.name })),
        true,
      ),
      multi('product_ids', '推广产品', productOptions(products.data?.results || [])),
      ...(row ? [{ name: 'attachment_ids', label: '门诊签署完整合同', type: 'files', purpose: 'contract' }] : []),
    ];
    return h(C.FormDialog, {
      title: row ? '修改合同草稿' : '新增合同 / 续签',
      onClose,
      fields: row ? fields : fields.map((f) => ({ ...f, optional: true })),
      submitText: row ? '保存' : '保存待签草稿',
      initial: {
        subject_choice: selected,
        subject_kind: kind,
        settlement_cycle: 'monthly',
        ...(preparation ? {
          ...preparation.payload.agreement,
          subject_name: preparation.payload.subject?.name,
          subject_credit: preparation.payload.subject?.credit_code,
          subject_admin: preparation.payload.subject?.admin_name,
          subject_phone: preparation.payload.subject?.admin_phone,
          contact_name: preparation.payload.agreement?.contact?.name,
          contact_phone: preparation.payload.agreement?.contact?.phone,
        } : {}),
        ...(row
          ? {
              ...row,
              clinic_ids: row.coverage.map((x) => x.id),
              contact_name: row.contact.name,
              contact_phone: row.contact.phone,
            }
          : {}),
      },
      hint: '先保存待签草稿，再生成下载、打印签署、上传照片并提交。合同编号由系统生成。单店请从门诊管理开通。',
      onSubmit: async (v, key) => {
        const data = {
          number: v.number,
          starts_at: v.starts_at ? C.iso(v.starts_at) : '',
          ends_at: v.ends_at ? C.iso(v.ends_at) : '',
          contact: { name: v.contact_name, phone: v.contact_phone },
          clinic_ids: v.clinic_ids || [],
          product_ids: v.product_ids,
          attachment_ids: v.attachment_ids || [],
          payment_mode: actualKind === 'chain' ? 'postpaid' : 'instant',
          settlement_cycle: actualKind === 'chain' ? v.settlement_cycle : '',
        };
        if (row) return C.api(base + 'clinic-agreements/' + row.id, 'POST', { version: row.version, data }, key);
        const saved = await C.api(base + 'contract-preparations' + (preparation ? '/' + preparation.id : ''), 'POST', {
          kind: actualKind, payload: { agreement: data, ...(selected === 'new' ? { subject: subjectData(v, actualKind) } : { cooperation_id: selected }) },
          ...(preparation ? { version: preparation.version } : {}),
        }, key);
        C.open('preparation', { id: saved.id });
        return saved;
      },
    });
  };
  function paper(r) {
    const fields =
      r.status === 'approved'
        ? [
            { name: 'return_carrier', label: '寄回快递公司' },
            { name: 'return_tracking', label: '寄回单号' },
            { name: 'returned_at', label: '寄回时间', type: 'date', time: true },
          ]
        : [
            { name: 'outbound_carrier', label: '寄往平台快递公司', optional: true },
            { name: 'outbound_tracking', label: '寄往平台单号', optional: true },
            { name: 'recipient', label: '门诊收件人', optional: true },
            { name: 'recipient_phone', label: '收件电话', optional: true },
            { name: 'return_address', label: '寄回地址', optional: true },
            ...(C.role === 'platform'
              ? [
                  { name: 'received_at', label: '平台收到原件时间', type: 'date', time: true },
                  { name: 'platform_signed_at', label: '平台签署时间', type: 'date', time: true },
                  {
                    name: 'signed_attachment_ids',
                    label: '双方签署完整合同',
                    type: 'files',
                    purpose: 'contract',
                  },
                ]
              : []),
          ];
    C.form({
      title: '纸质合同收签与寄回',
      fields,
      initial: { ...r.paper, signed_attachment_ids: r.signed_attachment_ids },
      onSubmit: (v, key) => {
        const data = {};
        for (const f of fields)
          if (v[f.name]) data[f.name] = f.type === 'date' ? C.iso(v[f.name]) : v[f.name];
        return C.api(
          base + 'clinic-agreements/' + r.id + '/paper',
          'POST',
          { version: r.version, data },
          key,
        );
      },
    });
  }
  C.dialogs.agreement = function ({ id, onClose, readOnly = false }) {
    const q = C.useChoices(base + 'clinic-agreements/' + id),
      r = q.data;
    const edit = r?.can_manage && !readOnly;
    function batchOnline() {
      C.form({
        title: '批量上线已审核门店',
        fields: [
          multi(
            'clinic_ids',
            '选择门店',
            r.coverage.map((x) => ({ value: x.id, label: x.name })),
          ),
          C.Reason,
        ],
        onSubmit: async (v, key) => {
          const result = await C.api(base + 'clinics/batch-online', 'POST', v, key);
          A.Modal.info({
            title: '逐店上线结果',
            content: h(
              'div',
              null,
              result.results.map((x) =>
                h(
                  'p',
                  { key: x.id },
                  (r.coverage.find((s) => s.id === x.id)?.name || x.id) +
                    '：' +
                    (x.status === 'online' ? '已上线' : x.message),
                ),
              ),
            ),
          });
          return result;
        },
      });
    }
    async function correct() {
      try {
        const row = await C.api(base + 'clinics/' + r.onboarding_clinic_id);
        C.open('clinicForm', { row, draft: r.onboarding_profile, joint: true, agreement: r });
      } catch (e) {
        A.Message.error(e.message);
      }
    }
    return h(
      C.Drawer,
      { title: r?.onboarding ? '单店入驻 · 联合审核' : '合同详情', onClose },
      h(C.Error, { error: q.error, retry: q.reload }),
      r &&
        h(
          React.Fragment,
          null,
          h(A.Alert, {
            type: 'info',
            content:
              r.scope_notice ||
              (r.onboarding
                ? '资料与合同一次审核。原件收到、平台签署及完整附件齐备后，才能审核通过并上线。'
                : '合同内容可先预审；收到原件并签署上传后才能最终生效。'),
          }),
          h(
            A.Space,
            { className: 'detail-actions', wrap: true },
            edit &&
              r.status === 'draft' &&
              C.button('修改草稿', () =>
                C.open('agreementForm', {
                  subject: {
                    id: r.cooperation_id,
                    kind: r.payment_mode === 'instant' ? 'single' : 'chain',
                  },
                  row: r,
                }),
              ),
            edit &&
              r.status === 'draft' &&
              C.button('提交审核', () =>
                C.action(
                  '提交合同审核',
                  base + 'clinic-agreements/' + id + '/submit',
                  r.version,
                  {},
                  [],
                ),
              ),
            edit &&
              (!r.onboarding || r.status === 'approved' || r.status === 'terminated') &&
              ['approved', 'rejected', 'terminated'].includes(r.status) &&
              C.button('登记续签 / 修订', () =>
                C.open('agreementForm', {
                  subject: {
                    id: r.cooperation_id,
                    kind: r.payment_mode === 'instant' ? 'single' : 'chain',
                  },
                }),
              ),
            edit && r.onboarding && r.status === 'rejected' && C.button('补正并重新提交', correct),
            edit &&
              ['draft', 'pending', 'approved'].includes(r.status) &&
              (r.status !== 'approved' || C.role === 'platform') &&
              C.button('原件收签 / 寄回', () => paper(r)),
            edit &&
              C.role === 'platform' &&
              r.status === 'pending' &&
              C.button(r.onboarding ? '审核入驻申请' : '审核合同', () =>
                C.action(
                  r.onboarding ? '统一审核门诊资料与合同' : '审核合同',
                  base +
                    'clinic-agreements/' +
                    id +
                    (r.onboarding ? '/onboarding-review' : '/review'),
                  r.version,
                  { approved: true, final: false },
                  [
                    { name: 'approved', label: '审核通过', type: 'boolean' },
                    {
                      name: 'final',
                      label: r.onboarding ? '完成最终审核并上线' : '完成最终审核并生效',
                      type: 'boolean',
                    },
                    C.Reason,
                  ],
                ),
              ),
            edit &&
              C.role === 'platform' &&
              r.status === 'approved' &&
              !r.onboarding &&
              C.button('批量上线门店', batchOnline),
            edit &&
              C.role === 'platform' &&
              r.status === 'approved' &&
              C.button('终止合同', () =>
                C.action(
                  '终止合同',
                  base + 'clinic-agreements/' + id + '/terminate',
                  r.version,
                  {},
                  [C.Reason],
                ),
              ),
          ),
          h(C.Facts, {
            data: r,
            fields: [
              'subject_name',
              'number',
              'revision',
              'status',
              'payment_mode',
              'starts_at',
              'ends_at',
              'settlement_cycle',
              'due_at',
              'reason',
            ],
          }),
          r.onboarding_profile &&
            h(
              C.Panel,
              { title: '门诊资料与资质' },
              h(C.ProfileView, {
                profile: r.onboarding_profile,
                clinicId: r.onboarding_clinic_id,
                changeId: r.onboarding_change_id,
                context: 'after',
                reviewStatus: r.status,
              }),
            ),
          h(
            C.Panel,
            { title: '合同推广产品' },
            h(
              A.Space,
              { wrap: true },
              (r.products || []).map((x) => h(A.Tag, { key: x.id }, x.internal_name)),
            ),
          ),
          h(
            C.Panel,
            { title: '覆盖门店' },
            h(
              A.Space,
              { wrap: true },
              r.coverage.map((x) => h(A.Tag, { key: x.id }, x.name)),
            ),
          ),
          h(C.Panel, { title: '门诊签署件' }, h(C.Attachments, { ids: r.attachment_ids })),
          r.generated_attachment_ids?.length > 0 && h(C.Panel, { title: '系统生成的待签合同（核对用）' }, h(C.Attachments, { ids: r.generated_attachment_ids })),
          h(
            C.Panel,
            { title: '双方最终签署件' },
            h(C.Attachments, { ids: r.signed_attachment_ids }),
          ),
          r.can_manage && h(C.Panel, { title: '原件流转记录' }, h(C.Facts, { data: r.paper })),
          r.can_manage && h(C.Logs, { type: 'clinicagreement', id }),
        ),
    );
  };
  C.pages.instantOrders = () =>
    h(
      C.Panel,
      { title: '核销现付订单' },
      h(A.Alert, {
        type: 'info',
        content:
          '付款成功后才完成核销。结果未决先查单；已收款待核销可重试，不重新收费。本期不提供错误核销退款。',
      }),
      h(C.List, {
        path: base + 'instant-orders',
        columns: [
          C.column('clinic_name'),
          C.column('internal_name'),
          C.column('amount_cents', '获客费'),
          C.column('status'),
          C.column('paid_at'),
        ],
        actions: (r) => C.button('详情 / 支付处理', () => C.open('instant', { id: r.id })),
      }),
    );
  C.dialogs.instant = function ({ id, onClose }) {
    const q = C.useChoices(base + 'instant-orders/' + id),
      r = q.data;
    return h(
      C.Drawer,
      { title: '核销现付订单', onClose, width: 760 },
      h(C.Error, { error: q.error, retry: q.reload }),
      r &&
        h(
          React.Fragment,
          null,
          h(C.Facts, {
            data: r,
            fields: [
              'clinic_name',
              'debtor_name',
              'internal_name',
              'amount_cents',
              'status',
              'paid_at',
              'error_code',
            ],
          }),
          h(A.Alert, {
            type: 'warning',
            content:
              '付款责任属于合同签约主体，前台可用工作手机付款。已核销现付订单本期不能撤销或退款。',
          }),
          r.status === 'paid' &&
            ['platform', 'clinic'].includes(C.role) &&
            C.button('重试完成核销', () =>
              C.form({
                title: '重试完成核销',
                fields: [],
                onSubmit: () => C.api(base + 'instant-orders/' + id, 'POST', { confirmed: true }),
              }),
            ),
          ...(r.payments || []).map((p) =>
            h(
              C.Panel,
              { key: p.id, title: '支付记录' },
              p.simulated &&
                h(A.Alert, { type: 'warning', content: '模拟验收交易，不发生真实资金往来。' }),
              h(C.Facts, { data: p, fields: ['number', 'amount_cents', 'status', 'error_code'] }),
              p.payment_parameters?.code_url && !p.simulated && h(C.PaymentQr, { id: p.id }),
              ['platform', 'clinic'].includes(C.role) &&
                ['query', 'close', 'retry'].map((action) =>
                  C.button(
                    {
                      query: '查询付款结果',
                      close: '查单并关闭未付订单',
                      retry: '重试生成支付信息',
                    }[action],
                    () =>
                      C.form({
                        title: '核对支付结果',
                        fields: [],
                        onSubmit: () =>
                          C.api(base + 'payments/' + p.id + '/' + action, 'POST', {
                            confirmed: true,
                          }),
                      }),
                  ),
                ),
            ),
          ),
          h(C.Logs, { type: 'instantredemptionorder', id }),
        ),
    );
  };
  C.PaymentQr = function ({ id }) {
    const [url, setUrl] = React.useState(null),
      [error, setError] = React.useState(null);
    React.useEffect(() => {
      let live = true,
        local;
      C.request(base + 'payments/' + id + '/qr', { binary: true })
        .then((blob) => {
          local = URL.createObjectURL(blob);
          if (live) setUrl(local);
          else URL.revokeObjectURL(local);
        })
        .catch((e) => {
          if (live) setError(e);
        });
      return () => {
        live = false;
        if (local) URL.revokeObjectURL(local);
      };
    }, [id]);
    return h(
      'div',
      null,
      h(C.Error, { error }),
      url && h('img', { src: url, alt: '微信付款二维码', width: 240, height: 240 }),
    );
  };
})();
