// API projections are server-authorized JSON. Render only explicit field whitelists.
export type Entity = Record<string, any>;
export interface Session { token: string; audience: string; memberships?: Entity[]; membership?: Entity; profile?: Entity; has_pending_benefits?: boolean; needs_profile_completion?: boolean; }
export interface Action { key: string; label: string; id?: string; value?: string; danger?: boolean; }
export interface Row { id: string; title: string; status?: string; lines: string[]; actions: Action[]; }
export interface Field { key: string; label: string; type?: string; value?: string | boolean; required?: boolean; options?: string[]; }
export interface View { title: string; notice?: string; rows?: Row[]; actions?: Action[]; fields?: Field[]; facts?: {label: string; value: string}[]; tabs?: {key: string; label: string}[]; total?: number; page?: number; qr?: string; latitude?: number; longitude?: number; markers?: Entity[]; image?: string; submitLabel?: string; }
export const statuses: Record<string,string> = { all:'全部', pending:'待确认', success:'预约成功', completed:'已完成', cancelled:'已取消', pending_claim:'待领取', available:'可预约', reserved:'预约占用', restoring:'待恢复', used:'已使用', expired:'已过期', invalid:'已失效', frozen:'已冻结', pending_payment:'待付款', payment_review:'凭证待审核', disputed:'待核查', overdue:'已逾期', settled:'已结清', no_payment:'无需付款', approved:'审核通过', rejected:'已退回', unread:'未读', read:'已读', resolved:'已处理', conflict:'待核查', closed:'已关闭', active:'有效', reversed:'已撤销', effective:'生效中' };
export const money = (v: unknown) => (Number(v || 0) / 100).toFixed(2) + '元';
Object.assign(statuses,{draft:'草稿',not_started:'待生效',superseded:'历史版本',terminated:'已终止',disabled:'已移出',online:'已上线',offline:'已下线',processed:'已处理'});
export function dateText(v: unknown): string {
  if (!v) return '未确定';
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) return String(v);
  const value = new Date(String(v)).getTime();
  return Number.isFinite(value) ? new Date(value + 8*3600000).toISOString().slice(0,16).replace('T',' ') : '未确定';
}
export function appointmentRow(a: Entity): Row { return {id:a.id,title:a.external_name || a.clinic_name || '预约', status:statuses[a.status] || a.status, lines:[a.clinic_name || '', a.customer_name || '', '预约时间：'+dateText(a.scheduled_at || a.requested_at), a.completion_source === 'system' ? '系统自动完成，不代表已治疗或已核销' : ''], actions:[{key:'appointment',id:a.id,label:'预约详情'}]}; }
