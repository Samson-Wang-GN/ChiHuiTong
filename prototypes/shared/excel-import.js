/* REQ-041: bounded XLSX prototype, explicit mapping; never upload real customer data. */
window.PrototypeImport = (() => {
  const h = React.createElement, W = PrototypeWorkflows;
  const {Button, Select, InputNumber, Checkbox, Alert, Upload, Descriptions, Tag} = arco;
  const fields = [['name', '客户姓名'], ['phone', '手机号'], ['quantity', '开卡数量'], ['customerNo', '客户编号（选填）']];
  const aliases = {
    name: ['姓名', '客户姓名', '客户名称', 'name', 'customername'],
    phone: ['手机号', '手机号码', '客户手机', '客户手机号', '客户手机号码', 'mobile', 'phone'],
    quantity: ['开卡数量', '购卡数量', '卡片数量', 'quantity', 'cardcount'],
    customerNo: ['客户编号', '客户编码', '会员编号', 'customerno', 'customerid']
  };
  const norm = v => String(v ?? '').normalize('NFKC').replace(/\s/g, '').toLowerCase();
  const col = i => i < 26 ? String.fromCharCode(65 + i) : 'A' + String.fromCharCode(65 + i - 26);
  const initial = () => ({book: null, file: '', sheet: 0, header: 1, mapping: {}, mode: 'column', uniform: undefined, confirmed: false, confirmedAt: null, saveFormat: false, error: '', notice: '', reading: false});
  const alert = (text, type = 'info') => h(Alert, {content: text, type, style: {marginBottom: 12}});
  const button = (text, onClick, props = {}) => h(Button, {onClick, ...props}, text);

  async function readWorkbook(file) {
    if (!/\.xlsx$/i.test(file.name) || !file.size || file.size > 1024 * 1024) throw Error('请上传1MB以内的.xlsx文件；原型只接受虚构客户资料。');
    const bytes = new Uint8Array(await file.arrayBuffer()), view = new DataView(bytes.buffer), decoder = new TextDecoder();
    let end = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) if (view.getUint32(i, true) === 0x06054b50) { end = i; break; }
    if (end < 0) throw Error('无法读取Excel，请检查文件是否损坏或加密。');
    const count = view.getUint16(end + 10, true), entries = new Map();
    let offset = view.getUint32(end + 16, true), total = 0;
    if (!count || count > 100 || view.getUint16(end + 4, true)) throw Error('工作簿过于复杂或不是支持的.xlsx文件。');
    for (let i = 0; i < count; i++) {
      if (offset + 46 > bytes.length || view.getUint32(offset, true) !== 0x02014b50) throw Error('Excel结构损坏。');
      const n = view.getUint16(offset + 28, true), extra = view.getUint16(offset + 30, true), comment = view.getUint16(offset + 32, true);
      if (offset + 46 + n + extra + comment > bytes.length) throw Error('Excel目录不完整。');
      const path = decoder.decode(bytes.slice(offset + 46, offset + 46 + n)), raw = view.getUint32(offset + 24, true);
      if (entries.has(path) || /(^\/|\.\.|\\)/.test(path) || view.getUint16(offset + 8, true) & 1) throw Error('Excel含不支持的路径或加密内容。');
      total += raw;
      if (raw > 2 * 1024 * 1024 || total > 10 * 1024 * 1024) throw Error('Excel展开内容超出原型上限。');
      entries.set(path, {method: view.getUint16(offset + 10, true), size: view.getUint32(offset + 20, true), raw, local: view.getUint32(offset + 42, true)});
      offset += 46 + n + extra + comment;
    }
    if ([...entries.keys()].some(p => /vbaproject|externallinks/i.test(p))) throw Error('不接受含宏或外部链接的工作簿，请另存为纯数据.xlsx。');
    const cache = new Map();
    async function xml(path, optional = false) {
      if (cache.has(path)) return cache.get(path);
      const e = entries.get(path);
      if (!e) { if (optional) return null; throw Error('Excel缺少工作簿或工作表内容。'); }
      if (e.local + 30 > bytes.length || view.getUint32(e.local, true) !== 0x04034b50) throw Error('Excel文件内容不完整。');
      const start = e.local + 30 + view.getUint16(e.local + 26, true) + view.getUint16(e.local + 28, true);
      if (start + e.size > bytes.length) throw Error('Excel压缩内容不完整。');
      let content = bytes.slice(start, start + e.size);
      if (e.method === 8) {
        const reader = new Blob([content]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader(), chunks = [];
        let size = 0;
        try { for (;;) { const r = await reader.read(); if (r.done) break; size += r.value.length; if (size > 2 * 1024 * 1024) throw Error('Excel解压内容超出原型上限。'); chunks.push(r.value); } }
        finally { await reader.cancel(); }
        content = new Uint8Array(size); let at = 0; for (const chunk of chunks) { content.set(chunk, at); at += chunk.length; }
      } else if (e.method !== 0) throw Error('不支持该Excel压缩格式，请另存为.xlsx。');
      if (content.length !== e.raw) throw Error('Excel内容长度不一致，请重新导出。');
      const text = decoder.decode(content);
      if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw Error('Excel不允许外部实体。');
      const doc = new DOMParser().parseFromString(text, 'application/xml');
      if (doc.querySelector('parsererror')) throw Error('Excel内容损坏，请重新导出。');
      if (doc.getElementsByTagName('f').length) throw Error('文件包含公式，请转换为纯文本或数值后上传。');
      cache.set(path, doc); return doc;
    }
    for (const path of entries.keys()) if (path.endsWith('.rels')) {
      const relationships = await xml(path);
      if ([...relationships.getElementsByTagName('Relationship')].some(r => r.getAttribute('TargetMode') === 'External')) throw Error('工作簿不允许外部链接。');
    }
    const workbook = await xml('xl/workbook.xml'), rels = await xml('xl/_rels/workbook.xml.rels');
    const relationships = [...rels.getElementsByTagName('Relationship')];
    if (relationships.some(r => r.getAttribute('TargetMode') === 'External')) throw Error('工作簿不允许外部链接。');
    const names = [...workbook.getElementsByTagName('sheet')];
    if (!names.length || names.length > 5) throw Error('原型支持1～5个工作表，每次选择一个导入。');
    const shared = await xml('xl/sharedStrings.xml', true);
    const strings = shared ? [...shared.getElementsByTagName('si')].map(s => [...s.getElementsByTagName('t')].map(t => t.textContent).join('')) : [];
    const sheets = [];
    for (const s of names) {
      const relation = relationships.find(r => r.getAttribute('Id') === s.getAttribute('r:id'));
      const target = relation?.getAttribute('Target') || '', path = target.startsWith('/') ? target.slice(1) : 'xl/' + target;
      if (!/^xl\/worksheets\/[^/]+\.xml$/.test(path) || !/\/worksheet$/.test(relation?.getAttribute('Type') || '')) throw Error('不支持该工作表关联，请另存为普通Excel工作表。');
      const doc = await xml(path), sourceRows = [...doc.getElementsByTagName('row')];
      if (sourceRows.length > 220 || doc.getElementsByTagName('mergeCell').length) throw Error('原型每表最多220行，且不支持合并单元格；请整理为平面客户表。');
      const used = new Set(), rows = sourceRows.map((r, i) => {
        const number = Number(r.getAttribute('r') || i + 1), cells = [], occupied = new Set();
        if (!Number.isSafeInteger(number) || number < 1 || used.has(number)) throw Error('Excel行号无效或重复。');
        used.add(number);
        for (const c of r.getElementsByTagName('c')) {
          const ref = /^([A-Z]+)(\d+)$/.exec(c.getAttribute('r') || ''); let index = 0;
          if (!ref || Number(ref[2]) !== number) throw Error('Excel单元格位置无效。');
          for (const ch of ref[1]) index = index * 26 + ch.charCodeAt(0) - 64;
          if (index < 1 || index > 30 || occupied.has(index)) throw Error('原型最多30列，且不接受重复单元格。');
          occupied.add(index);
          const type = c.getAttribute('t'), value = c.getElementsByTagName('v')[0]?.textContent || '';
          if (type === 'e') throw Error('Excel包含错误单元格，请修正后上传。');
          if (type === 's' && (!/^\d+$/.test(value) || Number(value) >= strings.length)) throw Error('Excel文本索引损坏。');
          cells[index - 1] = type === 's' ? strings[Number(value)] : type === 'inlineStr' ? [...c.getElementsByTagName('t')].map(t => t.textContent).join('') : value;
        }
        return {number, cells};
      }).sort((a, b) => a.number - b.number);
      sheets.push({name: s.getAttribute('name') || '工作表', rows});
    }
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return {sheets, sha256: [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('')};
  }

  function headers(sheet, header) { return sheet?.rows.find(r => r.number === header)?.cells || []; }
  function guess(values) {
    const mapping = {};
    for (const [key] of fields) {
      const found = Array.from(values, (v, i) => aliases[key].includes(norm(v)) ? String(i) : null).filter(v => v !== null);
      if (found.length === 1) mapping[key] = found[0];
    }
    if (values.filter(v => /手机|电话|mobile|phone/i.test(norm(v))).length > 1) delete mapping.phone;
    return mapping;
  }
  function bestHeader(sheet) {
    return sheet.rows.reduce((best, row) => {
      const score = Object.keys(guess(row.cells)).length;
      return score > best.score ? {number: row.number, score} : best;
    }, {number: sheet.rows[0]?.number || 1, score: -1});
  }
  const formatKey = org => 'chihuitong-import-formats-v1-' + encodeURIComponent(org);
  const signature = values => JSON.stringify(Array.from(values, norm).sort());
  function formats(org) {
    const raw = localStorage.getItem(formatKey(org));
    if (!raw) return [];
    const saved = JSON.parse(raw);
    if (!Array.isArray(saved) || saved.some(s => !s || typeof s.signature !== 'string' || !s.labels || !['column', 'uniform'].includes(s.mode))) throw Error('已保存格式不可读；请取消保存格式，手动确认本次对应关系。');
    return saved;
  }
  function configure(book, file, sheetIndex, header, org) {
    const sheet = book.sheets[sheetIndex], values = headers(sheet, header);
    const next = {...initial(), book, file, sheet: sheetIndex, header, mapping: guess(values)};
    try {
      const saved = formats(org), match = saved.find(s => s.signature === signature(values));
      if (match && new Set(Array.from(values, norm)).size === values.length) {
        const mapping = {};
        for (const [key] of fields) if (match.labels[key]) {
          const index = values.findIndex(v => norm(v) === match.labels[key]); if (index >= 0) mapping[key] = String(index);
        }
        next.mapping = mapping; next.mode = match.mode;
        next.notice = '已套用本机构保存的格式；请检查样例并再次确认。统一数量须本次填写。';
      } else next.notice = saved.length ? '文件格式变化或列名重复，未套用保存格式；请重新确认对应关系。' : '已按列名识别；未识别或存在歧义的字段请手动选择。';
    } catch (e) { next.notice = e.message; }
    return next;
  }
  function problem(d) {
    if (!d.book || d.reading) return '请先上传并完成读取。';
    const values = headers(d.book.sheets[d.sheet], d.header), used = new Set();
    for (const [key, label] of fields) {
      if (key === 'quantity' && d.mode === 'uniform') continue;
      const v = d.mapping[key];
      if (v === undefined || v === '') { if (key !== 'customerNo') return '请选择“' + label + '”对应的Excel列。'; else continue; }
      if (!/^\d+$/.test(v) || Number(v) >= values.length || !norm(values[Number(v)])) return '列对应关系无效，请重新选择。';
      if (used.has(v)) return '不同字段不能对应同一个Excel列。'; used.add(v);
    }
    if (d.mode === 'uniform' && (!Number.isSafeInteger(Number(d.uniform)) || Number(d.uniform) < 1 || Number(d.uniform) > 500)) return '请明确填写每人1～500张的统一数量，不能留空。';
    return '';
  }
  function items(d) {
    if (!d.book) return [];
    const sheet = d.book.sheets[d.sheet];
    return sheet.rows.filter(r => r.number > d.header && r.cells.some(v => String(v ?? '').trim())).map(r => {
      const get = key => d.mapping[key] === undefined || d.mapping[key] === '' ? '' : String(r.cells[Number(d.mapping[key])] ?? '');
      return {id: 'ROW-' + r.number, sheetName: sheet.name, sourceRow: r.number, customerNo: get('customerNo'), name: get('name'), phone: get('phone'), quantity: d.mode === 'uniform' ? d.uniform : get('quantity'), rawName: get('name'), rawPhone: get('phone')};
    });
  }
  function snapshot(d) {
    const values = headers(d.book.sheets[d.sheet], d.header);
    return {version: 1, file: d.file, sha256: d.book.sha256, sheet: d.book.sheets[d.sheet].name, header: d.header, mode: d.mode === 'uniform' ? '全部客户统一数量' : '按Excel列读取', uniform: d.mode === 'uniform' ? Number(d.uniform) : null, fields: fields.filter(([key]) => !(key === 'quantity' && d.mode === 'uniform')).map(([key, field]) => ({field, column: d.mapping[key] === undefined || d.mapping[key] === '' ? '未选择' : col(Number(d.mapping[key])) + ' · ' + values[Number(d.mapping[key])]})), confirmedAt: d.confirmedAt};
  }
  function saveFormat(d, org) {
    const values = headers(d.book.sheets[d.sheet], d.header), labels = {};
    if (new Set(Array.from(values, norm)).size !== values.length) throw Error('重名列不能保存为自动复用格式；取消勾选后仍可确认本次映射。');
    fields.forEach(([key]) => { if (d.mapping[key] !== undefined && d.mapping[key] !== '' && !(key === 'quantity' && d.mode === 'uniform')) labels[key] = norm(values[Number(d.mapping[key])]); });
    const id = signature(values), next = formats(org).filter(s => s.signature !== id);
    next.push({signature: id, labels, mode: d.mode, header: d.header});
    localStorage.setItem(formatKey(org), JSON.stringify(next.slice(-10)));
  }
  function sample(kind) {
    if (kind === 'uniform') return [{name: '福利名单', rows: [['客户姓名', '客户手机'], ['客户甲（演示）', '13800000011'], ['客户乙（演示）', '13800000012']]}];
    if (kind === 'error') return [{name: '异常名单', rows: [['客户姓名', '手机号码', '购卡数量'], ['错误姓名（演示）', '13800000011', 2], ['客户乙（演示）', '13800000012', 0], ['客户丙（演示）', '13800000013', 1], ['客户丙（演示）', '13800000013', 1], ['客户丁（演示）', '无效手机号', 1]]}];
    return [{name: '填写说明', rows: [['说明'], ['全部是虚构客户，仅供列识别演示']]}, {name: '九月福利名单', rows: [['机构福利客户名单（演示）'], [], ['客户手机', '购卡数量', '客户名称', '会员编号'], ['+86 138 0000 0011', 2, '客户甲（演示）', 'C001'], ['13800000012', 1, '客户乙（演示）', 'C002']]}];
  }

  function Editor({value: d, onChange, pages}) {
    const generation = React.useRef(0);
    React.useEffect(() => () => { generation.current++; }, []);
    const update = change => onChange(old => ({...old, ...change, confirmed: false, confirmedAt: null, error: ''}));
    const load = async file => {
      const token = ++generation.current;
      onChange({...initial(), reading: true});
      try {
        const book = await readWorkbook(file);
        if (token !== generation.current) return false;
        let index = 0; book.sheets.forEach((s, i) => { if (bestHeader(s).score > bestHeader(book.sheets[index]).score) index = i; });
        onChange(configure(book, file.name, index, bestHeader(book.sheets[index]).number, PROTOTYPE.org));
      } catch (e) { if (token === generation.current) onChange({...initial(), error: '读取失败：' + e.message}); }
      return false;
    };
    const sheet = d.book?.sheets[d.sheet], values = headers(sheet, d.header), raw = items(d);
    const checked = PrototypeSales.inspect(raw, pages), invalid = checked.filter(r => r.error);
    const configError = d.book ? problem(d) : '';
    const countError = d.book && !configError && (raw.length < 1 || raw.length > 200) ? '选中工作表须包含1～200条客户明细。' : '';
    const quantity = checked.reduce((n, r) => n + (Number.isSafeInteger(r.quantity) && r.quantity > 0 ? r.quantity : 0), 0);
    const limitError = quantity > 500 ? '开卡总数超过原型500张上限，请拆分文件。' : '';
    const confirm = () => {
      const error = configError || countError || limitError;
      if (error) { onChange(old => ({...old, error})); return; }
      try { if (d.saveFormat) saveFormat(d, PROTOTYPE.org); }
      catch (e) { onChange(old => ({...old, error: '保存格式失败：' + e.message})); return; }
      onChange(old => ({...old, confirmed: true, confirmedAt: new Date().toISOString(), error: '', notice: old.saveFormat ? '本机构格式已保存；只保存列结构，不保存客户样例。' : old.notice}));
    };
    const options = Array.from(values, (v, i) => ({value: String(i), label: col(i) + ' · ' + (v || '空列名'), disabled: !norm(v)}));
    const phoneCandidates = options.filter(o => {
      const samples = sheet?.rows.filter(r => r.number > d.header && String(r.cells[Number(o.value)] ?? '').trim()).slice(0, 10) || [];
      return samples.length && samples.every(r => /^1[3-9]\d{9}$/.test(String(r.cells[Number(o.value)]).normalize('NFKC').replace(/[\s()-]/g, '').replace(/^(\+86|0086)/, '')));
    });
    const examples = key => raw.slice(0, 3).map(r => String(r[key] ?? '') || '（空）').join(' / ') || '—';
    return h('div', {className: 'import-editor'},
      alert('仅使用虚构客户资料。支持.xlsx、1MB、最多5个工作表；每次导入一个工作表，最多200条客户、500张卡。'),
      h('h3', null, '1. 上传客户名单'),
      h('div', {className: 'flow-actions'},
        h(Upload, {autoUpload: false, showUploadList: false, beforeUpload: load, accept: '.xlsx', disabled: d.reading}, button(d.reading ? '正在读取' : '上传客户Excel')),
        button('下载客户Excel模板', () => PrototypeExcel.download('记名销售客户模板', [{name: '客户清单', rows: [['客户编号', '姓名', '手机号', '开卡数量'], ['C001', '客户甲（演示）', '13800000011', 2], ['C002', '客户乙（演示）', '13800000012', 1]]}]))),
      h('div', {className: 'flow-actions import-samples'}, h('span', {className: 'muted'}, '快速体验：'),
        ...[['standard', '使用机构格式示例'], ['uniform', '使用缺数量列示例'], ['error', '使用异常名单示例']].map(([kind, text]) => button(text, () => load(new File([PrototypeExcel.workbook(sample(kind))], text + '.xlsx')), {disabled: d.reading}))),
      d.error && alert(d.error, 'error'),
      d.book && h(React.Fragment, null,
        h('div', {className: 'import-file'}, h('strong', null, d.file), h('span', {className: 'muted'}, '已读取 ' + d.book.sheets.length + ' 个工作表，仅导入当前选择')),
        h('div', {className: 'flow-form-grid'},
          W.field('工作表', h(Select, {value: d.sheet, options: d.book.sheets.map((s, i) => ({value: i, label: s.name})), onChange: i => onChange(configure(d.book, d.file, i, bestHeader(d.book.sheets[i]).number, PROTOTYPE.org))})),
          W.field('表头所在行', h(Select, {value: d.header, options: sheet.rows.map(r => ({value: r.number, label: '第 ' + r.number + ' 行 · ' + r.cells.filter(Boolean).join(' / ').slice(0, 80)})), onChange: n => onChange(configure(d.book, d.file, d.sheet, n, PROTOTYPE.org))}))),
        h('h3', null, '2. 确认列对应关系'), d.notice && alert(d.notice),
        !d.mapping.phone && phoneCandidates.length > 0 && alert('内容格式像手机号的候选列：' + phoneCandidates.map(o => o.label).join('、') + '。仅作提示，请人工确认客户手机号列。', 'warning'),
        W.field('开卡数量来源', h(Select, {value: d.mode, options: [{value: 'column', label: '按Excel列读取'}, {value: 'uniform', label: '全部客户统一数量'}], onChange: mode => update({mode})})),
        d.mode === 'uniform' && W.field('每人统一开卡数量（张）', h(InputNumber, {value: d.uniform, min: 1, max: 500, precision: 0, placeholder: '请填写，不自动默认为1', onChange: uniform => update({uniform})})),
        h('div', {className: 'import-mappings'}, ...fields.filter(([key]) => !(key === 'quantity' && d.mode === 'uniform')).map(([key, label]) => h('div', {className: 'import-mapping', key},
          W.field(label + (key === 'customerNo' ? '' : ' *'), h(Select, {value: d.mapping[key], allowClear: key === 'customerNo', placeholder: '请选择Excel列', options, onChange: v => update({mapping: {...d.mapping, [key]: v}})})),
          h('div', {className: 'import-example'}, h(Tag, {color: d.confirmed ? 'green' : d.mapping[key] === undefined || d.mapping[key] === '' ? 'orange' : 'arcoblue'}, d.confirmed ? '已确认' : d.mapping[key] === undefined || d.mapping[key] === '' ? '待选择' : '待核对'), h('span', null, '样例：' + examples(key)))))),
        values.filter(v => /手机|电话|mobile|phone/i.test(norm(v))).length > 1 && alert('存在多个电话相关列，请核对客户手机号，勿选择业务员或联系人电话。', 'warning'),
        h(Checkbox, {checked: d.saveFormat, onChange: saveFormat => update({saveFormat})}, '保存为本机构导入格式'),
        h('div', {className: 'flow-actions'}, button(d.confirmed ? '列对应关系已确认' : '确认列对应关系', confirm, {type: 'primary', disabled: d.confirmed}), d.confirmed && h(Tag, {color: 'green'}, '已确认；修改后需重新确认')),
        (configError || countError || limitError) && alert(configError || countError || limitError, 'warning'),
        h('h3', null, '3. 校验预览'),
        h(Descriptions, {column: 3, data: [{label: '客户人数', value: new Set(checked.filter(r => /^1[3-9]\d{9}$/.test(r.phone)).map(r => r.phone)).size + ' 人（按有效手机号去重）'}, {label: '开卡张数', value: invalid.length || configError || countError || limitError ? '存在异常，暂不确定' : quantity + ' 张'}, {label: '校验明细', value: raw.length + ' 条 / 异常 ' + invalid.length + ' 条'}]}),
        alert(d.mode === 'uniform' ? '当前统一数量：每人 ' + (d.uniform ?? '未填写') + ' 张；不会叠加Excel中的数量。' : '按Excel明细数量开卡；空白、0、负数、小数均不自动补1。'),
        invalid.length > 0 && alert('请修正原Excel后重新上传；异常行不自动删除或合并，整单不能提交。', 'error'),
        h('div', {className: 'flow-actions'}, button('下载错误清单', () => PrototypeExcel.download('记名销售错误清单', [{name: '全部异常明细', rows: [['工作表', '原始行号', '客户姓名', '原手机号', '原开卡数量', '错误原因'], ...invalid.map(r => [r.sheetName, r.sourceRow, r.rawName, r.rawPhone, String(raw.find(x => x.id === r.id)?.quantity ?? ''), r.error])]}]), {disabled: !invalid.length})),
        h(W.RecordList, {key: d.file + d.sheet + d.header + JSON.stringify(d.mapping) + d.mode + d.uniform, items: checked.map(r => ({...r, match: r.status, status: r.error ? '异常' : '校验通过'})), states: ['校验通过', '异常'], tableWidth: 820, columns: [['sourceRow', 'Excel行号'], ['name', '客户姓名'], ['phone', '规范手机号'], ['quantity', '开卡张数'], ['status', '状态'], ['error', '错误原因']]})));
  }
  function Receipt({value}) {
    if (!value) return alert('历史订单未记录列对应关系，不补造导入依据。');
    return h('section', {className: 'import-receipt'}, h('h2', null, 'Excel导入依据'),
      h(Descriptions, {column: 2, border: true, data: [['原文件', value.file], ['工作表', value.sheet], ['表头行', value.header], ['数量规则', value.mode + (value.uniform ? ' · 每人' + value.uniform + '张' : '')], ...value.fields.map(f => [f.field, f.column]), ['文件SHA-256', value.sha256]].map(([label, v]) => ({label, value: v}))}));
  }
  return {initial, readWorkbook, guess, bestHeader, configure, problem, items, snapshot, saveFormat, formatKey, Editor, Receipt};
})();
