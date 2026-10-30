import { config } from './config';
import { Entity, Session } from './model';

let session: Session | null = null;
let generation = 0;
let navigationContext: Entity = {};
export function consumeNavigation(): Entity {
  const value = navigationContext;
  navigationContext = {};
  return value;
}
const retries = new Map<string, string>();
const temporaryFiles = new Set<string>();
export function current(): Session | null {
  return session;
}
export function epoch(): number {
  return generation;
}
export function clearSession(): void {
  session = null;
  generation++;
  retries.clear();
  cleanFiles();
}
export function isAdmin(): boolean {
  return config.audience === 'clinic' && session?.membership?.role === 'admin';
}
export function requireAdmin(): void {
  if (!isAdmin()) throw new Error('仅门诊管理员可查看合同和账单');
}
export function selectMembership(id: string): void {
  const member = session?.memberships?.find((m) => m.id === id);
  if (!session || !member) throw new Error('该门诊身份不可用，请重新登录');
  session.membership = member;
  generation++;
  retries.clear();
  cleanFiles();
}
export function configured(): void {
  if (!/^https:\/\/[a-zA-Z0-9.-]+(?::443)?(?:\/[a-zA-Z0-9_/-]*)?$/.test(config.apiBase))
    throw new Error('小程序服务地址尚未配置，请联系平台');
  if (!/^wx[a-fA-F0-9]{16}$/.test(config.appid))
    throw new Error('小程序账号尚未配置，暂不能进行真实授权');
}
export function endpoint(path: string): string {
  if (
    !path.startsWith('/') ||
    path.includes('..') ||
    /[\\#\r\n]/.test(path) ||
    path.startsWith('//')
  )
    throw new Error('请求路径不合法');
  return config.apiBase.replace(/\/$/, '') + '/api/v1/mini/' + config.audience + path;
}
export function headers(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...(session ? { Authorization: 'Bearer ' + session.token } : {}),
    ...(session?.membership ? { 'X-Membership-ID': session.membership.id } : {}),
  };
}
function safeError(data: any, status: number): Error {
  const error = new Error(
    typeof data?.message === 'string'
      ? data.message
      : status === 401
        ? '登录已失效，请重新授权'
        : '操作未完成，请检查输入或稍后重试',
  ) as Error & { status: number; code?: string };
  error.status = status;
  error.code = data?.code;
  return error;
}
export async function request(
  path: string,
  method: 'GET' | 'POST' = 'GET',
  data?: Entity,
  write = false,
): Promise<any> {
  configured();
  const revision = generation;
  const signature = method + path + JSON.stringify(data || {});
  const header = headers();
  if (write) {
    if (!retries.has(signature))
      retries.set(
        signature,
        Date.now().toString(36) +
          '-' +
          Math.random().toString(36).slice(2) +
          '-' +
          Math.random().toString(36).slice(2),
      );
    header['Idempotency-Key'] = retries.get(signature)!;
  }
  return new Promise((resolve, reject) =>
    wx.request({
      url: endpoint(path),
      method,
      data,
      header,
      timeout: 15000,
      success: (result) => {
        if (revision !== generation) {
          reject(new Error('身份已切换，请重新操作'));
          return;
        }
        if (result.statusCode >= 200 && result.statusCode < 300) {
          retries.delete(signature);
          resolve(result.data);
        } else {
          if (result.statusCode === 401) clearSession();
          if (result.statusCode >= 400 && result.statusCode < 500) retries.delete(signature);
          reject(safeError(result.data, result.statusCode));
        }
      },
      fail: () => reject(new Error('网络连接失败。请保留当前页面，重试相同操作；请勿重复付款')),
    }),
  );
}
export async function login(phoneCode: string): Promise<Session> {
  configured();
  if (!config.privacyReady) throw new Error('隐私说明尚未配置完成，暂不能提交手机号授权');
  const actual = wx.getAccountInfoSync().miniProgram.appId;
  if (actual !== config.appid) throw new Error('当前小程序账号与配置不一致');
  if (!phoneCode) throw new Error('请主动授权手机号后继续');
  const result = await new Promise<WechatMiniprogram.LoginSuccessCallbackResult>(
    (resolve, reject) =>
      wx.login({ success: resolve, fail: () => reject(new Error('微信登录未完成，请重试')) }),
  );
  const data = await request('/login', 'POST', { login_code: result.code, phone_code: phoneCode });
  if (data.audience !== config.audience || typeof data.token !== 'string')
    throw new Error('登录返回身份不匹配');
  clearSession();
  session = data;
  if (data.memberships?.length === 1) selectMembership(data.memberships[0].id);
  return session!;
}
export async function refreshIdentity(): Promise<void> {
  if (!session) throw new Error('请先授权手机号登录');
  const next = await request('/me');
  if (next.audience !== config.audience) {
    clearSession();
    throw new Error('登录身份不匹配');
  }
  const id = session?.membership?.id;
  session = { ...session!, ...next };
  if (config.audience === 'clinic') {
    session!.membership = next.memberships?.find((m: Entity) => m.id === id);
    if (!session!.membership && next.memberships?.length === 1)
      session!.membership = next.memberships[0];
  }
}
export async function logout(): Promise<void> {
  try {
    if (session) await request('/logout', 'POST', {}, true);
  } finally {
    clearSession();
  }
}
export function confirm(content: string): Promise<boolean> {
  return new Promise((resolve) =>
    wx.showModal({
      title: '请确认',
      content,
      success: (r) => resolve(r.confirm),
      fail: () => resolve(false),
    }),
  );
}
export function query(data: Entity): string {
  return Object.entries(data)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(String(v)))
    .join('&');
}
const tabs = ['home', 'benefits', 'appointments', 'mine', 'scan'];
export function go(page: string, values: Entity = {}): void {
  if (!/^[a-z-]+$/.test(page)) throw new Error('页面地址不合法');
  const url = '/pages/' + page + '/index';
  if (tabs.includes(page)) {
    navigationContext = values;
    wx.switchTab({ url });
  } else wx.navigateTo({ url: url + (Object.keys(values).length ? '?' + query(values) : '') });
}
export function pickLocation(): Promise<WechatMiniprogram.GetLocationSuccessCallbackResult> {
  return new Promise((resolve, reject) =>
    wx.getLocation({
      type: 'gcj02',
      success: resolve,
      fail: () => reject(new Error('未获取定位，可输入城市、区域或门诊名称继续搜索')),
    }),
  );
}
export function scan(): Promise<string> {
  return new Promise((resolve, reject) =>
    wx.scanCode({
      onlyFromCamera: true,
      scanType: ['qrCode'],
      success: (r) => resolve(r.result),
      fail: () => reject(new Error('未完成扫码，请重试')),
    }),
  );
}
export function cleanFiles(): void {
  for (const path of temporaryFiles)
    wx.getFileSystemManager().unlink({
      filePath: path,
      fail: () => {
        /* OS may have already cleared temporary files. */
      },
    });
  temporaryFiles.clear();
}
export function download(path: string): Promise<string> {
  configured();
  const revision = generation;
  return new Promise((resolve, reject) =>
    wx.downloadFile({
      url: endpoint(path),
      header: headers(),
      timeout: 15000,
      success: (r) => {
        if (revision !== generation || r.statusCode !== 200) {
          if (r.tempFilePath) {
            temporaryFiles.add(r.tempFilePath);
            cleanFiles();
          }
          reject(new Error('附件不可用或身份已改变'));
        } else {
          temporaryFiles.add(r.tempFilePath);
          resolve(r.tempFilePath);
        }
      },
      fail: () => reject(new Error('附件加载失败，请重试')),
    }),
  );
}
export async function attachment(id: string): Promise<void> {
  if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error('附件编号不合法');
  const file = await download('/files/' + id);
  await new Promise<void>((resolve, reject) =>
    wx.openDocument({
      filePath: file,
      showMenu: false,
      success: () => resolve(),
      fail: () =>
        wx.previewImage({
          urls: [file],
          success: () => resolve(),
          fail: () => reject(new Error('附件无法预览，请在后台查看')),
        }),
    }),
  );
}
