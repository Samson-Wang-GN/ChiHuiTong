(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C,
    base = '/api/v1/';
  Object.assign(C.names, {
    content: '模板内容',
    parameter_names: '模板变量',
    provider_template_id: '服务商模板编号',
    sign_name: '短信签名',
    template_code: '短信类型',
    attempts: '尝试次数',
    attempt: '本次序号',
    last_error_code: '最近异常',
    error_code: '异常代码',
    available_at: '计划执行时间',
    locked_until: '处理锁到期',
    accepted_at: '受理时间',
    finished_at: '结束时间',
    simulated: '模拟记录',
    note: '说明',
    working: '工作日',
    date: '日期',
  });
  Object.assign(C.labels, {
    open: '待处理',
    resolved: '已处理',
    'contract.expiring': '合同即将到期',
    accepted: '已受理（不等于送达）',
    sending: '发送中',
    unknown: '结果待核实',
    done: '执行完成',
    'appointment.new': '新预约',
    'appointment.cancelled': '预约取消',
    'appointment.reschedule': '客户改期',
    'appointment.overdue': '过期预约提醒',
    'appointment.supplement': '补核销提醒',
    'bill.reminder': '付款提醒',
    'bill.overdue': '逾期提醒',
  });
  C.openNotification = (r) => {
    if (r.object_type === 'contract' && r.contract_version_id) {
      C.open('contract', {
        id: r.contract_version_id,
        canManage: C.role === 'channel' || C.role === 'platform',
      });
      return;
    }
    const type = {
      appointment: 'appointment',
      clinicbill: 'clinicBill',
      partnerbill: 'partnerBill',
      salesorder: 'sale',
      clinic: 'clinic',
    }[r.object_type];
    if (type && C.dialogs[type]) C.open(type, { id: r.object_id });
    else C.showTasks('all');
  };
  C.NotificationList = ({ initialStatus = 'all' }) =>
    h(
      C.Panel,
      { title: '站内消息' },
      h(C.List, {
        path: base + 'notifications',
        initialStatus,
        columns: ['title', 'created_at', 'status'].map((k) => C.column(k)),
        actions: (r) => [
          r.status === 'unread' &&
            C.button('标为已读', async () => {
              try {
                await C.api(base + 'notifications/' + r.id + '/read', 'POST', {});
                C.refresh();
              } catch (e) {
                A.Message.error(e.message);
              }
            }),
          C.button('查看事项', () => C.openNotification(r)),
        ],
      }),
    );
  C.pages.notifications = () => h(C.NotificationList);
  C.pages.sms = () =>
    h(
      C.Panel,
      { title: '短信管理' },
      h(A.Alert, {
        type: 'warning',
        content:
          '开发验收使用模拟短信，模拟受理不代表真实发送或送达。正式短信签名、报备、费用和重试由平台负责。',
      }),
      h(
        A.Tabs,
        { defaultActiveTab: 'templates' },
        h(
          A.Tabs.TabPane,
          { key: 'templates', title: '预置模板配置' },
          h(C.List, {
            path: base + 'sms-templates',
            columns: ['name', 'content', 'provider_template_id', 'sign_name', 'status'].map((k) =>
              C.column(k),
            ),
            actions: (r) =>
              C.button('修改配置', () =>
                C.form({
                  title: '配置短信模板 · ' + r.name,
                  fields: [
                    { name: 'content', type: 'textarea', max: 1000 },
                    { name: 'parameters', label: '变量顺序（英文逗号分隔）' },
                    { name: 'provider_template_id', optional: true },
                    { name: 'sign_name', optional: true },
                    {
                      name: 'status',
                      type: 'select',
                      options: C.options({ active: '启用', disabled: '停用' }),
                    },
                    C.Reason,
                  ],
                  initial: { ...r, parameters: r.parameter_names.join(',') },
                  hint: '只修改预置模板，不新增短信类型。变量名称必须与预置业务匹配，真实服务商参数顺序必须一致。',
                  onSubmit: (v, key) => {
                    const { parameters, ...data } = v;
                    return C.api(
                      base + 'sms-templates/' + r.code,
                      'POST',
                      {
                        ...data,
                        provider_template_id: data.provider_template_id || '',
                        sign_name: data.sign_name || '',
                        parameter_names: parameters
                          .split(',')
                          .map((s) => s.trim())
                          .filter(Boolean),
                        version: r.version,
                      },
                      key,
                    );
                  },
                }),
              ),
          }),
        ),
        h(
          A.Tabs.TabPane,
          { key: 'deliveries', title: '发送记录' },
          h(C.List, {
            path: base + 'sms-deliveries',
            columns: [
              'template_code',
              'phone',
              'status',
              'simulated',
              'attempts',
              'accepted_at',
              'last_error_code',
            ].map((k) => C.column(k)),
            actions: (r) => C.button('发送过程', () => C.open('smsHistory', { id: r.id })),
          }),
        ),
      ),
    );
  C.dialogs.smsHistory = ({ id, onClose }) =>
    h(
      C.Drawer,
      { title: '短信发送过程', onClose },
      h(C.List, {
        path: base + 'sms-deliveries/' + id + '/attempts',
        columns: ['attempt', 'created_at', 'finished_at', 'status', 'simulated', 'error_code'].map(
          (k) => C.column(k),
        ),
        actions: (r) => C.button('模板快照', () => C.open('smsTemplateSnapshot', { row: r })),
      }),
    );
  C.dialogs.smsTemplateSnapshot = ({ row, onClose }) =>
    h(
      C.Drawer,
      { title: '本次发送模板快照', onClose, width: 760 },
      h(C.Facts, { data: row }),
      h(
        C.Panel,
        { title: '发送时使用的模板' },
        h(C.Facts, {
          data: { ...row.template, parameter_names: row.template?.parameter_names?.join('，') },
        }),
      ),
    );
  C.pages.jobs = () =>
    h(
      C.Panel,
      { title: '系统任务' },
      h(C.List, {
        path: base + 'jobs',
        columns: ['kind', 'status', 'attempts', 'available_at', 'last_error_code'].map((k) =>
          C.column(k),
        ),
        actions: (r) => C.button('详情', () => C.open('job', { row: r })),
      }),
    );
  C.dialogs.job = ({ row: r, onClose }) =>
    h(
      C.Drawer,
      { title: '系统任务详情', onClose, width: 760 },
      h(C.Facts, { data: r }),
      r.status === 'failed' &&
        h(
          A.Button,
          {
            type: 'primary',
            style: { marginTop: 20 },
            onClick: () =>
              C.action(
                '重新执行失败任务',
                base + 'jobs/' + r.id + '/retry',
                null,
                {},
                [C.Reason],
                '只重试本任务；服务端继续检查幂等和业务状态，不绕过原有审核。',
              ),
          },
          '重试任务',
        ),
    );
  C.pages.calendar = function () {
    const [year, setYear] = React.useState(new Date().getFullYear()),
      [status, setStatus] = React.useState('all');
    const q = C.useQuery(base + 'calendar?year=' + year);
    const rows = q.data?.results || [];
    const edit = (row) =>
      C.form({
        title: '工作日 / 调休配置',
        fields: [
          { name: 'date', label: '日期', type: 'date' },
          { name: 'working', label: '是否工作日', type: 'boolean' },
          { name: 'note', label: '配置说明' },
        ],
        initial: row || { working: true },
        hint: '用于两工作日审核期限；周/月账单付款期限按自然日，不受工作日配置影响。',
        onSubmit: (v) =>
          C.api(base + 'calendar/' + v.date, 'POST', { working: v.working, note: v.note }),
      });
    return h(
      C.Panel,
      {
        title: '工作日日历',
        extra: h(A.Button, { type: 'primary', onClick: () => edit() }, '配置日期'),
      },
      h(A.Alert, {
        type: 'info',
        content: '未单独配置的日期默认周一至周五为工作日。请按实际节假日及调休安排维护。',
      }),
      h(A.InputNumber, {
        value: year,
        onChange: (v) => {
          if (v >= 2020 && v <= 2100) setYear(v);
        },
        min: 2020,
        max: 2100,
        style: { margin: '16px 0' },
        suffix: '年',
      }),
      h(C.Error, { error: q.error, retry: q.reload }),
      h(
        A.Tabs,
        { activeTab: status, onChange: setStatus },
        [
          ['all', '全部'],
          ['working', '工作日'],
          ['holiday', '休息日'],
        ].map(([key, label]) =>
          h(A.Tabs.TabPane, {
            key,
            title:
              label +
              '（' +
              rows.filter((r) => key === 'all' || r.working === (key === 'working')).length +
              '）',
          }),
        ),
      ),
      h(A.Table, {
        rowKey: 'date',
        loading: q.loading,
        data: rows.filter((r) => status === 'all' || r.working === (status === 'working')),
        columns: ['date', 'working', 'note']
          .map((k) => C.column(k))
          .concat([
            { title: '操作', width: 120, render: (_, r) => C.button('修改', () => edit(r)) },
          ]),
        pagination: { pageSize: 20 },
        scroll: { x: 700 },
      }),
    );
  };
})();
