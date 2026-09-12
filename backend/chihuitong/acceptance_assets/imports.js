(function () {
  'use strict';
  const C = window.CHT,
    { h, A } = C,
    base = '/api/v1/';
  Object.assign(C.names, {
    total_rows: '客户明细行数',
    processed_rows: '已校验行数',
    error_rows: '异常行数',
    total_cards: '开卡总张数',
    mapping_digest: '列对应确认摘要',
    failure_code: '读取 / 校验异常',
    sheet: '工作表',
    header_row: '表头行',
    quantity_mode: '数量读取方式',
    uniform_quantity: '每位客户统一张数',
  });
  Object.assign(C.labels, {
    queued: '等待读取',
    mapping: '待确认列',
    validating: '正在校验',
    validated: '校验完成',
    confirmed: '已确认',
    valid: '校验通过',
    invalid: '异常',
    column: '读取数量列',
    uniform: '使用统一数量',
  });
  const fields = [
    'name',
    'phone',
    'quantity',
    'resource_customer_no',
    'gender',
    'age',
    'occupation',
  ];
  const fieldLabel = (key) =>
    key === 'name'
      ? '客户姓名'
      : key === 'phone'
        ? '客户手机号'
        : key === 'quantity'
          ? '开卡张数'
          : C.names[key];
  function letters(index) {
    let text = '';
    for (let n = index + 1; n; n = Math.floor((n - 1) / 26))
      text = String.fromCharCode(65 + ((n - 1) % 26)) + text;
    return text;
  }
  function Rows({ id }) {
    return h(C.List, {
      path: base + 'imports/' + id + '/rows',
      columns: [
        { title: 'Excel原行号', dataIndex: 'row_number', width: 120 },
        ...fields.map((key) => ({
          title: fieldLabel(key),
          width: 150,
          render: (_, r) => C.text(key, r.normalized[key] ?? r.raw[key]),
        })),
        C.column('status'),
        {
          title: '异常原因',
          width: 250,
          render: (_, r) => (r.errors || []).map((e) => e.message).join('；'),
        },
      ],
    });
  }
  C.ImportReceipt = function ({ id }) {
    const q = C.useQuery(base + 'imports/' + id),
      r = q.data;
    return h(
      'div',
      null,
      h(C.Error, { error: q.error, retry: q.reload }),
      r &&
        h(
          'div',
          null,
          h(C.Facts, {
            data: r,
            fields: ['id', 'status', 'total_rows', 'error_rows', 'total_cards', 'failure_code'],
          }),
          h(
            C.Panel,
            { title: '已确认的导入依据' },
            h(C.Facts, {
              data: r.configuration,
              fields: ['sheet', 'header_row', 'quantity_mode', 'uniform_quantity'],
            }),
            h(A.Table, {
              rowKey: 'field',
              pagination: false,
              columns: [
                { title: '系统字段', dataIndex: 'field', render: fieldLabel },
                { title: '原Excel列', dataIndex: 'column' },
              ],
              data: Object.entries(r.configuration?.mapping || {}).map(([field, index]) => ({
                field,
                column:
                  letters(index) +
                  ' · ' +
                  (r.preview?.[r.configuration.sheet]?.[r.configuration.header_row - 1]?.[index] ||
                    '空表头'),
              })),
            }),
          ),
          h(C.Panel, { title: '导入明细' }, h(Rows, { id })),
          C.role === 'resource' &&
            r.status === 'confirmed' &&
            h(
              A.Button,
              {
                onClick: () =>
                  C.form({
                    title: '保存机构导入格式',
                    fields: [{ name: 'name', label: '格式名称' }],
                    hint: '只保存列结构，不保存客户样例；下次相同表头会自动匹配。',
                    onSubmit: (v) => C.api(base + 'import-formats', 'POST', { batch_id: id, ...v }),
                  }),
              },
              '保存为机构格式',
            ),
        ),
    );
  };
  C.ImportEditor = function ({ value, onChange, prepareRef }) {
    const [assets, setAssets] = React.useState([]),
      [id, setId] = React.useState(value?.id || ''),
      [current, setCurrent] = React.useState(value || null),
      [sheet, setSheet] = React.useState(value?.configuration?.sheet || ''),
      [header, setHeader] = React.useState(value?.configuration?.header_row || 1),
      [mapping, setMapping] = React.useState(value?.configuration?.mapping || {}),
      [quantityMode, setQuantityMode] = React.useState(
        value?.configuration?.quantity_mode || 'column',
      ),
      [quantity, setQuantity] = React.useState(value?.configuration?.uniform_quantity || null),
      [dirty, setDirty] = React.useState(false),
      [busy, setBusy] = React.useState(false),
      [matching, setMatching] = React.useState(false),
      [error, setError] = React.useState(null),
      [ambiguous, setAmbiguous] = React.useState({}),
      [recognition, setRecognition] = React.useState(null);
    const keys = React.useRef(new Map()),
      initial = React.useRef(''),
      generation = React.useRef(0),
      mounted = React.useRef(true);
    const q = C.useQuery(id ? base + 'imports/' + id : null);
    React.useEffect(
      () => () => {
        mounted.current = false;
        generation.current += 1;
        prepareRef.current = null;
      },
      [],
    );
    React.useEffect(() => {
      if (!q.data || q.data.id !== id) return;
      setCurrent(q.data);
      if (initial.current !== id && q.data.sheets.length) {
        const config = q.data.configuration?.sheet ? q.data.configuration : q.data.recommendation;
        setSheet(config?.sheet || q.data.sheets[0].name);
        setHeader(config?.header_row || 1);
        setMapping(config?.mapping || {});
        setAmbiguous(config?.ambiguous || {});
        setQuantityMode(config?.quantity_mode || 'column');
        setQuantity(config?.uniform_quantity || null);
        setRecognition(q.data.recommendation);
        initial.current = id;
      }
    }, [q.data, id]);
    React.useEffect(() => {
      if (!id || !['queued', 'validating'].includes(current?.status)) return;
      const timer = setInterval(q.reload, 1500);
      return () => clearInterval(timer);
    }, [id, current?.status]);
    async function mutate(path, body) {
      const signature = path + JSON.stringify(body);
      if (!keys.current.has(signature)) keys.current.set(signature, crypto.randomUUID());
      return C.api(path, 'POST', body, keys.current.get(signature));
    }
    function changed(fn) {
      generation.current += 1;
      fn();
      setDirty(true);
      setError(null);
      onChange(null);
    }
    async function upload(ids) {
      const run = ++generation.current;
      setAssets(ids);
      setId('');
      setCurrent(null);
      setMapping({});
      setAmbiguous({});
      setRecognition(null);
      initial.current = '';
      setDirty(true);
      setError(null);
      onChange(null);
      if (!ids.length) {
        setMatching(false);
        return;
      }
      setMatching(true);
      try {
        const batch = await mutate(base + 'imports', { asset_id: ids[0] });
        if (!mounted.current || run !== generation.current) return;
        setId(batch.id);
        setCurrent(batch);
      } catch (e) {
        if (mounted.current && run === generation.current) setError(e);
      } finally {
        if (mounted.current && run === generation.current) setMatching(false);
      }
    }
    async function selectSource(nextSheet, nextHeader) {
      const run = ++generation.current;
      setSheet(nextSheet);
      setHeader(nextHeader);
      setMapping({});
      setAmbiguous({});
      setDirty(true);
      setRecognition(null);
      setError(null);
      setMatching(true);
      onChange(null);
      try {
        const result = await C.api(base + 'imports/' + id + '/suggest', 'POST', {
          sheet: nextSheet,
          header_row: nextHeader,
        });
        if (!mounted.current || run !== generation.current) return;
        setMapping(result.mapping);
        setAmbiguous(result.ambiguous);
      } catch (e) {
        if (mounted.current && run === generation.current) setError(e);
      } finally {
        if (mounted.current && run === generation.current) setMatching(false);
      }
    }
    const preview = current?.preview?.[sheet] || [],
      headers = preview[header - 1] || [],
      selected = Object.fromEntries(
        Object.entries(mapping).filter(
          ([field, index]) =>
            index !== undefined && (quantityMode !== 'uniform' || field !== 'quantity'),
        ),
      );
    function issue(field) {
      if (field === 'quantity' && quantityMode === 'uniform')
        return Number.isInteger(quantity) && quantity > 0 && quantity <= 100000
          ? ''
          : '请填写每位客户的开卡数量（正整数）';
      const index = mapping[field];
      if (index === undefined)
        return ['name', 'phone', 'quantity'].includes(field)
          ? ambiguous[field]?.length
            ? '有多个候选列，请选择正确的一列'
            : '未匹配，请选择原文件中的对应列'
          : '';
      if (Object.values(selected).filter((v) => v === index).length > 1)
        return '此列已对应其他字段，请重新选择';
      return '';
    }
    const problems = fields.filter((field) => issue(field)),
      hasPreview = !!headers.length && current?.status !== 'queued',
      ready = hasPreview && !matching;
    async function prepare() {
      if (!ready) throw new Error('请先上传文件，等待自动读取和匹配完成');
      if (problems.length) {
        const message = '请先补全列对应关系：' + problems.map(fieldLabel).join('、');
        setError(new Error(message));
        throw new Error(message);
      }
      const run = generation.current;
      const ensureCurrent = () => {
        if (!mounted.current || run !== generation.current)
          throw new Error('文件或列配置已变化，请重新点击下一步');
      };
      setBusy(true);
      setError(null);
      try {
        let batch = current;
        if (dirty || !['validated', 'confirmed', 'validating'].includes(batch.status)) {
          batch = await mutate(base + 'imports/' + id + '/mapping', {
            version: batch.version,
            sheet,
            header_row: header,
            mapping: selected,
            quantity_mode: quantityMode,
            ...(quantityMode === 'uniform' ? { uniform_quantity: quantity } : {}),
          });
          ensureCurrent();
          setDirty(false);
          setCurrent((v) => ({ ...v, ...batch }));
        }
        const deadline = Date.now() + 90000;
        while (batch.status === 'validating' && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          ensureCurrent();
          batch = await C.api(base + 'imports/' + id);
          ensureCurrent();
          setCurrent(batch);
        }
        if (batch.status === 'validating')
          throw new Error('名单仍在校验，请稍后再点下一步，无需重复上传');
        if (!['validated', 'confirmed'].includes(batch.status))
          throw new Error('文件校验未完成，请检查提示或重新上传文件');
        if (batch.error_rows > 0)
          throw new Error(
            '有 ' + batch.error_rows + ' 行数据需要修改，请查看下方异常明细，修正文件后重新上传',
          );
        if (batch.status !== 'confirmed') {
          batch = await mutate(base + 'imports/' + id + '/confirm', {
            version: batch.version,
            mapping_digest: batch.mapping_digest,
          });
          ensureCurrent();
        }
        const result = { ...current, ...batch };
        setCurrent(result);
        setDirty(false);
        onChange(result);
        return result;
      } catch (e) {
        if (mounted.current && run === generation.current) setError(e);
        throw e;
      } finally {
        if (mounted.current) setBusy(false);
      }
    }
    prepareRef.current = prepare;
    const options = headers.map((text, index) => ({
      value: index,
      label: letters(index) + ' · ' + String(text || '空表头'),
    }));
    function mappingTable(list) {
      return h(A.Table, {
        className: 'import-mapping',
        pagination: false,
        rowKey: 'field',
        size: 'small',
        data: list.map((field) => ({ field })),
        columns: [
          {
            title: '客户资料字段',
            width: 155,
            render: (_, r) =>
              fieldLabel(r.field) +
              (['name', 'phone', 'quantity'].includes(r.field) ? '（必填）' : '（选填）'),
          },
          {
            title: '对应原文件列',
            width: 300,
            render: (_, r) =>
              h(
                'div',
                null,
                h(A.Select, {
                  value: mapping[r.field],
                  allowClear: true,
                  disabled:
                    busy || matching || (r.field === 'quantity' && quantityMode === 'uniform'),
                  error: !!issue(r.field),
                  placeholder:
                    r.field === 'quantity' && quantityMode === 'uniform'
                      ? '使用下方统一数量'
                      : '请选择原文件列',
                  options,
                  onChange: (index) =>
                    changed(() => setMapping((v) => ({ ...v, [r.field]: index }))),
                  'aria-label': fieldLabel(r.field) + '对应列',
                }),
                h(
                  'div',
                  {
                    style: {
                      color: issue(r.field) ? 'rgb(var(--danger-6))' : 'var(--color-text-3)',
                      fontSize: 12,
                      marginTop: 4,
                    },
                    role: issue(r.field) ? 'alert' : undefined,
                  },
                  issue(r.field) ||
                    (r.field === 'quantity' && quantityMode === 'uniform'
                      ? '每位客户 ' + quantity + ' 张'
                      : mapping[r.field] !== undefined
                        ? '已匹配，可调整'
                        : '未匹配，不导入此项'),
                ),
              ),
          },
          {
            title: '样例值',
            width: 190,
            render: (_, r) =>
              mapping[r.field] === undefined
                ? '—'
                : preview
                    .slice(header, header + 2)
                    .map((row) => String(row[mapping[r.field]] ?? ''))
                    .join(' / '),
          },
        ],
        scroll: { x: 645 },
      });
    }
    return h(
      'div',
      { className: 'import-editor' },
      h(A.Alert, {
        type: 'info',
        content:
          '上传后自动匹配列名。请核对下方预览；有未匹配项时选择对应列，再点击底部“下一步”。支持 .xlsx。',
      }),
      h(C.FileInput, {
        purpose: 'sales_excel',
        multiple: false,
        value: assets,
        onChange: upload,
        disabled: busy,
      }),
      h(C.Error, { error: error || q.error, retry: id ? q.reload : () => upload(assets) }),
      current?.status === 'failed' &&
        h(A.Alert, {
          type: 'error',
          content: '文件读取或校验未完成。请检查文件内容，删除当前文件后重新上传；不会沿用之前的名单。',
        }),
      (matching || current?.status === 'queued') &&
        h(A.Spin, {
          loading: true,
          tip: '正在读取文件并自动匹配列名…',
          style: { width: '100%', minHeight: 100 },
        }),
      hasPreview &&
        h(
          'div',
          null,
          h(
            C.Panel,
            { title: '原文件预览 · 前10条数据' },
            h(
              'p',
              { className: 'muted' },
              '工作表：' +
                sheet +
                '；表头：第 ' +
                header +
                ' 行。' +
                (recognition?.saved_format
                  ? '已自动应用本机构相同表头的已确认格式。'
                  : '已自动识别常见列名。'),
            ),
            recognition?.alternatives > 0 &&
              h(A.Alert, {
                type: 'warning',
                content: '发现多个可能的客户表，已选当前工作表，请核对；可展开下方设置切换。',
              }),
            h(A.Table, {
              className: 'import-preview',
              rowKey: 'rowNumber',
              pagination: false,
              size: 'small',
              columns: [
                { title: '原行号', dataIndex: 'rowNumber', width: 76, fixed: 'left' },
                ...headers.map((title, index) => ({
                  title: letters(index) + ' · ' + String(title || '空表头'),
                  dataIndex: 'c' + index,
                  width: 155,
                  ellipsis: true,
                })),
              ],
              data: preview.slice(header, header + 10).map((row, i) => ({
                rowNumber: header + i + 1,
                ...Object.fromEntries(
                  headers.map((_, index) => ['c' + index, String(row[index] ?? '')]),
                ),
              })),
              scroll: { x: Math.max(650, 76 + headers.length * 155) },
              noDataElement: h(A.Empty, { description: '此表头下没有数据，请检查工作表或表头行' }),
            }),
          ),
          h(
            C.Panel,
            { title: '核对列对应关系' },
            h(A.Alert, {
              type: problems.length ? 'warning' : 'success',
              content: problems.length
                ? '需要确认：' + problems.map(fieldLabel).join('、') + '。请在下方选择原文件列。'
                : '必填项已匹配，核对无误后点击底部“下一步”。',
            }),
            mappingTable(['name', 'phone', 'quantity']),
            h(
              A.Space,
              { wrap: true, style: { margin: '12px 0' } },
              h(
                A.Checkbox,
                {
                  checked: quantityMode === 'uniform',
                  disabled: busy || matching,
                  onChange: (checked) =>
                    changed(() => setQuantityMode(checked ? 'uniform' : 'column')),
                },
                '不读取数量列，每位客户使用统一数量',
              ),
              quantityMode === 'uniform' &&
                h(A.InputNumber, {
                  value: quantity,
                  min: 1,
                  max: 100000,
                  precision: 0,
                  disabled: busy || matching,
                  onChange: (v) => changed(() => setQuantity(v)),
                  placeholder: '请输入每人张数',
                  'aria-label': '每位客户开卡数量',
                }),
            ),
            h(
              A.Collapse,
              { bordered: false },
              h(
                A.Collapse.Item,
                { name: 'optional', header: '可选客户资料（自动匹配，可展开调整）' },
                mappingTable(fields.slice(3)),
                h(
                  'p',
                  { className: 'muted' },
                  '资源方客户编号仅留存，不参与系统关联；性别、年龄、职业只补充空缺。',
                ),
              ),
              h(
                A.Collapse.Item,
                { name: 'source', header: '工作表与表头设置（识别不准确时调整）' },
                h(
                  A.Space,
                  { wrap: true },
                  h(A.Select, {
                    value: sheet,
                    disabled: busy,
                    'aria-label': '工作表',
                    onChange: (v) => selectSource(v, 1),
                    style: { width: 240 },
                    options: (current.sheets || []).map((s) => ({
                      value: s.name,
                      label: s.name + '（' + s.rows + '行）',
                    })),
                  }),
                  h(A.InputNumber, {
                    value: header,
                    disabled: busy,
                    'aria-label': '表头行',
                    min: 1,
                    max: Math.min(20, current.sheets?.find((s) => s.name === sheet)?.rows || 20),
                    prefix: '表头第',
                    suffix: '行',
                    onChange: (v) => {
                      if (Number.isInteger(v) && v > 0) selectSource(sheet, v);
                    },
                  }),
                ),
              ),
            ),
          ),
          (busy || current.status === 'validating') &&
            h(A.Alert, {
              type: 'info',
              content: '正在校验全部客户数据，通过后自动进入下一步，请稍候…',
            }),
          !dirty &&
            ['validated', 'confirmed', 'failed'].includes(current.status) &&
            h(
              C.Panel,
              { title: '全表校验结果' },
              h(C.Facts, {
                data: current,
                fields: [
                  'total_rows',
                  'processed_rows',
                  'error_rows',
                  'total_cards',
                  'failure_code',
                ],
              }),
              current.error_rows > 0 &&
                h(
                  A.Button,
                  {
                    onClick: () =>
                      C.download(
                        base + 'imports/' + id + '/errors.xlsx',
                        '导入异常清单.xlsx',
                      ).catch(setError),
                  },
                  '下载错误 Excel',
                ),
              h(Rows, { id }),
            ),
        ),
    );
  };
})();
