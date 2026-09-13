import { Entity, Row, statuses, dateText, money, appointmentRow } from '../shared/model';
import * as R from '../shared/runtime';
import * as Files from './attachments';
import { payment } from './payment';
import {
  Screen,
  list,
  field,
  fact,
  detail,
  timeFields,
  checkTime,
  required,
  command,
  appointmentFacts,
} from '../shared/screens';

const org = () => R.current()!.membership!.organization_id;
const attachmentRows = (ids: string[] = []): Row[] =>
  ids.map((id, i) => ({
    id,
    title: '附件 ' + (i + 1),
    lines: [],
    actions: [{ key: 'attachment', id, label: '查看附件' }],
  }));
const billRow = (b: Entity): Row => ({
  id: b.id,
  title: b.clinic_name + ' · ' + (b.cycle === 'weekly' ? '周结' : '月结') + '账单',
  status: statuses[b.status] || b.status,
  lines: [
    '出账日：' + b.issued_on,
    '账单金额：' + money(b.total_cents),
    '未结金额：' + money(b.remaining_cents),
    '付款期限：' + dateText(b.due_at),
  ],
  actions: [{ key: 'bill', id: b.id, label: '查看账单' }],
});
const contractRow = (c: Entity): Row => ({
  id: c.id,
  title: c.number + ' · 第' + c.revision + '版',
  status: statuses[c.display_status] || statuses[c.status] || c.display_status,
  lines: [dateText(c.starts_at) + ' 至 ' + dateText(c.ends_at)],
  actions: [{ key: 'contract', id: c.id, label: '查看合同' }],
});
const financial = [
  'pending_payment',
  'payment_review',
  'disputed',
  'overdue',
  'settled',
  'cancelled',
  'no_payment',
];
const taskNames: Record<string, string> = {
  appointment_confirmation: '预约确认',
  appointment_reschedule: '客户改期申请',
  appointment_fulfillment: '过期预约待办',
  clinic_payment: '账单付款',
  finance_feedback: '对账反馈',
};
function appointmentActions(a: Entity): Entity[] {
  const pending = a.reschedules?.some((x: Entity) => x.status === 'pending');
  const actions: Entity[] = [];
  if (a.status === 'pending')
    actions.push(
      { key: 'confirm', label: '确认预约' },
      { key: 'cancel', label: '无法接诊，取消预约' },
    );
  if (a.status === 'success' && !pending) {
    actions.push({ key: 'reschedule', label: '协商改期' });
    if (new Date(a.scheduled_at).getTime() > Date.now())
      actions.push({ key: 'cancel', label: '无法接诊，取消预约' });
    else if (!a.patient_arrived_at && !a.conflict)
      actions.push({ key: 'report-absent', label: '患者未到，取消但不释放权益' });
  }
  if (pending) actions.push({ key: 'review-reschedule', label: '处理客户改期申请' });
  if (
    a.reserved &&
    !a.restoration_pending &&
    !a.conflict &&
    !pending &&
    ['success', 'completed'].includes(a.status)
  )
    actions.push({
      key: 'scan-appointment',
      label: a.completion_source === 'system' ? '扫码补核销' : '扫码核销',
    });
  const active = a.redemptions?.find((x: Entity) => x.status === 'active');
  if (active && !active.clinic_settled)
    actions.push({ key: 'reverse', label: '撤销错误核销', danger: true });
  actions.push({ key: 'appointment-logs', label: '操作记录' }, { key: 'phone', label: '联系客户' });
  return actions;
}
export const screens: Record<string, Screen> = {
  home: {
    async load() {
      const w = await R.request('/workbench');
      return {
        title: R.current()!.membership!.organization_name,
        notice: '预约确认、改期与核销请及时处理；系统自动完成不代表已治疗。',
        actions: [
          { key: 'tasks', label: '待处理任务' },
          { key: 'fulfillment', label: '过期预约待办' },
          { key: 'notifications', label: '通知消息' },
        ],
        facts: Object.entries(w.tasks.categories || {})
          .filter(([k]) => taskNames[k])
          .map(([k, v]) => fact(taskNames[k], (v as Entity).pending)),
      };
    },
  },
  tasks: {
    load: (ctx) =>
      list(
        ctx,
        '/workbench/tasks',
        ['pending', 'processed'],
        (t) => ({
          id: t.id,
          title: t.title,
          status: t.status === 'pending' ? '待处理' : '已处理',
          lines: [dateText(t.created_at), t.overdue ? '已超过处理期限' : ''],
          actions: [{ key: 'task', id: t.id, label: '查看并处理' }],
        }),
        '待处理任务',
      ),
    async action(ctx, _key, id) {
      const t = ctx.cache.rows.find((x: Entity) => x.id === id);
      const d = await R.request('/workbench/tasks/' + t.kind + '/' + t.object_id);
      if (t.kind === 'appointment_confirmation') R.go('appointment', { id: d.record.id });
      else if (t.kind === 'appointment_reschedule')
        R.go('reschedule-review', { id: d.record.appointment_id });
      else if (t.kind === 'appointment_fulfillment')
        R.go('appointment', { id: d.record.appointment.id });
      else if (t.kind === 'clinic_payment') R.go('bill', { id: d.record.id });
      else R.go('notifications');
    },
  },
  appointments: {
    load: (ctx) =>
      list(
        ctx,
        '/appointments',
        ['pending', 'success', 'completed', 'cancelled'],
        appointmentRow,
        '预约管理',
      ),
  },
  appointment: {
    async load(ctx) {
      const a = await detail(ctx, '/appointments/' + ctx.params.id);
      return {
        title: '预约详情',
        notice: a.conflict
          ? '到诊反馈存在冲突，请联系平台处理。'
          : a.restoration_pending
            ? '权益待客户申请恢复，不能重复核销。'
            : a.completion_source === 'system'
              ? '预约时间已过72小时，系统自动完成；未核销不产生获客费。'
              : '请核对客户与预约，治疗完成后再核销。',
        facts: [
          fact('客户', a.customer_name),
          fact('预约手机号', a.phone),
          ...appointmentFacts(a),
          fact(
            '到诊反馈',
            a.patient_arrived_at
              ? '客户已反馈到诊'
              : a.clinic_absent_at
                ? '门诊反馈未到，权益仍占用'
                : '尚未反馈',
          ),
        ],
        rows: (a.reschedules || [])
          .filter((r: Entity) => r.status === 'pending')
          .map((r: Entity) => ({
            id: r.id,
            title: '客户改期待确认',
            lines: ['原时间：' + dateText(r.previous_at), '申请时间：' + dateText(r.proposed_at)],
            actions: [{ key: 'review-reschedule', label: '处理改期' }],
          })),
        actions: appointmentActions(a) as any,
      };
    },
    async action(ctx, key) {
      const a = ctx.cache.object;
      if (key === 'phone') wx.makePhoneCall({ phoneNumber: a.phone });
      else if (key === 'scan-appointment') R.go('scan', { appointment_id: a.id });
      else if (key === 'review-reschedule') R.go('reschedule-review', { id: a.id });
      else if (key === 'appointment-logs') R.go('logs', { id: a.id, type: 'appointment' });
      else R.go('appointment-action', { id: a.id, action: key });
    },
  },
  'appointment-action': {
    async load(ctx) {
      const a = await detail(ctx, '/appointments/' + ctx.params.id);
      const type = ctx.params.action;
      return {
        title:
          (
            {
              confirm: '确认预约',
              cancel: '无法接诊',
              reschedule: '协商改期',
              'report-absent': '患者未到',
              reverse: '撤销错误核销',
            } as Entity
          )[type] || '预约处理',
        facts: appointmentFacts(a),
        fields: ['confirm', 'reschedule'].includes(type)
          ? [
              ...timeFields(),
              ...(type === 'reschedule' ? [field('agreed', '已与客户协商一致', 'checkbox')] : []),
            ]
          : ['cancel', 'reverse'].includes(type)
            ? [field('reason', type === 'cancel' ? '无法接诊原因' : '撤销原因')]
            : [],
        notice:
          type === 'report-absent'
            ? '取消后不释放权益，须由客户在小程序申请恢复。'
            : type === 'reverse'
              ? '仅未完成结算的交易可撤销；特殊补核销撤销后由客户申请恢复权益。'
              : '请与客户沟通后确定日期和时间，不能超过权益有效期。',
        submitLabel: '确认提交',
      };
    },
    async submit(ctx) {
      const a = ctx.cache.object,
        type = ctx.params.action;
      let path = '/appointments/' + a.id + '/' + type,
        data: Entity = { version: a.version };
      if (type === 'confirm') data.scheduled_at = checkTime(ctx.form);
      else if (type === 'reschedule') {
        if (ctx.form.agreed !== true) throw new Error('请确认已经与客户协商一致');
        data = { ...data, proposed_at: checkTime(ctx.form), agreed: true };
      } else if (type === 'cancel') data.reason = required(ctx.form, 'reason', '无法接诊原因');
      else if (type === 'report-absent') data.confirmed = true;
      else if (type === 'reverse') {
        const row = a.redemptions.find((r: Entity) => r.status === 'active');
        if (!row || row.clinic_settled) throw new Error('已结清或无有效核销，不能撤销');
        path = '/redemptions/' + row.id + '/reverse';
        data = { version: row.version, reason: required(ctx.form, 'reason', '撤销原因') };
      } else throw new Error('不支持此操作');
      if (await command(path, data, '确认提交？系统会复核当前预约和账单状态。')) wx.navigateBack();
    },
  },
  'reschedule-review': {
    async load(ctx) {
      const a = await detail(ctx, '/appointments/' + ctx.params.id);
      const r = a.reschedules.find((x: Entity) => x.status === 'pending');
      if (!r) throw new Error('该改期已处理，请返回刷新预约');
      ctx.cache.change = r;
      return {
        title: '确认客户改期',
        facts: [
          ...appointmentFacts(a),
          fact('新意向时间', dateText(r.proposed_at)),
          fact('处理截止', dateText(r.expires_at)),
        ],
        fields: [{ key: 'reason', label: '拒绝原因（拒绝时必填）' }],
        actions: [
          { key: 'approve', label: '同意改期' },
          { key: 'reject', label: '拒绝改期' },
        ],
      };
    },
    async action(ctx, key) {
      const r = ctx.cache.change;
      const approved = key === 'approve';
      if (
        await command(
          '/reschedules/' + r.id + '/review',
          {
            version: r.version,
            approved,
            reason: approved ? '' : required(ctx.form, 'reason', '拒绝原因'),
          },
          approved ? '确认改为客户申请的日期与时间？' : '确认拒绝？原预约时间仍有效。',
        )
      )
        wx.navigateBack();
    },
  },
  fulfillment: {
    load: (ctx) =>
      list(
        ctx,
        '/fulfillment-tasks',
        ['pending', 'conflict', 'closed'],
        (t) => ({
          ...appointmentRow(t.appointment),
          id: t.id,
          title:
            (t.kind === 'supplement' ? '待补核销' : '过期预约') +
            ' · ' +
            t.appointment.customer_name,
          status: statuses[t.status],
        }),
        '过期预约待办',
      ),
  },
  scan: {
    async load(ctx) {
      return {
        title: '扫码核销',
        notice:
          ctx.cache.success ||
          '请扫描客户预约详情的核销二维码，核对信息并确认治疗完成。未核销不记费。',
        actions: [{ key: 'scan-code', label: '扫描核销二维码' }, ...(ctx.params.appointment_id ? [{key:'scan-all',label:'改为扫描其他预约'}] : [])],
        rows: (ctx.cache.candidates || []).map((a: Entity) => ({
          ...appointmentRow(a),
          actions: [{ key: 'quote', id: a.id, label: '核对并核销' }],
        })),
        ...(ctx.cache.quote
          ? {
              facts: [
                fact('客户', ctx.cache.selected.customer_name),
                fact('推广产品', ctx.cache.selected.external_name),
                fact('权益来源', ctx.cache.selected.source_name),
                fact('预约时间', dateText(ctx.cache.selected.scheduled_at)),
                fact('核销数量', ctx.cache.quote.units),
                fact('本次获客费', money(ctx.cache.quote.fee_cents)),
              ],
              fields: [field('treated', '已核实客户身份并完成本次治疗', 'checkbox')],
              submitLabel: '确认核销',
            }
          : {}),
      };
    },
    async action(ctx, key, id) {
      if (key === 'scan-all') { ctx.params={}; ctx.cache={}; ctx.form={}; return; }
      if (key === 'scan-code') {
        ctx.cache.quote = null;
        ctx.cache.success = '';
        const credential = await R.scan();
        const data = await R.request('/redemptions/scan', 'POST', { credential });
        ctx.cache.credential = credential;
        ctx.cache.candidates = data.results.filter(
          (a: Entity) => !ctx.params.appointment_id || a.id === ctx.params.appointment_id,
        );
        if (!ctx.cache.candidates.length) throw new Error('此二维码没有当前门诊可核销的匹配预约');
      } else if (key === 'quote') {
        const a = ctx.cache.candidates.find((x: Entity) => x.id === id);
        if (!a) throw new Error('请重新扫码');
        ctx.cache.quote = await R.request('/redemptions/quote', 'POST', {
          credential: ctx.cache.credential,
          appointment_id: a.id,
        });
        ctx.cache.selected = a;
        ctx.form.treated = false;
      }
    },
    async submit(ctx) {
      if (ctx.form.treated !== true) throw new Error('请核实身份并确认已完成治疗');
      const q = ctx.cache.quote,
        a = ctx.cache.selected;
      if (!q || !a) throw new Error('请重新扫码核对');
      if (
        await command(
          '/redemptions',
          {
            credential: ctx.cache.credential,
            appointment_id: a.id,
            version: q.version,
            confirmed: true,
            quote: q.quote,
          },
          '确认核销 ' + q.units + ' 份，并产生获客费 ' + money(q.fee_cents) + '？',
        )
      ) {
        ctx.cache = { success: '核销成功，已记录本次交易。' };
        ctx.params = {};
        ctx.form = {};
      }
    },
  },
  mine: {
    async load() {
      return {
        title: '我的门诊',
        facts: [
          fact('门诊', R.current()!.membership!.organization_name),
          fact('身份', R.isAdmin() ? '管理员' : '员工'),
        ],
        actions: [
          ...(R.isAdmin()
            ? [
                { key: 'cooperation', label: '合同与推广产品' },
                { key: 'bills', label: '门诊账单' },
              ]
            : []),
          { key: 'membership', label: '切换门诊身份' },
          { key: 'notifications', label: '通知消息' },
          { key: 'privacy', label: '隐私说明' },
          { key: 'logout', label: '退出登录' },
        ],
      };
    },
  },
  bills: { admin: true, load: (ctx) => list(ctx, '/bills', financial, billRow, '门诊账单') },
  bill: {
    admin: true,
    async load(ctx) {
      const b = await detail(ctx, '/bills/' + ctx.params.id);
      const payable = !['settled', 'cancelled', 'no_payment'].includes(b.status);
      return {
        title: '账单详情',
        notice:
          '以平台审核或服务端查单为准；上传凭证、微信客户端回调均不代表已结清。逾期由平台人工处理。',
        facts: [
          fact('状态', statuses[b.status]),
          fact('账单金额', money(b.total_cents)),
          fact('已记付款', money(b.received_cents)),
          fact('剩余应付', money(b.remaining_cents)),
          fact('付款期限', dateText(b.due_at)),
        ],
        actions: [
          { key: 'bill-lines', label: '逐笔交易明细' },
          { key: 'export-bill', label: '下载交易明细Excel' },
          { key: 'receipts', label: '付款凭证与审核进度' },
          { key: 'bill-logs', label: '操作记录' },
          ...(payable
            ? [
                { key: 'receipt', label: '上传付款凭证' },
                { key: 'payment', label: '微信支付' },
                { key: 'bill-feedback', label: '反馈账单问题' },
              ]
            : []),
        ],
      };
    },
    async action(ctx, key) {
      if (key === 'export-bill') await Files.exportBill(ctx.params.id);
      else if (key === 'bill-logs') R.go('logs', { id: ctx.params.id, type: 'clinicbill' });
      else R.go(key, { id: ctx.params.id });
    },
  },
  'bill-lines': {
    admin: true,
    load: (ctx) =>
      list(
        ctx,
        '/bills/' + ctx.params.id + '/lines',
        ['active', 'disabled'],
        (r) => ({
          id: r.id,
          title: r.transaction.external_name,
          status: r.active ? '有效交易' : '已撤销移出',
          lines: [
            r.transaction.customer_name,
            '预约时间：' + dateText(r.transaction.scheduled_at),
            '核销时间：' + dateText(r.transaction.redeemed_at),
            '获客费：' + money(r.amount_cents),
            r.transaction.clinic_settled ? '门诊已结清' : '门诊未结清',
          ],
          actions: [{ key: 'appointment', id: r.transaction.appointment_id, label: '查看预约' }],
        }),
        '账单逐笔交易',
      ),
  },
  receipts: {
    admin: true,
    load: (ctx) =>
      list(
        ctx,
        '/bills/' + ctx.params.id + '/receipts',
        ['pending', 'approved', 'rejected'],
        (r) => ({
          id: r.id,
          title: money(r.amount_cents) + ' · ' + r.payer,
          status: statuses[r.status],
          lines: [dateText(r.paid_at), r.reason || ''],
          actions: r.attachment_ids.map((id: string, i: number) => ({
            key: 'attachment',
            id,
            label: '查看凭证 ' + (i + 1),
          })),
        }),
        '付款凭证',
      ),
  },
  receipt: {
    admin: true,
    async load(ctx) {
      const b = await detail(ctx, '/bills/' + ctx.params.id);
      return {
        title: '提交付款凭证',
        facts: [fact('本次须付清', money(b.remaining_cents))],
        notice: '请上传真实付款凭证，提交后由平台审核；未审核通过不会结清账单。',
        fields: [
          field('payer', '付款方名称'),
          field('reference', '银行流水或付款备注'),
          ...timeFields(),
        ],
        actions: [
          { key: 'upload', label: ctx.cache.attachment ? '重新选择凭证' : '选择付款凭证图片' },
        ],
        rows: ctx.cache.attachment ? attachmentRows([ctx.cache.attachment]) : [],
        submitLabel: '提交平台审核',
      };
    },
    async action(ctx, key) {
      if (key === 'upload') ctx.cache.attachment = await Files.uploadReceipt();
    },
    async submit(ctx) {
      if (!ctx.cache.attachment) throw new Error('请先上传付款凭证');
      const b = ctx.cache.object;
      const { timestamp } = await import('../shared/screens');
      const paid_at = timestamp(ctx.form);
      if (new Date(paid_at).getTime() > Date.now()) throw new Error('付款时间不能晚于当前时间');
      if (
        await command(
          '/bills/' + b.id + '/receipts',
          {
            version: b.version,
            amount_cents: b.remaining_cents,
            paid_at,
            payer: required(ctx.form, 'payer', '付款方名称'),
            reference: required(ctx.form, 'reference', '流水或付款备注'),
            attachment_ids: [ctx.cache.attachment],
          },
          '确认提交付款凭证等待平台审核？',
        )
      )
        wx.navigateBack();
    },
  },
  payment,
  'bill-feedback': {
    admin: true,
    async load(ctx) {
      await detail(ctx, '/bills/' + ctx.params.id);
      return {
        title: '账单问题反馈',
        fields: [field('message', '请说明需要核对的交易或金额')],
        submitLabel: '提交平台核查',
      };
    },
    async submit(ctx) {
      if (
        await command(
          '/bills/' + ctx.params.id + '/feedback',
          { version: ctx.cache.object.version, message: required(ctx.form, 'message', '问题说明') },
          '确认提交账单问题？',
        )
      )
        wx.navigateBack();
    },
  },
  cooperation: {
    admin: true,
    async load(ctx) {
      const c = await detail(ctx, '/organizations/' + org() + '/cooperation');
      return {
        title: '合同与推广产品',
        notice: '三方合同由渠道签订或续签、平台审核；门诊只读查看。',
        rows: [c.current_contract, c.next_contract, c.pending_contract]
          .filter(Boolean)
          .map(contractRow),
        actions: [
          { key: 'contracts', label: '全部合同版本' },
          { key: 'products', label: '门诊推广产品' },
        ],
      };
    },
  },
  contracts: {
    admin: true,
    load: (ctx) =>
      list(
        ctx,
        '/organizations/' + org() + '/contracts',
        [
          'draft',
          'pending',
          'effective',
          'not_started',
          'expired',
          'superseded',
          'rejected',
          'terminated',
        ],
        contractRow,
        '合同版本',
      ),
  },
  contract: {
    admin: true,
    async load(ctx) {
      const c = await detail(ctx, '/contracts/' + ctx.params.id);
      return {
        title: '三方合同',
        facts: [
          fact('合同编号', c.number),
          fact('版本', c.revision),
          fact('状态', statuses[c.display_status] || statuses[c.status]),
          fact('生效日', dateText(c.starts_at)),
          fact('到期日', dateText(c.ends_at)),
          fact('结算周期', c.settlement_cycle === 'weekly' ? '周结' : '月结'),
        ],
        rows: attachmentRows(c.attachment_ids).concat(
          (c.products || []).map((p: Entity) => ({
            id: p.product_id,
            title: p.external_name || p.product?.external_name || '合同推广产品',
            lines: ['合同授权的推广产品'],
            actions: [],
          })),
        ),
        actions: [{ key: 'contract-logs', label: '操作记录' }],
      };
    },
    async action(ctx) {
      R.go('logs', { type: 'contractversion', id: ctx.params.id });
    },
  },
  products: {
    admin: true,
    async load(ctx) {
      const c = await R.request('/organizations/' + org() + '/cooperation');
      const match = /\/clinics\/([a-f0-9-]{36})\/products$/.exec(c.products_endpoint || '');
      if (!match) throw new Error('门诊产品入口暂不可用');
      return list(
        ctx,
        '/clinics/' + match[1] + '/products',
        ['online', 'offline'],
        (p) => ({
          id: p.product_id,
          title: p.external_name,
          status: p.status === 'online' ? '已上线' : '已下线',
          lines: [p.usage_rules],
          actions: [],
        }),
        '门诊推广产品',
      );
    },
  },
  logs: {
    async load(ctx) {
      if (!['appointment', 'clinicbill', 'contractversion'].includes(ctx.params.type))
        throw new Error('记录类型不支持');
      if (ctx.params.type !== 'appointment') R.requireAdmin();
      const data = await R.request(
        '/objects/' +
          ctx.params.type +
          '/' +
          ctx.params.id +
          '/logs?' +
          R.query({ page: ctx.page, page_size: 20 }),
      );
      return {
        title: '操作记录',
        rows: data.results.map((r: Entity) => ({
          id: r.id,
          title: logTitle(r.action),
          lines: [dateText(r.occurred_at), r.actor + ' · ' + r.organization, r.reason || ''],
          actions: [],
        })),
        total: data.total,
        page: ctx.page,
      };
    },
  },
  notifications: {
    load: (ctx) =>
      list(
        ctx,
        '/notifications',
        ['unread', 'read'],
        (n) => ({
          id: n.id,
          title: n.title,
          status: statuses[n.status],
          lines: [dateText(n.created_at)],
          actions: [{ key: 'notification', id: n.id, label: '阅读消息' }],
        }),
        '通知消息',
      ),
    async action(ctx, _key, id) {
      const n = ctx.cache.rows.find((x: Entity) => x.id === id);
      await R.request('/notifications/' + id + '/read', 'POST', {}, true);
      if (n.object_type === 'appointment') R.go('appointment', { id: n.object_id });
      else if (n.object_type === 'clinicbill' && R.isAdmin()) R.go('bill', { id: n.object_id });
      else if (n.contract_version_id && R.isAdmin())
        R.go('contract', { id: n.contract_version_id });
    },
  },
};
function logTitle(action: string): string {
  const labels: Entity = {
    'appointment.confirmed': '确认预约',
    'appointment.cancelled': '取消预约',
    'appointment.clinic_absent': '门诊反馈患者未到',
    'appointment.customer_feedback': '客户到诊反馈',
    'appointment.redeemed': '完成核销',
    'redemption.reversed': '撤销核销',
    'contract.submitted': '提交合同',
    'contract.reviewed': '审核合同',
    'bill.receipt_submitted': '提交付款凭证',
  };
  return labels[action] || '业务操作记录';
}
