import { Entity, money, statuses } from '../shared/model';
import * as R from '../shared/runtime';
import { Screen, Context, detail, fact } from '../shared/screens';

async function query(ctx: Context, action = 'query'): Promise<void> {
  if (!ctx.cache.payment) throw new Error('暂无支付记录，请刷新');
  ctx.cache.payment = await R.request(
    '/payments/' + ctx.cache.payment.id + '/' + action,
    'POST',
    { confirmed: true },
    true,
  );
}
async function invoke(ctx: Context): Promise<void> {
  const p = ctx.cache.payment;
  if (p.simulated) {
    await query(ctx);
    return;
  }
  if (p.method && p.method !== 'jsapi')
    throw new Error('此支付单由后台发起，请先查询或关闭原支付单，再从小程序付款');
  const v = p.payment_parameters;
  if (
    p.status !== 'pending' ||
    !v ||
    !['timeStamp', 'nonceStr', 'package', 'signType', 'paySign'].every(
      (key) => typeof v[key] === 'string',
    )
  )
    throw new Error('微信支付尚未就绪，请查询或重试准备支付');
  let error: Error | undefined;
  try {
    await new Promise<void>((resolve, reject) =>
      wx.requestPayment({
        timeStamp: v.timeStamp,
        nonceStr: v.nonceStr,
        package: v.package,
        signType: v.signType,
        paySign: v.paySign,
        success: () => resolve(),
        fail: () => reject(new Error('微信支付未完成，已查询服务端结果，请核对')),
      }),
    );
  } catch (e) {
    error = e as Error;
  }
  await query(ctx);
  if (error && ctx.cache.payment.status !== 'success') throw error;
}
export const payment: Screen = {
  admin: true,
  async load(ctx) {
    const b = await detail(ctx, '/bills/' + ctx.params.id);
    if (!ctx.cache.payment) {
      const history = await R.request('/bills/' + b.id + '/payments?page_size=1');
      ctx.cache.payment = history.results[0] || null;
    }
    const p = ctx.cache.payment;
    const actions: Entity[] = [];
    if (b.status !== 'settled' && b.status !== 'cancelled' && b.status !== 'no_payment') {
      if (!p || p.status === 'closed') actions.push({ key: 'pay', label: '发起微信支付' });
      else if (p.status !== 'success') {
        if (p.status === 'pending' && p.payment_parameters && p.method !== 'native')
          actions.push({ key: 'resume-payment', label: '继续支付' });
        if (p.can_retry_preparation)
          actions.push({ key: 'prepare-payment', label: '重新准备支付' });
        actions.push({ key: 'close-payment', label: '关闭原支付单' });
      }
    }
    if (p) actions.push({ key: 'query-payment', label: '查询付款结果' });
    return {
      title: '微信支付',
      notice: p?.simulated
        ? '当前为验收模拟支付，未产生真实资金往来。'
        : '支付后须由服务端查询确认。结果未知时请先查询，不要重复付款。',
      facts: [
        fact('待付金额', money(b.remaining_cents)),
        fact('账单状态', statuses[b.status]),
        ...(p
          ? [
              fact(
                '支付状态',
                (
                  {
                    creating: '准备中',
                    pending: '待支付',
                    unknown: '结果待核实',
                    success: '支付成功',
                    closed: '已关闭',
                  } as Entity
                )[p.status] || '处理中',
              ),
            ]
          : []),
      ],
      actions: actions as any,
    };
  },
  async action(ctx, key) {
    if (key === 'query-payment') {
      await query(ctx);
      return;
    }
    if (key === 'close-payment') {
      if (await R.confirm('确认关闭原支付单？系统会先核对是否已经付款，不会取消已到账交易。'))
        await query(ctx, 'close');
      return;
    }
    if (key === 'prepare-payment') {
      await query(ctx, 'retry');
      return;
    }
    if (key === 'resume-payment') {
      if (await R.confirm('确认继续本张支付单？不会创建新的支付单。')) await invoke(ctx);
      return;
    }
    if (key !== 'pay') throw new Error('不支持的支付操作');
    if (ctx.cache.payment && ctx.cache.payment.status !== 'closed')
      throw new Error('已有支付单，请先查询或继续原支付单');
    if (!(await R.confirm('确认支付 ' + money(ctx.cache.object.remaining_cents) + '？'))) return;
    ctx.cache.payment = await R.request(
      '/bills/' + ctx.params.id + '/payment',
      'POST',
      { version: ctx.cache.object.version },
      true,
    );
    await invoke(ctx);
  },
};
