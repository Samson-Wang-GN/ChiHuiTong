(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C;
  const base = '/api/v1/';
  const enums = (values) => values.map((value) => ({ value, label: C.label(value) }));
  const productFields = [
    { name: 'internal_name' },
    { name: 'external_name' },
    { name: 'product_type', type: 'select', options: enums(['service', 'deduction', 'discount']) },
    { name: 'usage_rules', type: 'textarea' },
    { name: 'redemption_units', type: 'number', min: 1 },
    { name: 'fee', label: '单次获客费（元）', type: 'number', precision: 2 },
    { name: 'validity_days', type: 'number', min: 1, max: 36500 },
    { name: 'status', type: 'select', options: enums(['active', 'disabled']) },
  ];
  function editProduct(row) {
    C.form({
      title: row ? '修改推广产品' : '新建推广产品',
      fields: row ? [...productFields, C.Reason] : productFields,
      initial: row
        ? { ...row, fee: row.fee_cents / 100 }
        : {
            product_type: 'service',
            redemption_units: 1,
            fee: 60,
            validity_days: 180,
            status: 'active',
          },
      hint: '后台以内部名称为主，患者及门诊小程序展示外部名称。获客费与分配规则在核销时锁定，历史交易不重算。',
      onSubmit: (v) => {
        const { fee, reason, ...product } = v;
        product.fee_cents = Math.round(fee * 100);
        return C.api(
          base + 'products' + (row ? '/' + row.id : ''),
          'POST',
          row ? { product, reason, version: row.version } : product,
        );
      },
    });
  }
  C.pages.products = () =>
    h(
      C.Panel,
      {
        title: '推广产品',
        extra: h(A.Button, { type: 'primary', onClick: () => editProduct() }, '新建推广产品'),
      },
      h(C.List, {
        path: base + 'products',
        search: true,
        columns: [
          'internal_name',
          'external_name',
          'product_type',
          'redemption_units',
          'fee_cents',
          'validity_days',
          'status',
        ].map((k) => C.column(k)),
        actions: (r) => [
          C.button('详情', () => C.open('product', { row: r })),
          C.button('修改', () => editProduct(r)),
        ],
      }),
    );
  C.dialogs.product = ({ row, onClose }) =>
    h(
      C.Drawer,
      { title: row.internal_name + ' · 推广产品', onClose },
      h(
        A.Tabs,
        { defaultActiveTab: 'info' },
        h(A.Tabs.TabPane, { key: 'info', title: '产品资料' }, h(C.Facts, { data: row })),
        h(
          A.Tabs.TabPane,
          { key: 'logs', title: '操作记录' },
          h(C.Logs, { type: 'product', id: row.id }),
        ),
      ),
    );
  const organizationFields = [
    { name: 'name', label: '机构名称' },
    { name: 'kind', type: 'select', options: enums(['insurance', 'bank', 'broker', 'channel']) },
    { name: 'contact_name' },
    { name: 'contact_phone' },
    { name: 'admin_name' },
    { name: 'admin_phone' },
  ];
  function createOrganization() {
    C.form({
      title: '新增合作机构',
      fields: organizationFields,
      initial: { kind: 'broker' },
      hint: '同时创建平台开通的初始管理员，其管理员身份不能被机构修改。新增后需完成机构审核。',
      onSubmit: (v) => C.api(base + 'organizations', 'POST', v),
    });
  }
  C.pages.institutions = () =>
    h(
      C.Panel,
      {
        title: '机构管理',
        extra: h(A.Button, { type: 'primary', onClick: createOrganization }, '新增机构'),
      },
      h(C.List, {
        path: base + 'organizations',
        search: true,
        columns: [
          C.column('name', '机构名称', 240),
          C.column('kind'),
          C.column('status'),
          C.column('id', '机构编号', 280),
        ],
        actions: (r) => C.button('详情', () => C.open('institution', { id: r.id })),
      }),
    );
  function OrganizationInfo({ row }) {
    return h(
      'div',
      null,
      h(C.Facts, {
        data: { ...row, ...row.details },
        fields: ['name', 'kind', 'status', 'contact_name', 'contact_phone'],
      }),
      h(
        A.Space,
        { wrap: true, className: 'detail-actions' },
        C.role === 'platform' &&
          row.kind !== 'clinic' &&
          C.button('修改资料', () =>
            C.form({
              title: '修改机构资料',
              fields: [
                { name: 'name', label: '机构名称' },
                { name: 'contact_name' },
                { name: 'contact_phone' },
                C.Reason,
              ],
              initial: { name: row.name, ...row.details },
              onSubmit: (v) =>
                C.api(base + 'organizations/' + row.id, 'POST', { ...v, version: row.version }),
            }),
          ),
        row.status === 'pending' &&
          C.button('审核机构', () =>
            C.action(
              '审核机构',
              base + 'organizations/' + row.id + '/review',
              row.version,
              { approved: true },
              C.reviewFields,
            ),
          ),
        row.status === 'rejected' &&
          C.button('重新提交审核', () =>
            C.action('重新提交审核', base + 'organizations/' + row.id + '/resubmit', row.version),
          ),
        ['active', 'disabled'].includes(row.status) &&
          row.kind !== 'clinic' &&
          C.button(row.status === 'active' ? '停用机构' : '启用机构', () =>
            C.action(
              row.status === 'active' ? '停用机构' : '启用机构',
              base + 'organizations/' + row.id + '/status',
              row.version,
              { status: row.status === 'active' ? 'disabled' : 'active' },
              [C.Reason],
              '停用后机构账号不能访问业务，请核对操作对象。',
            ),
          ),
      ),
    );
  }
  C.dialogs.institution = function ({ id, onClose, tab = 'info' }) {
    const q = C.useChoices(base + 'organizations/' + id),
      row = q.data;
    return h(
      C.Drawer,
      { title: (row?.name || '机构') + ' · 管理模块', onClose },
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Spin,
        { loading: q.loading, style: { width: '100%' } },
        row &&
          h(
            'div',
            null,
            h(A.Alert, {
              type: 'info',
              content:
                row.name + ' · ' + C.label(row.kind) + ' · 本页仅管理当前机构资料、合同及授权。',
            }),
            h(
              A.Tabs,
              { defaultActiveTab: tab },
              h(A.Tabs.TabPane, { key: 'info', title: '机构资料' }, h(OrganizationInfo, { row })),
              h(
                A.Tabs.TabPane,
                { key: 'contracts', title: '合作合同' },
                h(Contracts, { orgId: id, canManage: true }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'products', title: '推广产品配置' },
                h(Cooperation, { orgId: id, productsOnly: true }),
              ),
              ['insurance', 'bank', 'broker'].includes(row.kind) &&
                h(A.Tabs.TabPane, { key: 'brands', title: '来源展示名' }, h(Brands, { orgId: id })),
              h(
                A.Tabs.TabPane,
                { key: 'members', title: '机构账号' },
                h(Members, { orgId: id, kind: row.kind }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'logs', title: '操作记录' },
                h(C.Logs, { type: 'organization', id }),
              ),
            ),
          ),
      ),
    );
  };
  function Brands({ orgId }) {
    const edit = (row) =>
      C.form({
        title: row ? '修改来源展示名' : '新增来源展示名',
        fields: [
          { name: 'name', label: '对客户展示的来源名称' },
          { name: 'status', type: 'select', options: enums(['active', 'disabled']) },
        ],
        initial: row || { status: 'active' },
        hint: '仅当前客户资源方可选择本列表，不向其他资源方开放。',
        onSubmit: (v) =>
          C.api(base + 'organizations/' + orgId + '/source-brands', 'POST', {
            ...v,
            ...(row ? { brand_id: row.id, version: row.version } : {}),
          }),
      });
    return h(C.List, {
      path: base + 'organizations/' + orgId + '/source-brands',
      toolbar:
        C.role === 'platform' &&
        h(A.Button, { type: 'primary', onClick: () => edit() }, '新增展示名'),
      columns: [C.column('name', '来源展示名', 260), C.column('status')],
      actions: C.role === 'platform' ? (r) => C.button('修改', () => edit(r)) : null,
    });
  }
  function Members({ orgId, kind }) {
    const roles = [
      { value: 'admin', label: '管理员' },
      ...(kind === 'platform'
        ? []
        : [{ value: 'staff', label: kind === 'clinic' ? '员工' : '业务员' }]),
    ];
    const add = () =>
      C.form({
        title: '创建登录账号',
        fields: [
          { name: 'name', label: '账号姓名' },
          { name: 'phone', label: '登录手机号' },
          { name: 'role', type: 'select', options: roles },
        ],
        initial: { role: kind === 'platform' ? 'admin' : 'staff' },
        hint: '使用手机号和验证码登录；管理员可见机构全部数据，业务员仅可见本人关联业务。',
        onSubmit: (v) => C.api(base + 'organizations/' + orgId + '/members', 'POST', v),
      });
    const edit = (r) =>
      C.form({
        title: '管理账号 · ' + r.name,
        fields: [
          { name: 'role', type: 'select', options: roles, disabled: r.platform_created },
          { name: 'active', type: 'boolean' },
          C.Reason,
        ],
        initial: { role: r.role, active: r.active },
        hint: r.platform_created
          ? '平台开通的初始管理员，身份锁定。停用自己的账号及最后一个管理员会被拒绝。'
          : '角色与数据范围由服务端校验；暂不提供业务员交接功能。',
        onSubmit: (v) => C.api(base + 'members/' + r.id, 'POST', { ...v, version: r.version }),
      });
    return h(C.List, {
      path: base + 'organizations/' + orgId + '/members',
      toolbar: h(A.Button, { type: 'primary', onClick: add }, '创建账号'),
      columns: ['name', 'phone', 'role', 'active', 'platform_created'].map((k) => C.column(k)),
      actions: (r) => [
        C.button('管理', () => edit(r)),
        C.button('操作记录', () =>
          C.open('logs', { type: 'membership', id: r.id, title: r.name + ' · 操作记录' }),
        ),
      ],
    });
  }
  C.Members = Members;
  C.pages.accounts = () =>
    h(
      C.Panel,
      { title: '账号管理' },
      h(Members, { orgId: C.actor.organization_id, kind: C.actor.kind }),
    );
  C.dialogs.logs = ({ type, id, title, onClose }) =>
    h(C.Drawer, { title: title || '操作记录', onClose }, h(C.Logs, { type, id }));
  const contractFields = [
    { name: 'number', label: '合同编号' },
    { name: 'starts_at', type: 'date', time: true },
    { name: 'ends_at', type: 'date', time: true },
    { name: 'settlement_cycle', type: 'select', options: enums(['monthly', 'weekly']) },
    { name: 'contact_name', label: '合同联系人' },
    { name: 'contact_phone', label: '合同联系电话' },
    { name: 'attachment_ids', label: '完整合同附件', type: 'files', purpose: 'contract' },
  ];
  async function contractForm(orgId, row, renewFrom) {
    if (!row && !renewFrom) {
      try {
        const history = await C.api(base + 'organizations/' + orgId + '/contracts?page_size=1');
        renewFrom = history.results[0];
      } catch (error) {
        A.Message.error(error.message);
        return;
      }
    }
    C.form({
      title: row ? '修改合同草稿' : '登记合同 / 续签',
      fields: row
        ? [...contractFields.filter((f) => f.name !== 'number'), C.Reason]
        : contractFields,
      initial: row
        ? { ...row, contact_name: row.contact.name, contact_phone: row.contact.phone }
        : { settlement_cycle: renewFrom?.settlement_cycle || 'monthly', number: renewFrom?.number || '' },
      hint: '三方门诊合同由渠道提交、平台审核。月结付款期限为出账次日起5个自然日，周结为3个自然日；新周期适用于尚未出账交易。',
      onSubmit: (v) => {
        const { number, reason, contact_name, contact_phone, ...values } = v;
        const data = {
          ...values,
          starts_at: C.iso(values.starts_at),
          ends_at: C.iso(values.ends_at),
          contact: { name: contact_name, phone: contact_phone },
        };
        return C.api(
          base + (row ? 'contract-versions/' + row.id : 'organizations/' + orgId + '/contracts'),
          'POST',
          row ? { data, reason, version: row.version } : { number, data },
        );
      },
    });
  }
  function Contracts({ orgId, canManage = false }) {
    return h(C.List, {
      path: base + 'organizations/' + orgId + '/contracts',
      toolbar:
        canManage &&
        h(A.Button, { type: 'primary', onClick: () => contractForm(orgId) }, '登记 / 续签合同'),
      columns: [
        'number',
        'revision',
        'starts_at',
        'ends_at',
        'settlement_cycle',
        'display_status',
      ].map((k) => C.column(k)),
      actions: (r) => C.button('详情', () => C.open('contract', { id: r.id, canManage })),
    });
  }
  C.Contracts = Contracts;
  C.dialogs.contract = function ({ id, canManage = false, onClose }) {
    const q = C.useChoices(base + 'contract-versions/' + id),
      r = q.data;
    canManage = canManage && (C.role === 'platform' || (C.role === 'channel' && r?.kind === 'clinic'));
    return h(
      C.Drawer,
      { title: '合同详情', onClose, width: 1000 },
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Spin,
        { loading: q.loading, style: { width: '100%' } },
        r &&
          h(
            'div',
            null,
            h(A.Alert, {
              type: 'info',
              content:
                r.number +
                ' · 第' +
                r.revision +
                '版 · ' +
                C.label(r.display_status) +
                '。存量核销优先适用新合同，无新合同时使用最近合同。',
            }),
            h(
              A.Space,
              { wrap: true, className: 'detail-actions' },
              canManage &&
                r.status === 'draft' &&
                C.button('修改草稿', () => contractForm(r.organization_id, r)),
              canManage && r.status !== 'draft' && r.status !== 'pending' &&
                C.button(r.status === 'rejected' ? '修改并重新登记' : '登记续签版本', () => contractForm(r.organization_id, null, r)),
              canManage &&
                r.status === 'draft' &&
                C.button('提交审核', () =>
                  C.action(
                    '提交合同审核',
                    base + 'contract-versions/' + id + '/submit',
                    r.version,
                    {},
                    [],
                    '确认合同资料与全部附件完整后提交。',
                  ),
                ),
              C.role === 'platform' &&
                r.status === 'pending' &&
                C.button('审核合同', () =>
                  C.action(
                    '审核合同',
                    base + 'contract-versions/' + id + '/review',
                    r.version,
                    { approved: true },
                    C.reviewFields,
                  ),
                ),
              C.role === 'platform' &&
                r.status === 'approved' &&
                C.button('终止合同', () =>
                  C.action(
                    '终止合同',
                    base + 'contract-versions/' + id + '/terminate',
                    r.version,
                    {},
                    [C.Reason],
                    '新业务将停止使用本合同，存量预约仍按履约规则处理。',
                  ),
                ),
            ),
            h(
              A.Tabs,
              { defaultActiveTab: 'info' },
              h(
                A.Tabs.TabPane,
                { key: 'info', title: '合同资料' },
                h(C.Facts, {
                  data: r,
                  fields: [
                    'number',
                    'revision',
                    'display_status',
                    'starts_at',
                    'ends_at',
                    'settlement_cycle',
                    'submitted_at',
                    'due_at',
                    'reviewed_at',
                    'reason',
                  ],
                }),
                h(
                  C.Panel,
                  { title: '合同联系人' },
                  h(C.Facts, {
                    data: { contact_name: r.contact.name, contact_phone: r.contact.phone },
                  }),
                ),
                h(C.Panel, { title: '全部合同附件' }, h(C.Attachments, { ids: r.attachment_ids })),
              ),
              r.kind !== 'clinic' &&
                h(
                  A.Tabs.TabPane,
                  { key: 'products', title: '推广产品配置' },
                  h(Terms, { contract: r }),
                ),
              h(
                A.Tabs.TabPane,
                { key: 'logs', title: '操作记录' },
                h(C.Logs, { type: 'contractversion', id }),
              ),
            ),
          ),
      ),
    );
  };
  function Terms({ contract }) {
    const edit = (row) => C.open('termForm', { contract, row });
    const editable = C.role === 'platform' && ['draft', 'approved'].includes(contract.status);
    return h(C.List, {
      path: base + 'contract-versions/' + contract.id + '/products',
      toolbar:
        editable &&
        h(A.Button, { type: 'primary', onClick: () => edit() }, '添加推广产品'),
      columns: [
        {
          title: '推广产品',
          width: 220,
          render: (_, r) => r.product?.internal_name || r.product_id,
        },
        { title: '单次获客费', width: 150, render: (_, r) => C.money(r.product?.fee_cents) },
        C.column('mode', '分配方式'),
        {
          title: '分配数值',
          width: 140,
          render: (_, r) => r.value + (r.mode === 'percent' ? ' %' : ' 元/次'),
        },
        {
          title: '本方金额（元/次）',
          width: 170,
          render: (_, r) =>
            C.money(
              Math.round(
                r.mode === 'percent'
                  ? (r.product.fee_cents * Number(r.value)) / 100
                  : Number(r.value) * 100,
              ),
            ),
        },
        C.column('status'),
      ],
      actions: editable ? (r) => C.button('修改配置', () => edit(r)) : null,
    });
  }
  C.dialogs.termForm = function ({ contract, row, onClose }) {
    const q = C.useChoices(base + 'products?page_size=100');
    const [preview, setPreview] = React.useState({
      product_id: row?.product_id,
      mode: row?.mode || 'percent',
      value: Number(row?.value || 0),
    });
    const options = (q.data?.results || []).map((p) => ({
      value: p.id,
      label: p.internal_name + ' · ' + C.money(p.fee_cents),
    }));
    const product = q.data?.results.find((p) => p.id === preview.product_id);
    const cents = product
      ? Math.round(
          preview.mode === 'percent'
            ? (product.fee_cents * preview.value) / 100
            : preview.value * 100,
        )
      : null;
    const update = (key) => (value) => setPreview((v) => ({ ...v, [key]: value }));
    return h(C.FormDialog, {
      title: '推广产品配置 · ' + contract.number,
      onClose,
      fields: [
        {
          name: 'product_id',
          label: '推广产品',
          render: () => h(A.Select, { options, disabled: !!row, onChange: update('product_id') }),
        },
        {
          name: 'mode',
          label: '分配方式',
          render: () =>
            h(A.Select, { options: enums(['percent', 'amount']), onChange: update('mode') }),
        },
        {
          name: 'value',
          label: preview.mode === 'percent' ? '分配比例（%）' : '单次分配金额（元）',
          render: () =>
            h(A.InputNumber, {
              min: 0,
              precision: 2,
              style: { width: '100%' },
              onChange: update('value'),
            }),
        },
        { name: 'status', type: 'select', options: enums(['active', 'disabled']) },
        C.Reason,
      ],
      initial: row
        ? {
            product_id: row.product_id,
            mode: row.mode,
            value: Number(row.value),
            status: row.status,
          }
        : { mode: 'percent', value: 0, status: 'active' },
      hint: h(
        'div',
        null,
        h(C.Error, { error: q.error, retry: q.reload }),
        h('p', null, '一个合同可配置多个推广产品。最终分配不能超过获客费，核销时锁定。'),
        h(A.Alert, {
          type: product && cents > product.fee_cents ? 'error' : 'info',
          content: product
            ? '实时试算：单次获客费 ' +
              C.money(product.fee_cents) +
              '，本方分配 ' +
              C.money(cents) +
              '。其他合作方与平台剩余收益以核销校验为准。'
            : '选择推广产品后显示分配试算。',
        }),
      ),
      onSubmit: (v) =>
        C.api(base + 'contract-versions/' + contract.id + '/products', 'POST', {
          ...v,
          value: String(v.value),
          ...(row ? { version: row.version } : {}),
        }),
    });
  };
  function Cooperation({ orgId, productsOnly = false }) {
    const q = C.useChoices(base + 'organizations/' + orgId + '/cooperation'),
      r = q.data;
    return h(
      'div',
      null,
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Spin,
        { loading: q.loading, style: { width: '100%' } },
        r &&
          h(
            'div',
            null,
            r.current_contract
              ? h(
                  C.Panel,
                  {
                    title: '当前合作合同',
                    extra: C.button('查看合同', () =>
                      C.open('contract', {
                        id: r.current_contract.id,
                        canManage: C.role === 'platform',
                      }),
                    ),
                  },
                  h(C.Facts, {
                    data: r.current_contract,
                    fields: [
                      'number',
                      'starts_at',
                      'ends_at',
                      'display_status',
                      'settlement_cycle',
                    ],
                  }),
                )
              : h(A.Alert, { type: 'warning', content: '尚无可用合同，请联系平台办理。' }),
            r.next_contract &&
              h(
                C.Panel,
                { title: '下一合同' },
                h(C.Facts, {
                  data: r.next_contract,
                  fields: ['number', 'starts_at', 'ends_at', 'display_status'],
                }),
              ),
            r.pending_contract &&
              h(
                C.Panel,
                {
                  title: '待审核合同',
                  extra: C.button('详情', () =>
                    C.open('contract', {
                      id: r.pending_contract.id,
                      canManage: C.role === 'platform',
                    }),
                  ),
                },
                h(C.Facts, {
                  data: r.pending_contract,
                  fields: ['number', 'display_status', 'due_at'],
                }),
              ),
            r.current_contract &&
              r.products_endpoint &&
              h(
                C.Panel,
                { title: '推广产品配置' },
                r.products_endpoint.includes('contract-versions')
                  ? h(Terms, { contract: r.current_contract })
                  : h(C.ClinicProducts, { clinicId: r.products_endpoint.split('/')[4] }),
              ),
            !productsOnly &&
              h(C.Panel, { title: '合同历史' }, h(Contracts, { orgId, canManage: false })),
          ),
      ),
    );
  }
  C.Cooperation = Cooperation;
  C.pages.cooperation = () =>
    h(
      C.Panel,
      { title: '合作合同与推广产品' },
      h(A.Alert, {
        type: 'info',
        content: '本页仅查看本机构合同及授权推广产品；配置由平台统一管理。',
      }),
      h(Cooperation, { orgId: C.actor.organization_id }),
    );
})();
