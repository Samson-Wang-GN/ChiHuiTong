import * as R from '../shared/runtime';
export async function exportBill(id: string): Promise<void> {
  R.requireAdmin();
  if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error('账单编号不合法');
  if (!(await R.confirm('下载账单全部交易明细，包含客户资料，请妥善保管，勿向无关人员转发。')))
    return;
  const file = await R.download('/bills/' + id + '/export.xlsx?status=all');
  await new Promise<void>((resolve, reject) =>
    wx.openDocument({
      filePath: file,
      fileType: 'xlsx',
      showMenu: true,
      success: () => resolve(),
      fail: () => reject(new Error('Excel已下载但无法预览，请在门诊后台下载')),
    }),
  );
}
export async function uploadReceipt(): Promise<string> {
  R.requireAdmin();
  const chosen = await new Promise<WechatMiniprogram.ChooseMediaSuccessCallbackResult>(
    (resolve, reject) =>
      wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sizeType: ['compressed'],
        success: resolve,
        fail: () => reject(new Error('未选择付款凭证')),
      }),
  );
  const file = chosen.tempFiles[0];
  if (!file || file.size > 5 * 1024 * 1024) throw new Error('请选择不超过5MB的图片');
  R.configured();
  const revision = R.epoch();
  const header = R.headers();
  delete header['Content-Type'];
  return new Promise((resolve, reject) =>
    wx.uploadFile({
      url: R.endpoint('/files'),
      filePath: file.tempFilePath,
      name: 'file',
      formData: { purpose: 'payment' },
      header,
      timeout: 30000,
      success: (r) => {
        try {
          if (revision !== R.epoch()) throw new Error('身份已改变');
          const data = JSON.parse(r.data);
          if (r.statusCode !== 201) throw new Error(data.message || '凭证上传失败，请重新选择');
          resolve(data.id);
        } catch (e) {
          reject(e);
        }
      },
      fail: () => reject(new Error('凭证上传失败，请重试')),
    }),
  );
}
