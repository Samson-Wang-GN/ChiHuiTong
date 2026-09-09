(() => {
  const h = React.createElement;
  const {useState,useEffect} = React;
  const {Tabs,Button,Input,InputNumber,Select,Tag,Table,Alert,Breadcrumb,Menu,Drawer,Modal,Form,Checkbox,Message,Descriptions,Empty,DatePicker,TimePicker,Upload,Avatar} = arco;
  const config = window.PROTOTYPE;
  const workflow = window.PrototypeWorkflows;
  workflow.prepare(config);
  const operations=window.PrototypeOperations,tasks=window.PrototypeTasks;
  operations.prepare(config);
  const sales=window.PrototypeSales;
  sales.prepare(config);
  const overview=window.PrototypeOverview;
  overview.prepare(config);
  const overdue=window.PrototypeOverdue;
  overdue.prepare(config);
  const institutions=window.PrototypeInstitutions;
  if(institutions)institutions.prepare(config);
  const migrateInstitutions=p=>{const next=institutions?institutions.migrate(p):p;return management.migrate(clinicInfo?clinicInfo.migrate(next):next)};
  const clinicInfo=window.PrototypeClinicInfo;
  if(clinicInfo){clinicInfo.prepare(config);config.version='0.26';}
  const management=window.PrototypeManagement;management.prepare(config);config.version='0.29';
  const storageKey = 'chihuitong-prototype-v1-' + config.role;
  const clone = value => JSON.parse(JSON.stringify(value));
  const pageRows = (pages,id) => {const p=pages.find(p=>p.id===id);return (p?.rows||[]).filter(r=>!p.recordType||r.type===p.recordType)};
  const activeContract = c => c && ['已生效','即将到期'].includes(c.status) && c.start<='2026-09-07' && c.end>='2026-09-07';
  const schemeList = pages => pageRows(pages,'schemes').length?pageRows(pages,'schemes'):(config.schemeCatalog||[]);
  const allocation = (r,fee) => PrototypeRules.share(fee,r)/100;
  const termView = (r,pages) => {
    const c=pageRows(pages,'contracts').find(c=>c.id===r.contract);
    const s=schemeList(pages).find(s=>operations.sameProduct(pages,s.id||s.name,r.scheme));
    return {...r,party:c?.party||'合同主体待补充',fee:s?.fee,payout:s?allocation(r,s.fee).toFixed(2):'—',access:r.status!=='已启用'?'授权已停用':!activeContract(c)?'合同未生效或已到期':s?.status!=='已启用'?'方案未启用':'可开展新业务'};
  };
  const allowedScheme = (pages,name) => config.role==='clinic'?(config.authorizations||[]).some(r=>operations.sameProduct(pages,r.scheme,name)&&r.status==='已启用'&&activeContract({...r,status:r.contractStatus})&&schemeList(pages).some(s=>operations.sameProduct(pages,s.name,name)&&s.status==='已启用')):pageRows(pages,'contractSchemes').some(r=>operations.sameProduct(pages,r.scheme,name)&&termView(r,pages).access==='可开展新业务');
  const route = () => {const id=location.hash.slice(1).split('?')[0]||'workbench';return institutions&&['contracts','contractSchemes'].includes(id)?'institutions':['platform','resource'].includes(config.role)&&['imports','orders','cards'].includes(id)?'sales':id==='credit'?'bills':config.role!=='platform'&&id==='contractSchemes'?'contracts':config.role==='channel'&&['clinicContracts','offers'].includes(id)?'clinics':id};
  const scope = () => {const p=new URLSearchParams(location.hash.split('?')[1]||'');p.delete('floating');return p;};
  // 合并新页面定义与已有演示记录，不使用缓存中的旧动作/表单覆盖新版配置。
  const restore = stored => config.pages.map(p=>{
    let old=Array.isArray(stored)&&stored.find(o=>o.id===p.id);
    if(!old&&p.legacyPage&&Array.isArray(stored)){
      const legacy=stored.find(o=>o.id===p.legacyPage);
      if(legacy)old={rows:legacy.rows.filter(r=>r.type===p.recordType)};
    }
    if(!old)return clone(p);
    const rows=old.rows.map(r=>{const item={...clone(p.rows.find(n=>n.id===r.id)||{}),...r};if(institutions&&p.id==='contracts'&&!r.institutionId)delete item.institutionId;return item;});
    for(const r of p.rows)if(!rows.some(o=>o.id===r.id))rows.push(clone(r));
    if(p.id==='contracts')for(const r of rows)if(!r.party)r.party=p.rows.find(n=>n.id===r.id)?.party;
    if(p.id==='schemes')for(const r of rows)for(const key of ['split','resourceShare','channelShare','platformShare'])delete r[key];
    return {...clone(p),rows};
  });
  const badge = value => h(Tag,{color:/逾期|冻结|拒绝|异常|失效/.test(value)?'red':/待|到期|暂停/.test(value)?'orange':/成功|已生效|正常|已结|完成|已上线|已寄送/.test(value)?'green':/取消|下线|停用|回滚|撤销/.test(value)?undefined:'arcoblue'},value);
  function App(){
    const [fullPages,setPages] = useState(()=>{try{const raw=localStorage.getItem(storageKey);if(raw&&!localStorage.getItem(storageKey+'-before-0.29'))localStorage.setItem(storageKey+'-before-0.29',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.27'))localStorage.setItem(storageKey+'-before-0.27',raw);if(raw&&clinicInfo&&!localStorage.getItem(storageKey+'-before-0.26'))localStorage.setItem(storageKey+'-before-0.26',raw);if(raw&&clinicInfo&&!localStorage.getItem(storageKey+'-before-0.25'))localStorage.setItem(storageKey+'-before-0.25',raw);if(raw&&institutions&&!localStorage.getItem(storageKey+'-before-0.24'))localStorage.setItem(storageKey+'-before-0.24',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.18'))localStorage.setItem(storageKey+'-before-0.18',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.19'))localStorage.setItem(storageKey+'-before-0.19',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.20'))localStorage.setItem(storageKey+'-before-0.20',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.21'))localStorage.setItem(storageKey+'-before-0.21',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.23'))localStorage.setItem(storageKey+'-before-0.23',raw);if(raw&&!localStorage.getItem(storageKey+'-before-0.22'))localStorage.setItem(storageKey+'-before-0.22',raw);if(raw&&config.role==='platform'&&!localStorage.getItem(storageKey+'-before-self-statement-removal'))localStorage.setItem(storageKey+'-before-self-statement-removal',raw);return migrateInstitutions(overdue.migrate(sales.migrate(operations.migrate(workflow.migrate(restore(JSON.parse(raw)))))))}catch{Message.warning('本地演示记录读取失败，已加载样例；旧数据未删除。');return migrateInstitutions(overdue.migrate(sales.migrate(operations.migrate(workflow.migrate(clone(config.pages))))))}});
    const [identityVersion,setIdentityVersion]=useState(0);
    const pages=management.project(fullPages);
    const [pageId,setPageId] = useState(route);
    const [routeHash,setRouteHash] = useState(location.hash);
    const [query,setQuery] = useState('');
    const [status,setStatus] = useState('全部');
    const [pageNumber,setPageNumber] = useState(1);
    const [pageSize,setPageSize] = useState(8);
    useEffect(()=>setPageNumber(1),[pageId,status,query,routeHash]);
    const [detail,setDetail] = useState(null);
    const [institutionTask,setInstitutionTask]=useState(null);
    const [operation,setOperation] = useState(null);
    const [draft,setDraft] = useState({});
    const [viewState,setViewState] = useState('正常');
    const [loggedIn,setLoggedIn] = useState(true);
    const [form] = Form.useForm();
    const institutionForm=institutions&&operation&&(!!operation.institutionId||operation.page.id==='institutions');
    const isLongForm=operation&&(operation.page.id==='contractSchemes'||operation.action.fields?.length>7||institutionForm&&operation.action.create);
    const formWidth=institutionForm?760:720;
    useEffect(()=>{const changed=()=>{setRouteHash(location.hash);setPageId(route());setInstitutionTask(null);setQuery('');setStatus('全部');setDetail(null);setOperation(null)};window.addEventListener('hashchange',changed);return()=>window.removeEventListener('hashchange',changed)},[]);
    useEffect(()=>{if(config.role!=='clinic')return;const id=new URLSearchParams(routeHash.split('?')[1]||'').get('floating');if(id){const p=pages.find(p=>p.id==='appointments'),row=p?.rows.find(r=>r.id===id);if(row)setDetail({page:p,row});}},[routeHash]);
    const current = pages.find(page=>page.id===pageId);
    const save = next => {try{next=management.merge(fullPages,pages,next)}catch(e){Message.error(e.message);return}next=management.record(fullPages,next);next=migrateInstitutions(overdue.migrate(sales.migrate(operations.migrate(workflow.migrate(next)))));tasks.record(pages,next);setPages(next);try{localStorage.setItem(storageKey,JSON.stringify(next))}catch{Message.warning('浏览器未允许保存，关闭页面后演示记录将重置')}};
    const navigate = id => {setPageId(id.split('?')[0]);location.hash=id;setQuery('');setStatus('全部');setViewState('正常');setDetail(null)};
    const matchedRows = current ? pageRows(pages,current.id).map(row=>current.id==='contractSchemes'?termView(row,pages):row).filter(row=>[...scope()].every(([k,v])=>row[k]===v)&&Object.values(row).some(value=>String(value).toLowerCase().includes(query.toLowerCase()))) : [];
    const rows=matchedRows.filter(row=>status==='全部'||row.status===status);
    const baseline=config.pages.find(p=>p.id===pageId);
    const statusDefaults={appointments:['待确认','成功','完成','取消'],contracts:['草稿','待审核','已审核待生效','已生效','即将到期','已到期','审核不通过','已终止']};
    const tabStates=['全部',...new Set([...(current?.statuses||statusDefaults[pageId]||[]),...(baseline?.rows||[]).map(r=>r.status),...(baseline?.actions||[]).flatMap(a=>[...(a.when||[]),a.next]),baseline?.create?.next,...(current?.rows||[]).map(r=>r.status)].filter(Boolean))];
    const tabCount=s=>matchedRows.filter(r=>s==='全部'||r.status===s).length;
    const begin = (action,row,page=current,context={}) => {
      if(institutions&&['contracts','contractSchemes'].includes(page.id)){
        const contract=page.id==='contracts'?row:pageRows(pages,'contracts').find(c=>c.id===row?.contract);
        const institution=pageRows(pages,'institutions').find(i=>i.id===context.institutionId)||institutions.owner(pages,contract);
        if(!institution){Message.error('请从机构管理选择机构后办理。');return}
        context={...context,institutionId:institution.id};
        if(action.link==='contractSchemes'){setDetail(null);location.hash=institutions.url(institution.id,'products',row.id);return}
      }
      if(action.link){setDetail(null);location.hash=action.link+'?'+action.filterKey+'='+encodeURIComponent(row[action.filterFrom]);return}
      if(page.id==='offers'&&action.next==='已上线'&&!allowedScheme(pages,row.scheme)){Message.error('当前渠道合同未授权该方案，不能上线优惠。');return}
      form.resetFields();const initial={...row,...action.defaults,...(action.create?Object.fromEntries([...scope()].filter(([key])=>(action.fields||[]).some(f=>f.key===key))):{})};
      if(context.institutionId&&page.id==='contracts'&&action.create){const i=pageRows(pages,'institutions').find(i=>i.id===context.institutionId);Object.assign(initial,{party:i.name,type:institutions.type(i),institutionId:i.id});}
      if(context.contractId&&page.id==='contractSchemes'&&action.create)initial.contract=context.contractId;
      for(const field of action.fields||[]){if(field.type==='number'&&typeof initial[field.key]!=='number')delete initial[field.key]}
      form.setFieldsValue(initial);setDraft(initial);setDetail(null);setOperation({action,row,page,...context,initialValues:clone(initial)});
    };
    const permitted = (action,row) => (action.label!=='同意客户改期'||row.changeStatus==='待确认')&&(!action.when || action.when.includes(row.status))&&(!action.types||action.types.includes(row.type));
    const optionsFor = field => institutions&&operation?.institutionId&&operation.page.id==='contracts'&&field.key==='party'?[pageRows(pages,'institutions').find(i=>i.id===operation.institutionId).name]:field.dynamic==='partnerContracts'?(institutions&&operation?.institutionId?institutions.contracts(pages,operation.institutionId):pageRows(pages,'contracts')).filter(c=>['平台—资源方','平台—渠道公司'].includes(c.type)).map(c=>({value:c.id,label:c.id+' · '+c.party})):
      field.dynamic==='schemes'?schemeList(pages).map(s=>({value:s.name,label:s.name+' · '+s.fee+'元/次'})):
      field.dynamic==='authorizedSchemes'?schemeList(pages).filter(s=>allowedScheme(pages,s.name)).map(s=>s.name):
      field.dynamic==='resourceParties'?pageRows(pages,'institutions').filter(r=>['保险公司','银行','经纪代理公司'].includes(r.type)).map(r=>r.name):field.options;
    const allocationError = (next,r) => {
      const c=pageRows(next,'contracts').find(c=>c.id===r.contract),s=schemeList(next).find(s=>operations.sameProduct(pages,s.id||s.name,r.scheme));
      if(!c||!['平台—资源方','平台—渠道公司'].includes(c.type)||!s)return '请选择有效合作方合同与推广产品。';
      if(!['按比例','按金额'].includes(r.mode)||!Number.isFinite(r.value)||r.value<0||(r.mode==='按比例'&&r.value>100)||allocation(r,s.fee)>s.fee)return '分配值无效：比例须在0–100%，本方金额不能超过获客费。';
      const overlap=(a,b)=>a.start<=b.end&&b.start<=a.end;
      for(const other of pageRows(next,'contractSchemes')){
        if(other.id===r.id||!operations.sameProduct(next,other.scheme,r.scheme)||other.status!=='已启用'||r.status!=='已启用')continue;
        const oc=pageRows(next,'contracts').find(c=>c.id===other.contract);
        if(!oc||!overlap(c,oc)||['已终止','审核不通过'].includes(oc.status))continue;
        if(oc.party===c.party&&oc.type===c.type)return '同一合作方在重叠合同期内不能重复授权同一方案。';
        if(oc.type!==c.type&&PrototypeRules.share(s.fee,other)+PrototypeRules.share(s.fee,r)>PrototypeRules.cents(s.fee))return '资源方与渠道方分配合计超过获客费，请调整合同分配。';
      }
      return null;
    };
    const recordAudit = (next,label,id) => {const audit=next.find(page=>page.id==='audit');if(audit)audit.rows.unshift({id:'LOG-'+Date.now(),name:label,subject:id,operator:config.user,time:new Date().toLocaleString('zh-CN',{hour12:false}),status:'已记录'})};
    const execute = async () => {
      try {await form.validate()} catch {return}
      const values=form.getFieldsValue();
      const {action,row,page}=operation;
      if(page.id==='appointments'&&row){const live=pageRows(pages,'appointments').find(a=>a.id===row.id);if(!live||action.when&&!action.when.includes(live.status)){Message.error('预约状态已变化，请刷新后重试');return}if(action.next==='取消'&&live.status==='成功'&&overdue.elapsed(live)>=0){Message.error('预约时间已过，请到过期预约待办记录患者未到，不能直接释放权益');return}if(values.date&&values.time&&Date.parse(values.date+'T'+values.time+':00+08:00')<=Date.parse(overdue.now)){Message.error('新的确认时间必须晚于当前评审时间');return}}

      if(institutions){const error=institutions.guard(pages,operation,values);if(error){Message.error(error);return}if(page.id==='contracts')values.institutionId=operation.institutionId;}
      for(const field of action.fields||[]){if(field.optional&&values[field.key]==null)continue;if(field.type==='number'&&(!Number.isFinite(values[field.key])||values[field.key]<(field.min??0)||(field.integer&&!Number.isInteger(values[field.key])))){Message.error('请填写有效的'+field.label);return}}
      if(action.guard==='unclaimed' && Number(row.claimed)>0){Message.error('已有客户领取，本批次不能整批回滚；可以申请停止剩余未领取权益。');return}
      if(action.guard==='unactivated' && Number(row.activated)>0){Message.error('本订单已有卡片激活，不能整单取消。');return}
      if(values.date && row?.expiry && values.date>row.expiry){Message.error('预约日期不得超过权益到期日 '+row.expiry);return}
      if(action.guard==='contract' && values.start>values.end){Message.error('合同生效日期不得晚于到期日。');return}
      if(action.create&&page.id==='contracts'&&values.type==='平台—资源方'&&pageRows(pages,'contracts').some(c=>c.type==='平台—资源方'&&c.party===values.party)){
        Message.error('该客户资源方已有平台主合同，请进入原合同维护推广产品；续签或变更应保留版本，不另建主合同。');return;
      }
      if(action.create&&page.id==='contracts'&&values.type==='平台—渠道公司'&&pageRows(pages,'contracts').some(c=>c.type===values.type&&c.party===values.party&&!['已终止','审核不通过'].includes(c.status)&&c.start<=values.end&&values.start<=c.end)){Message.error('该渠道已有重叠有效期的合作合同，请维护原合同版本。');return}
      if(page.id==='sources'){
        const owner=values.owner||row?.owner;
        if(!pageRows(pages,'institutions').some(r=>r.name===owner&&['保险公司','银行','经纪代理公司'].includes(r.type))){Message.error('请选择已有客户资源方。');return}
        if(page.rows.some(r=>r.id!==row?.id&&r.owner===owner&&r.name===(values.name||row?.name))){Message.error('该资源方已配置同名来源，请编辑或启用原记录。');return}
      }
      if(config.role==='resource'&&action.create&&['orders','imports'].includes(page.id)&&!allowedScheme(pages,values.scheme)){Message.error('本方有效合同未授权该推广产品。');return}
      if(config.role==='platform'&&['审核入账','审核定价','完成开卡'].includes(action.label)){
        const authorized=pageRows(pages,'contractSchemes').some(t=>operations.sameProduct(pages,t.scheme,row.scheme)&&termView(t,pages).party===row.owner&&termView(t,pages).access==='可开展新业务');
        if(!authorized){Message.error('该资源方有效合同未授权此方案，不能继续审核或开卡。');return}
      }
      if(page.id==='offers'&&action.next==='已上线'&&!allowedScheme(pages,row.scheme)){Message.error('当前渠道合同未授权该方案，不能上线优惠。');return}
      if(action.guard==='receipt' && Number(values.amount)!==Number(row.amount)){Message.error('请核对整张账单金额；不足额可登记付款记录，但不能整体结清。');return}
      if(action.guard==='paid' && Number(values.amount)!==Number(row.amount)){Message.error('确认收款金额必须与订单总额一致。');return}
      if(page.id==='institutions'&&action.create&&(!values.adminName?.trim()||!/^1\d{10}$/.test(values.adminPhone||''))){Message.error('请填写初始管理员姓名及11位登录手机号。');return}
      const next=clone(pages);const target=next.find(item=>item.id===page.id);
      if(page.id==='contractSchemes'){
        const candidate={...row,...values,id:row?.id,status:action.next||row?.status||'已启用'};
        const error=allocationError(next,candidate);if(error){Message.error(error);return}
        values.version=(row?.version||0)+1;
        for(const key of ['party','fee','payout','access'])delete values[key];
      }
      if(page.id==='schemes'&&(action.create||values.name!==undefined)){
        if(!String(values.name||'').trim()||!String(values.externalName||'').trim()||target.rows.some(r=>r.id!==row?.id&&r.name===values.name)){Message.error('请填写两个产品名称，内部名称不能重复。');return}
      }
      if(page.id==='schemes'&&row){
        if(values.name&&values.name!==row.name)values.aliases=[...new Set([...(row.aliases||[]),row.name,values.name])];
        Object.assign(target.rows.find(s=>s.id===row.id),values);
        for(const term of pageRows(next,'contractSchemes')){const error=allocationError(next,term);if(error){Message.error(error);return}}
      }
      if(action.create){target.rows.unshift({id:page.prefix+'-'+Date.now().toString().slice(-7),...values,...(page.id==='institutions'?{adminAccount:{id:'ADMIN-'+Date.now(),name:values.adminName,phone:values.adminPhone,role:'管理员',platformCreated:true,status:'待绑定'}}:{}),status:action.next||'待审核'})}
      else if(row){const item=target.rows.find(item=>item.id===row.id);Object.assign(item,values);if(action.next)item.status=action.next;if(action.label==='同意客户改期')item.changeStatus='已同意';if(page.id==='appointments'&&values.date&&values.time){delete item.change;overdue.rescheduled(item);}if(action.computePrice)item.amount=Number(values.price)*Number(item.quantity);if(action.guard==='unclaimed')item.remaining=0;if(action.stop)item.remaining=0;if(action.toggle)item.status=row.status==='已上线'?'已下线':'已上线';}
      recordAudit(next,action.label,row?.id||'新建记录');
      if(['contractSchemes','sources'].includes(page.id))Object.assign(pageRows(next,'audit')[0],{reason:values.reason||'新增配置',before:JSON.stringify(row||{}),after:JSON.stringify(values)});
      save(next);setOperation(null);setDetail(null);Message.success(action.success||'操作已保存到本组演示数据');
    };
    const download = () => {const columns=current.columns;const escape=value=>'"'+String(value??'').replace(/^[=+@-]/,"'").replace(/"/g,'""')+'"';const csv='\ufeff'+[columns.map(column=>escape(column[1])).join(','),...rows.map(row=>columns.map(column=>escape(row[column[0]])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));const anchor=document.createElement('a');anchor.href=url;anchor.download=config.role+'-'+current.id+'-演示数据.csv';anchor.click();URL.revokeObjectURL(url);Message.success('已导出当前筛选范围的演示数据')};
    const actionsFor = (page,row) => (page.actions||[]).filter(action=>permitted(action,row));
    const splitPreview = term => {
      if(config.role!=='platform')return null;
      const c=pageRows(pages,'contracts').find(c=>c.id===term.contract),s=schemeList(pages).find(s=>operations.sameProduct(pages,s.id||s.name,term.scheme));
      if(!c||!s||!Number.isFinite(term.value)||term.value<0||!['按比例','按金额'].includes(term.mode)||term.mode==='按比例'&&term.value>100)return h(Alert,{type:'info',content:'选择合同、方案和分配值后展示单次核销分配试算。'});
      const own=allocation(term,s.fee);
      const pairs=pageRows(pages,'contractSchemes').filter(r=>operations.sameProduct(pages,r.scheme,term.scheme)&&r.status==='已启用'&&pageRows(pages,'contracts').some(oc=>oc.id===r.contract&&oc.type!==c.type&&activeContract(oc))).map(r=>{
        const other=termView(r,pages),amount=allocation(r,s.fee),left=(PrototypeRules.cents(s.fee)-PrototypeRules.cents(own)-PrototypeRules.cents(amount))/100;
        return {id:r.id,party:other.party,resource:(c.type==='平台—资源方'?own:amount).toFixed(2),channel:(c.type==='平台—渠道公司'?own:amount).toFixed(2),platform:left.toFixed(2),result:left<0?'分配超额':'可分配'};
      });
      return h('section',{className:'detail-section'},h('h3',null,'单次核销分配试算'),h('p',{className:'muted'},'获客费 '+s.fee+' 元 · 本方 '+own.toFixed(2)+' 元；两方四舍五入至分，平台取余额以保持合计一致（已确认）。'),h(Table,{rowKey:'id',size:'small',pagination:false,scroll:{x:580},data:pairs,noDataElement:h(Empty,{description:'尚无可配对合同，需配置另一合作方后校验完整分配'}),columns:[{title:'配对合作方',dataIndex:'party'},{title:'资源方（元）',dataIndex:'resource'},{title:'渠道（元）',dataIndex:'channel'},{title:'平台（元）',dataIndex:'platform'},{title:'校验',dataIndex:'result'}]}));
    };
    const detailPanel = detail && h(Drawer,{title:detail.row.name||detail.row.id,visible:true,width:institutions&&['contracts','contractSchemes'].includes(detail.page.id)?780:640,footer:null,escToExit:!(institutions&&['contracts','contractSchemes'].includes(detail.page.id)),focusLock:true,autoFocus:true,onCancel:()=>setDetail(null)},
      h('div',{className:'status-line'},badge(detail.row.status||'详情'),h('span',{className:'muted'},detail.row.id)),
      h('div',{className:'detail-section'},h(Descriptions,{column:1,border:true,data:Object.entries(detail.row).filter(([key])=>key!=='status'&&!['overdueManaged','overdueTasks','overdueHistory','token','canRedeem'].includes(key)&&!key.startsWith('legacy')).map(([key,value])=>({label:detail.page.columns.find(column=>column[0]===key)?.[1]||({quantity:'单次核销份数',fee:'单次获客费（元）',benefit:'关联权益编号',released:'权益已恢复',redemptionId:'核销编号',conflict:'反馈冲突',completionSource:'完成来源',completionNote:'完成说明',customerPending:'客户待处理',clinicFeedback:'门诊反馈',customerFeedback:'客户反馈',held:'预约占用份数',used:'已核销份数',overdueHistory:'处理历史',overdueTasks:'待办历史',clinicSettlement:'门诊结算状态',clinicBill:'门诊账单',clinicSettledAt:'门诊结清日期',externalName:'外部产品展示名称',productId:'推广产品编号',aliases:'历史内部名称',id:'业务编号',institutionId:'所属机构编号',contact:'预约联系手机号',expiry:'权益到期日',phone:'联系手机号',remaining:'未领取数量',claimed:'已领取数量',activated:'已激活张数',note:'说明',amount:'应付金额',time:'操作时间',days:'有效期天数',source:'来源展示名',resourceShare:'资源方比例',channelShare:'渠道方比例',platformShare:'平台比例',reason:'操作原因',party:'签约主体',attachment:'合同附件',voucher:'凭证',courier:'物流公司',tracking:'物流单号',refund:'退款金额',refundDate:'退款日期',content:'模板内容',paid:'登记付款金额',perCard:'每卡份数',file:'导入文件',hours:'营业时间',terms:'使用条件',subject:'经营主体',license:'营业执照',medical:'医疗机构执业许可证',agreed:'已协商一致',confirmed:'已确认'}[key]||({version:'规则版本',owner:'所属资源方',before:'变更前记录',after:'变更后记录',authorization:'渠道合同授权'}[key])||key),value:key==='value'&&detail.row.mode?String(value)+(detail.row.mode==='按比例'?'%':' 元/次'):typeof value==='boolean'?(value?'是':'否'):String(value)}))})),
      detail.page.detailNote&&h(Alert,{type:'info',content:detail.page.detailNote}),
      detail.page.id==='contractSchemes'&&splitPreview(detail.row),
      h('div',{className:'detail-actions'},...actionsFor(detail.page,detail.row).map(action=>h(Button,{key:action.label,type:action.danger?'outline':'primary',status:action.danger?'danger':undefined,onClick:()=>begin(action,detail.row,detail.page)},action.label))));
    const fieldInput = field => field.options||field.dynamic?h(Select,{options:optionsFor(field),placeholder:'请选择'+field.label,disabled:(operation?.page.id==='contractSchemes'&&!!operation.row&&['contract','scheme'].includes(field.key))||(!!operation?.institutionId&&operation.page.id==='contracts'&&['party','type'].includes(field.key))}):field.type==='date'?h(DatePicker,{style:{width:'100%'},format:'YYYY-MM-DD'}):field.type==='time'?h(TimePicker,{style:{width:'100%'},format:'HH:mm'}):field.type==='file'||field.type==='excel'?h(Input,{readOnly:true,placeholder:'选择演示文件',suffix:h(Upload,{accept:field.type==='excel'?'.xlsx,.xls':'.pdf,.png,.jpg',showUploadList:false,autoUpload:false,beforeUpload:file=>{if(field.type==='excel'&&!/\.(xlsx|xls)$/i.test(file.name)){Message.error('请选择 Excel 文件');return false}form.setFieldsValue({[field.key]:file.name});return false}},h(Button,{size:'mini'},'选择文件'))}):field.type==='number'?h(InputNumber,{min:field.min??0,precision:field.integer?0:2,style:{width:'100%'},placeholder:'请输入'+field.label}):field.type==='checkbox'?h(Checkbox,null,field.label):field.type==='textarea'?h(Input.TextArea,{autoSize:{minRows:3,maxRows:5},placeholder:'请输入'+field.label}):h(Input,{placeholder:field.placeholder||'请输入'+field.label});
    const closeForm=()=>{const values=form.getFieldsValue();const changed=institutionForm?(operation.action.fields||[{key:'reason'}]).some(f=>JSON.stringify(values[f.key]??'')!==JSON.stringify(operation.initialValues?.[f.key]??'')):form.isFieldsTouched();if(changed)Modal.confirm({title:'离开当前表单？',content:'本次填写尚未提交，离开将放弃修改。',onOk:()=>setOperation(null)});else setOperation(null)};
    const modal = operation&&h(isLongForm?Drawer:Modal,{title:operation.action.label,visible:true,maskClosable:false,escToExit:!institutionForm,width:formWidth,style:{width:isLongForm?formWidth:520,maxWidth:'calc(100vw - 32px)'},onCancel:closeForm,onOk:execute,okText:operation.action.submit||operation.action.label,cancelText:'取消',unmountOnExit:true},
      h(Alert,{className:'form-hint',type:operation.action.danger?'warning':'info',content:operation.action.hint||'请核对本次操作信息，提交后保留操作记录。'}),
      operation.row&&h('p',{className:'muted'},'当前记录：'+operation.row.id),
      h(Form,{form,layout:'vertical',onValuesChange:(_,all)=>setDraft(all)},...(operation.action.fields||[{key:'reason',label:'操作说明',type:'textarea'}]).map(field=>h(Form.Item,{key:field.key,field:field.key,label:field.type==='checkbox'?undefined:field.label,triggerPropName:field.type==='checkbox'?'checked':'value',rules:field.optional?[]:field.type==='checkbox'?[{validator:(value,callback)=>value?callback():callback('请确认后继续')}]:[{required:true,message:'请填写'+field.label}]},fieldInput(field)))),operation.page.id==='contractSchemes'&&splitPreview({...operation.row,...draft}));
    const workbench = () => h(tasks.Workbench,{pages,navigate});
    const listContent = () => h(React.Fragment,null,
      h('div',{className:'toolbar'},h('span',{className:'muted'},'共 '+rows.length+' 条'),h(Input.Search,{placeholder:'搜索编号、名称或关键字',value:query,onChange:setQuery,allowClear:true,style:{width:300}}),h(Button,{onClick:()=>{setQuery('');setStatus('全部');setPageNumber(1)}},'重置'),current.export&&h(Button,{onClick:()=>Modal.confirm({title:'导出当前范围？',content:'仅导出本角色及当前筛选后的演示数据。',onOk:download})},'导出数据')),
      viewState==='加载中'?h(Table,{columns:[],data:[],loading:true}):viewState==='加载失败'?h('div',{className:'empty-help'},h(Alert,{type:'error',title:'数据加载失败',content:'请重试，已填写的信息将保留。'}),h(Button,{onClick:()=>setViewState('正常'),style:{marginTop:16}},'重新加载')):h(Table,{rowKey:'id',size:'default',border:false,stripe:false,scroll:{x:current.width||1000},pagination:{current:Math.min(pageNumber,Math.max(1,Math.ceil(rows.length/pageSize))),pageSize,showTotal:true,sizeCanChange:true,onChange:(number,size)=>{setPageNumber(size!==pageSize?1:number);setPageSize(size)}},noDataElement:h(Empty,{description:'没有符合条件的记录，请调整筛选条件'}),data:viewState==='空状态'?[]:rows,columns:[...current.columns.map(([key,title])=>({dataIndex:key,title,width:key==='name'?200:undefined,align:/amount|fee|quantity|claimed|remaining/.test(key)?'right':'left',render:(value,row)=>key==='status'?badge(value):key==='value'&&row.mode?String(value)+(row.mode==='按比例'?'%':' 元/次'):key==='name'?h('div',null,value,h('div',{className:'row-subtitle'},row.id)):value??'—'})),{title:'操作',fixed:'right',width:current.actions?.length?220:80,render:(_,row)=>h('div',{className:'detail-actions',style:{marginTop:0,gap:0}},h(Button,{type:'text',size:'small',onClick:()=>setDetail({row,page:current})},'详情'),...actionsFor(current,row).slice(0,2).map(action=>h(Button,{key:action.label,size:'small',type:'text',status:action.danger?'danger':undefined,onClick:()=>begin(action,row)},action.label)))}]}));
    const listPage = () => h(React.Fragment,null,
      h('div',{className:'page-heading'},h('div',null,h('h1',null,current.title),h('p',null,current.description)),h('div',{className:'detail-actions',style:{marginTop:0}},...(current.create?[h(Button,{key:'create',type:'primary',onClick:()=>begin(current.create,null)},current.create.label)]:[]))),
      current.notice&&h(Alert,{type:current.noticeType||'info',content:current.notice}),
      [...scope()].length>0&&h('div',{className:'detail-actions'},h(Tag,{color:'arcoblue'},'当前范围：'+[...scope()].map(([,v])=>v).join(' / ')),h(Button,{type:'text',onClick:()=>navigate(current.id)},'查看全部')),
      h('section',{className:'panel'},h(Tabs,{className:'status-tabs',type:'line',activeTab:status,onChange:setStatus,overflow:'scroll',headerPadding:false,destroyOnHide:true,animation:false},...tabStates.map(s=>h(Tabs.TabPane,{key:s,title:s+'（'+tabCount(s)+'）'},s===status?listContent():null)))));
    if(!loggedIn)return h(PrototypeRules.Login,{title:config.title,org:config.org,onLogin:()=>{const actor=management.session();if(['resource','channel'].includes(config.role)&&(!actor||actor.status==='已停用')){Message.error('当前演示账号已停用');return}setLoggedIn(true)}});
    return h(React.Fragment,null,h('header',{className:'shell-header'},h('div',{className:'brand'},h('span',{className:'brand-mark'},'齿'),'齿慧通',h('span',{className:'role-name'},config.title)),h('div',{className:'header-right'},h(Tag,null,'交互原型'),h(management.Switch,{pages:fullPages,onChange:()=>{setIdentityVersion(v=>v+1);setDetail(null);setOperation(null);setInstitutionTask(null);setLoggedIn(true);navigate('workbench')}}),h('span',{className:'org-label'},config.org),h(Avatar,{size:28,style:{background:'rgb(var(--primary-6))'}},(management.session()?.name||config.user).slice(0,1)),h('span',null,management.session()?.role||config.user),h(Button,{type:'text',onClick:()=>setLoggedIn(false)},'退出'))),
      h('aside',{className:'sidebar'},h('div',{className:'org-block'},h('strong',null,config.org),h('span',{className:'muted'},config.scope)),h(Menu,{selectedKeys:[pageId],onClickMenuItem:navigate},h(Menu.Item,{key:'workbench'},'工作台'),...pages.filter(p=>!p.hidden).map(page=>h(Menu.Item,{key:page.id},page.title)))),
      h('main',{className:'workspace',key:identityVersion},h(Breadcrumb,null,h(Breadcrumb.Item,null,config.title),h(Breadcrumb.Item,null,current?.title||'工作台')),config.role==='clinic'&&window.ClinicFloating&&h(ClinicFloating.Workbench,{pages,save,onOpen:id=>{const route=id?'appointments?floating='+encodeURIComponent(id):'tasks?type=appointments';if(location.hash==='#'+route&&id){const p=pages.find(p=>p.id==='appointments');setDetail({page:p,row:p.rows.find(r=>r.id===id)});}else navigate(route);}}),['channel','resource'].includes(config.role)&&management.session()?.role==='业务员'&&h(Alert,{type:'info',content:'当前仅显示本人关联数据；未确定归属的旧数据不开放。收益仅本人明细，整张结算单由机构管理员处理。'}),current?(current.custom==='orgAccounts'?h(management.Accounts,{pages,save}):current.custom==='institutions'?h(institutions.View,{pages,onBegin:begin,onDetail:(page,row)=>setDetail({page,row}),termView,viewState,onRetry:()=>setViewState('正常')}):current.custom==='overdue'?h(overdue.View,{pages,save}):current.custom==='overview'?h(overview.View,{pages,viewState,onRetry:()=>setViewState('正常')}):current.custom==='sales'?h('div',{className:'workflow'},h(sales.View,{pages,save})):current.custom==='tasks'?h(tasks.View,{pages,save,onGeneric:(page,row)=>{if(institutions&&['institutions','contracts'].includes(page.id)){const i=page.id==='institutions'?row:institutions.owner(pages,row);if(i){setInstitutionTask({id:i.id,section:page.id==='contracts'?'contracts':'info',contract:page.id==='contracts'?row.id:undefined});return}Message.error('历史合同尚未匹配唯一机构，请先核对机构资料。');return}setDetail({page,row})}}):current.custom==='statements'?h('div',{className:'workflow'},h('h1',null,current.title),h(operations.Statements,{pages,save})):current.custom?h(workflow.View,{key:current.id,current,pages,save}):listPage()):workbench(),h('div',{className:'prototype-note'},'齿慧通 · 独立角色原型 · 所有机构、客户和业务记录均为虚构演示数据'),h('div',{className:'review-controls'},h('span',{className:'muted'},'评审工具'),h(Select,{size:'small',value:viewState,onChange:setViewState,style:{width:130},options:['正常','加载中','空状态','加载失败']}),h(Button,{size:'small',onClick:()=>Modal.confirm({title:'重置本组演示数据？',content:'仅清除当前角色的本地演示修改，恢复初始样例。',onOk:()=>{save(clone(config.pages));setDetail(null);setViewState('正常')}})},'重置演示'))),institutionTask&&h(institutions.View,{pages,onBegin:begin,onDetail:(page,row)=>setDetail({page,row}),termView,taskContext:institutionTask,onClose:()=>setInstitutionTask(null)}),detailPanel,modal);
  }
  ReactDOM.createRoot(document.getElementById('root')).render(h(arco.ConfigProvider,null,h(App)));
})();
