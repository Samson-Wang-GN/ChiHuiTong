(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C;
  if (C.role !== 'clinic') return;
  let target = null,
    root = null,
    generation = 0,
    timer = null,
    controller = null,
    opening = false;
  let expanded = false,
    error = '',
    snapshot = null,
    lastUpdated = '',
    seen = null,
    newIds = new Set();
  const events = new EventTarget();
  const changed = () => {
    events.dispatchEvent(new Event('change'));
    render();
  };
  function render() {
    if (!root) return;
    const count = snapshot?.count;
    const title = !C.actor
      ? '正在登录'
      : error
        ? '预约提醒连接中断'
        : count == null
          ? '正在读取预约'
          : newIds.size
            ? '有 ' + newIds.size + ' 条新预约'
            : count
              ? '有 ' + count + ' 条预约待确认'
              : '暂无待处理预约';
    root.render(
      h(
        'div',
        { className: 'pip-content' },
        h(A.Alert, {
          type: error ? 'error' : count ? 'warning' : 'info',
          content: h(
            'div',
            null,
            h('strong', { 'aria-live': 'polite' }, title),
            newIds.size > 0 && h('div', null, '当前共 ' + count + ' 条待确认'),
          ),
        }),
        error &&
          h('p', { className: 'muted' }, error + '；最后更新 ' + (lastUpdated || '尚未同步')),
        h(
          A.Space,
          { style: { marginTop: 8 } },
          h(
            A.Button,
            { size: 'small', onClick: () => resize(!expanded) },
            expanded ? '收起' : '展开',
          ),
          h(A.Button, { size: 'small', onClick: () => process() }, '待处理任务'),
        ),
        expanded &&
          h(
            A.Tabs,
            { activeTab: 'pending', style: { marginTop: 12 } },
            h(
              A.Tabs.TabPane,
              { key: 'pending', title: '待确认（' + (count ?? '—') + '）' },
              (snapshot?.appointments || [])
                .slice(0, 20)
                .map((row) =>
                  h(
                    'article',
                    { key: row.id, className: 'pip-row' },
                    h(
                      'div',
                      null,
                      h('strong', null, '预约 ' + row.id.slice(-8).toUpperCase()),
                      h(
                        'div',
                        { className: 'muted' },
                        '意向 ' + C.text('requested_at', row.requested_at),
                      ),
                    ),
                    h(
                      A.Button,
                      { size: 'small', type: 'primary', onClick: () => process(row.id) },
                      '去处理',
                    ),
                  ),
                ),
              count > 20 &&
                h('p', { className: 'muted' }, '另有 ' + (count - 20) + ' 条，请到后台查看。'),
              count === 0 && h(A.Empty, { description: '已处理完，请点击收起保留提醒' }),
            ),
          ),
        expanded &&
          h(
            'p',
            { className: 'muted' },
            '关闭窗口会停止本窗提醒；收起不会停止。原后台关闭或电脑休眠时无法持续提醒。',
          ),
      ),
    );
  }
  function process(id) {
    window.focus();
    C.showTasks('appointment_confirmation');
    if (id) C.open('appointment', { id });
  }
  function resize(value) {
    expanded = value;
    try {
      target.resizeTo(value ? 400 : 320, value ? 520 : 150);
    } catch {
      error = '浏览器限制窗口尺寸，请手动调整';
    }
    changed();
  }
  function close() {
    generation++;
    clearTimeout(timer);
    controller?.abort();
    const windowRef = target;
    target = null;
    if (root) {
      root.unmount();
      root = null;
    }
    if (windowRef && !windowRef.closed) windowRef.close();
    opening = false;
    snapshot = null;
    seen = null;
    newIds = new Set();
    expanded = false;
    events.dispatchEvent(new Event('change'));
  }
  async function poll(epoch) {
    if (epoch !== generation || !target || target.closed) return;
    if (!C.actor) {
      render();
      timer = setTimeout(() => poll(epoch), 500);
      return;
    }
    controller = new AbortController();
    try {
      const data = await C.request('/api/v1/appointments/reminder-snapshot', {
        signal: controller.signal,
      });
      if (epoch !== generation) return;
      const current = new Set(data.appointments.map((r) => r.id));
      if (seen === null) seen = new Set(current);
      else
        for (const id of current)
          if (!seen.has(id)) {
            newIds.add(id);
            seen.add(id);
          }
      newIds = new Set([...newIds].filter((id) => current.has(id)));
      snapshot = data;
      error = '';
      lastUpdated = C.text('server_at', data.server_time);
      changed();
    } catch (e) {
      if (epoch !== generation || controller.signal.aborted) return;
      error = e.message;
      changed();
    }
    if (epoch === generation) timer = setTimeout(() => poll(epoch), 5000);
  }
  async function preopen() {
    if (target && !target.closed) {
      target.focus();
      return;
    }
    if (opening) return;
    error = '';
    if (!window.isSecureContext || !window.documentPictureInPicture || window.top !== window) {
      error =
        '当前浏览器不支持独立预约提醒窗，请使用支持文档画中画的桌面浏览器；工作台和短信提醒仍可使用。';
      changed();
      return;
    }
    opening = true;
    const epoch = ++generation;
    changed();
    try {
      const win = await window.documentPictureInPicture.requestWindow({ width: 320, height: 150 });
      if (epoch !== generation) {
        win.close();
        return;
      }
      target = win;
      win.document.title = '齿慧通 · 预约提醒';
      win.document.documentElement.lang = 'zh-CN';
      for (const name of ['arco.min.css', 'style.css']) {
        const link = win.document.createElement('link');
        link.rel = 'stylesheet';
        link.href = new URL('/chihuitong/assets/' + name, location.href).href;
        win.document.head.append(link);
      }
      win.document.body.className = 'pip-document';
      const host = win.document.createElement('div');
      win.document.body.append(host);
      root = ReactDOM.createRoot(host);
      win.addEventListener(
        'pagehide',
        () => {
          if (target === win) close();
        },
        { once: true },
      );
      poll(epoch);
    } catch (e) {
      error = '提醒小窗未能打开（' + e.name + '），请回到工作台点击“开启预约提醒”重试。';
    } finally {
      opening = false;
      changed();
    }
  }
  C.reminder = { preopen, close };
  window.addEventListener('pagehide', close);
  C.ReminderControl = function () {
    const [, update] = React.useReducer((v) => v + 1, 0);
    React.useEffect(() => {
      const fn = () => update();
      events.addEventListener('change', fn);
      return () => events.removeEventListener('change', fn);
    }, []);
    return h(
      C.Panel,
      {
        title: '预约确认提醒',
        extra: h(A.Button, { type: 'primary', loading: opening, onClick: preopen }, '开启预约提醒'),
      },
      h(A.Tag, { color: target ? 'green' : 'gray' }, target ? '提醒小窗已开启' : '提醒小窗未开启'),
      h(
        'span',
        { className: 'muted', style: { marginLeft: 12 } },
        '小窗跨页签显示；新预约更新数量，人工展开 / 收起。',
      ),
      error && h(A.Alert, { type: 'warning', content: error }),
    );
  };
})();
