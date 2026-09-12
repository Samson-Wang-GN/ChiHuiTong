(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C,
    base = '/api/v1/';
  Object.assign(C.names, {
    amount_cents: '本次金额',
    remaining_cents: '待收金额',
    payer: '付款方',
    reference: '付款流水号',
    paid_at: '付款时间',
    cycle: '结算周期',
    issued_on: '出账日期',
    period_end: '账期截止日',
    month: '结算月份',
    confirmed_at: '对账确认时间',
    received_at: '收款确认时间',
    actual_received_on: '实际收款日期',
    ledger_status: '记账状态',
    message: '异议内容',
    response: '处理回复',
    responded_at: '回复时间',
    bill_id: '账单编号',
    removed_at: '移除时间',
  });
  C.receiptFields = [
    { name: 'amount', label: '付款金额（元）', type: 'number', min: 0.01, precision: 2 },
    { name: 'paid_at', type: 'date', time: true },
    { name: 'payer', label: '付款方名称' },
    { name: 'reference', label: '付款流水号' },
    { name: 'attachment_ids', label: '付款凭证（全部）', type: 'files', purpose: 'payment' },
  ];
  C.receiptForm = (title, path, row) =>
    C.form({
      title,
      fields: C.receiptFields,
      initial: { amount: (row.remaining_cents ?? row.total_cents) / 100 },
      hint: '请上传已付款凭证；提交不等于到账，平台审核全额收款后账单才结清。验收环境只允许合成资料。',
      submitText: '提交付款凭证',
      onSubmit: (v, key) => {
        const { amount, ...data } = v;
        return C.api(
          path,
          'POST',
          {
            ...data,
            amount_cents: Math.round(amount * 100),
            paid_at: C.iso(data.paid_at),
            version: row.version,
          },
          key,
        );
      },
    });
  C.dialogs.clinicReceipt = ({ row: r, onClose }) =>
    h(
      C.Drawer,
      { title: '门诊收款凭证审核', onClose, width: 760 },
      h(C.Facts, {
        data: r,
        fields: ['bill_id', 'amount_cents', 'payer', 'paid_at', 'reference', 'status', 'reason'],
      }),
      h(C.Panel, { title: '全部付款凭证' }, h(C.Attachments, { ids: r.attachment_ids })),
      C.role === 'platform' &&
      r.status === 'pending' &&
        h(
          A.Button,
          {
            type: 'primary',
            style: { marginTop: 20 },
            onClick: () =>
              C.action(
                '审核门诊收款',
                base + 'clinic-receipts/' + r.id + '/review',
                r.version,
                { approved: true },
                C.reviewFields,
                '请核对账单、付款方、金额及到账流水；审核通过代表平台确认该笔款项已到账。',
              ),
          },
          '审核确认',
        ),
    );
  C.pages.clinicBills = () =>
    h(
      C.Panel,
      { title: '门诊账单' },
      h(A.Alert, {
        type: 'info',
        content: '按门诊合同周结 / 月结出账；逾期仅提醒，不自动下线。上传凭证后等待平台核实到账。',
      }),
      h(C.List, {
        path: base + 'clinic-bills',
        columns: [
          'clinic_name',
          'cycle',
          'issued_on',
          'due_at',
          'total_cents',
          'received_cents',
          'remaining_cents',
          'status',
        ].map((k) => C.column(k)),
        actions: (r) => C.button('详情', () => C.open('clinicBill', { id: r.id })),
      }),
    );
  function BillLines({ path, partner = false }) {
    return h(C.List, {
      path,
      exportPath: path.endsWith('/lines')
        ? path.slice(0, -6) + '/export.xlsx'
        : path + '/export.xlsx',
      exportName: partner ? '合作方逐笔明细.xlsx' : '门诊账单明细.xlsx',
      statusLabels: partner ? {} : { active: '有效交易', disabled: '已移除交易' },
      initialStatus: 'all',
      columns: [
        { title: '客户', width: 140, render: (_, r) => r.transaction.customer_name },
        { title: '门诊', width: 180, render: (_, r) => r.transaction.clinic_name },
        { title: '推广产品', width: 200, render: (_, r) => r.transaction.internal_name },
        {
          title: '核销时间',
          width: 180,
          render: (_, r) => C.text('redeemed_at', r.transaction.redeemed_at),
        },
        C.column('amount_cents'),
        {
          title: '门诊是否结算',
          width: 140,
          render: (_, r) => (r.transaction.clinic_settled ? '已结清' : '未结清'),
        },
        partner ? C.column('status') : C.column('active', '有效交易'),
      ],
      actions: (r) =>
        C.button('逐笔详情', () =>
          C.open('transaction', {
            row: { ...r.transaction, amount_cents: r.amount_cents, removed_at: r.removed_at },
          }),
        ),
    });
  }
  C.BillLines = BillLines;
  function FeedbackList({ rows }) {
    return rows?.length
      ? h(A.Table, {
          rowKey: 'id',
          data: rows,
          pagination: false,
          scroll: { x: 780 },
          columns: ['created_at', 'message', 'response', 'status']
            .map((k) => C.column(k))
            .concat([
              {
                title: '操作',
                width: 120,
                render: (_, r) => C.button('处理详情', () => C.open('feedback', { row: r })),
              },
            ]),
        })
      : h(A.Empty, { description: '暂无异议记录' });
  }
  function feedback(row, partner) {
    C.form({
      title: '提交账单异议',
      fields: [{ name: 'message', label: '问题描述', type: 'textarea', max: 2000 }],
      hint: '请描述具体交易和疑问，不要填写银行密码等无关资料。提交后由平台处理。',
      onSubmit: (v, key) =>
        C.api(
          base + (partner ? 'partner-bills/' : 'clinic-bills/') + row.id + '/feedback',
          'POST',
          { ...v, version: row.version },
          key,
        ),
    });
  }
  C.dialogs.feedback = ({ row: r, onClose }) =>
    h(
      C.Drawer,
      { title: '账单异议详情', onClose, width: 760 },
      h(C.Facts, { data: r }),
      C.role === 'platform' &&
        r.status === 'open' &&
        h(
          A.Button,
          {
            type: 'primary',
            style: { marginTop: 20 },
            onClick: () =>
              C.form({
                title: '回复账单异议',
                fields: [{ name: 'response', label: '处理回复', type: 'textarea', max: 2000 }],
                onSubmit: (v, key) =>
                  C.api(
                    base + 'finance-feedback/' + r.id + '/respond',
                    'POST',
                    { ...v, version: r.version },
                    key,
                  ),
              }),
          },
          '处理回复',
        ),
    );
  C.dialogs.clinicBill = function ({ id, onClose }) {
    const q = C.useQuery(base + 'clinic-bills/' + id),
      r = q.data;
    return h(
      C.Drawer,
      { title: '门诊账单详情', onClose },
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Spin,
        { loading: q.loading, style: { width: '100%' } },
        r &&
          h(
            'div',
            null,
            h(A.Alert, {
              type: r.status === 'overdue' ? 'warning' : 'info',
              content:
                r.clinic_name +
                ' · ' +
                C.label(r.cycle) +
                ' · 应收 ' +
                C.money(r.total_cents) +
                '；付款截止 ' +
                C.text('due_at', r.due_at),
            }),
            h(
              A.Space,
              { wrap: true, className: 'detail-actions' },
              C.role === 'clinic' &&
                ['pending_payment', 'overdue', 'disputed'].includes(r.status) &&
                h(
                  A.Button,
                  {
                    type: 'primary',
                    onClick: () =>
                      C.receiptForm(
                        '上传门诊付款凭证',
                        base + 'clinic-bills/' + id + '/receipts',
                        r,
                      ),
                  },
                  '上传付款凭证',
                ),
              C.role === 'clinic' &&
                !['settled', 'cancelled', 'no_payment'].includes(r.status) &&
                h(A.Button, { onClick: () => C.open('payment', { bill: r }) }, '微信扫码支付'),
              ['clinic', 'channel'].includes(C.role) &&
                C.button('反馈异议', () => feedback(r, false)),
              ['platform', 'channel'].includes(C.role) &&
                C.button('记录催收', () =>
                  C.action(
                    '记录门诊催收',
                    base + 'clinic-bills/' + id + '/collection-note',
                    r.version,
                    {},
                    [C.Reason],
                  ),
                ),
            ),
            h(
              A.Tabs,
              { defaultActiveTab: 'lines' },
              h(
                A.Tabs.TabPane,
                { key: 'lines', title: '逐笔交易' },
                h(BillLines, { path: base + 'clinic-bills/' + id + '/lines' }),
              ),
              h(A.Tabs.TabPane, { key: 'info', title: '账单信息' }, h(C.Facts, { data: r })),
              h(
                A.Tabs.TabPane,
                { key: 'receipts', title: '收款凭证' },
                h(C.List, {
                  path: base + 'clinic-bills/' + id + '/receipts',
                  columns: ['amount_cents', 'payer', 'paid_at', 'reference', 'status'].map((k) =>
                    C.column(k),
                  ),
                  actions: (v) => C.button('凭证详情', () => C.open('clinicReceipt', { row: v })),
                }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'payments', title: '微信支付记录' },
                h(PaymentList, { bill: r }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'feedback', title: '账单异议' },
                h(FeedbackList, { rows: r.feedback }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'logs', title: '操作记录' },
                h(C.Logs, { type: 'clinicbill', id }),
              ),
            ),
          ),
      ),
    );
  };
  C.pages.partnerBills = function () {
    const staff = C.actor.role !== 'admin';
    return h(
      C.Panel,
      { title: staff ? '本人结算明细' : '合作方结算单' },
      h(A.Alert, {
        type: 'info',
        content: staff
          ? '仅显示本人负责业务的逐笔明细，不显示或处理机构整张结算单。'
          : '每月合并历史未结算且门诊已全额付款的交易。合作方确认 → 平台上传线下付款凭证 → 合作方确认收款；0元单无需付款。',
      }),
      staff
        ? h(
            React.Fragment,
            null,
            h(
              A.Button,
              {
                style: { margin: '16px 0' },
                onClick: () =>
                  C.download(base + 'settlement-details/export.xlsx', '本人结算明细.xlsx').catch(
                    (e) => A.Message.error(e.message),
                  ),
              },
              '下载 Excel',
            ),
            h(BillLines, { path: base + 'settlement-details', partner: true }),
          )
        : h(C.List, {
            path: base + 'partner-bills',
            columns: [
              'organization_name',
              'month',
              'issued_on',
              'due_at',
              'total_cents',
              'status',
            ].map((k) => C.column(k)),
            actions: (r) => C.button('详情', () => C.open('partnerBill', { id: r.id })),
          }),
    );
  };
  function partnerPay(r) {
    C.form({
      title: '登记合作方线下付款',
      fields: C.receiptFields.filter((f) => f.name !== 'payer'),
      initial: { amount: r.total_cents / 100 },
      hint: '请先线下完成付款，再上传凭证；登记后等待合作方确认收款。当前为合成数据，不发生真实付款。',
      submitText: '登记已付款',
      onSubmit: (v, key) => {
        const { amount, ...data } = v;
        return C.api(
          base + 'partner-bills/' + r.id + '/pay',
          'POST',
          {
            ...data,
            amount_cents: Math.round(amount * 100),
            paid_at: C.iso(data.paid_at),
            version: r.version,
            confirmed: true,
          },
          key,
        );
      },
    });
  }
  C.dialogs.partnerBill = function ({ id, onClose }) {
    const q = C.useQuery(base + 'partner-bills/' + id),
      r = q.data;
    return h(
      C.Drawer,
      { title: '合作方结算单详情', onClose },
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Spin,
        { loading: q.loading, style: { width: '100%' } },
        r &&
          h(
            'div',
            null,
            h(A.Alert, {
              type: r.status === 'no_payment' ? 'info' : 'warning',
              content:
                r.status === 'no_payment'
                  ? '本单金额0元，保留逐笔明细及日志，无需付款或确认。'
                  : r.organization_name +
                    ' · 本单金额 ' +
                    C.money(r.total_cents) +
                    ' · ' +
                    C.label(r.status),
            }),
            h(
              A.Space,
              { wrap: true, className: 'detail-actions' },
              C.role !== 'platform' &&
                r.status === 'pending_confirmation' &&
                h(
                  A.Button,
                  {
                    type: 'primary',
                    onClick: () =>
                      C.action(
                        '确认结算单',
                        base + 'partner-bills/' + id + '/confirm',
                        r.version,
                        { confirmed: true },
                        [],
                        '请核对全部逐笔交易和合计金额；确认后由平台线下付款。',
                      ),
                  },
                  '确认对账',
                ),
              C.role === 'platform' &&
                r.status === 'pending_payment' &&
                h(
                  A.Button,
                  { type: 'primary', onClick: () => partnerPay(r) },
                  '登记付款并上传凭证',
                ),
              C.role !== 'platform' &&
                r.status === 'pending_receipt' &&
                h(
                  A.Button,
                  {
                    type: 'primary',
                    onClick: () =>
                      C.form({
                        title: '确认已收到平台付款',
                        fields: [{ name: 'actual_received_on', type: 'date' }],
                        hint: '请核实真实到账日期后确认。验收环境仅作合成流程记录。',
                        submitText: '确认收款',
                        onSubmit: (v, key) =>
                          C.api(
                            base + 'partner-bills/' + id + '/receive',
                            'POST',
                            { ...v, version: r.version, confirmed: true },
                            key,
                          ),
                      }),
                  },
                  '确认收款',
                ),
              C.role !== 'platform' &&
                !['no_payment', 'completed'].includes(r.status) &&
                C.button('反馈异议', () => feedback(r, true)),
            ),
            h(
              A.Tabs,
              { defaultActiveTab: 'lines' },
              h(
                A.Tabs.TabPane,
                { key: 'lines', title: '逐笔交易' },
                h(BillLines, { path: base + 'partner-bills/' + id + '/lines', partner: true }),
              ),
              h(A.Tabs.TabPane, { key: 'info', title: '结算信息' }, h(C.Facts, { data: r })),
              h(
                A.Tabs.TabPane,
                { key: 'payment', title: '平台付款凭证' },
                r.payment
                  ? h(
                      'div',
                      null,
                      h(C.Facts, { data: r.payment }),
                      h(C.Attachments, { ids: r.payment.attachment_ids }),
                    )
                  : h(A.Empty, {
                      description: r.status === 'no_payment' ? '本单无需付款' : '平台尚未登记付款',
                    }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'feedback', title: '对账异议' },
                h(FeedbackList, { rows: r.feedback }),
              ),
              h(
                A.Tabs.TabPane,
                { key: 'logs', title: '操作记录' },
                h(C.Logs, { type: 'partnerbill', id }),
              ),
            ),
          ),
      ),
    );
  };
  function PaymentList({ bill }) {
    return h(C.List, {
      path: base + 'clinic-bills/' + bill.id + '/payments',
      columns: ['id', 'amount_cents', 'status', 'created_at'].map((k) => C.column(k)),
      actions:
        C.role === 'clinic'
          ? (r) =>
              ['creating', 'pending', 'unknown'].includes(r.status)
                ? C.button('核对支付', () =>
                    C.action(
                      '核对支付结果',
                      base + 'payments/' + r.id + '/query',
                      null,
                      { confirmed: true },
                      [],
                      '向当前支付适配器查询交易结果，不能以客户口头付款认定已到账。',
                    ),
                  )
                : null
          : null,
    });
  }
  C.dialogs.payment = function ({ bill, onClose }) {
    const q = C.useQuery(base + 'payments/configuration');
    return h(
      C.Drawer,
      { title: '微信扫码支付', onClose, width: 760 },
      h(C.Facts, {
        data: bill,
        fields: ['clinic_name', 'total_cents', 'remaining_cents', 'status'],
      }),
      h(C.Error, { error: q.error, retry: q.reload }),
      h(A.Alert, {
        type: 'warning',
        content:
          '当前为模拟验收，不发生真实付款；请勿使用真实微信付款。模拟成功仍通过服务器核对当前账单版本和金额。',
      }),
      q.data &&
        !q.data.wechat_enabled &&
        !q.data.simulated &&
        h(A.Alert, { type: 'info', content: '支付适配器尚未启用，可以使用上传付款凭证流程。' }),
      q.data?.simulated &&
        h(
          A.Button,
          {
            type: 'primary',
            style: { marginTop: 20 },
            onClick: () =>
              C.action(
                '确认模拟微信付款',
                base + 'clinic-bills/' + bill.id + '/payments',
                bill.version,
                { method: 'native' },
                [],
                '仅生成模拟成功交易并更新本验收账单，不调用微信、不发生资金往来。',
              ),
          },
          '模拟微信支付成功',
        ),
      h(C.Panel, { title: '本账单支付记录' }, h(PaymentList, { bill })),
    );
  };
})();
