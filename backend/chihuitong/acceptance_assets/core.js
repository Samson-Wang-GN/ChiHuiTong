(function () {
  'use strict';
  const h = React.createElement, A = arco;
  const C = window.CHT = {h, A, role:window.ACCEPTANCE_ROLE, token:'', actor:null, pages:{}, dialogs:{}};
  C.labels = {all:'全部',pending:'待处理',processed:'已处理',active:'启用',disabled:'停用',approved:'审核通过',rejected:'审核退回',draft:'草稿',effective:'生效中',not_started:'未生效',expired:'已到期',superseded:'历史版本',terminated:'已终止',online:'上线',offline:'下线',paused:'暂停',exited:'结束合作',success:'预约成功',completed:'完成',cancelled:'取消',pending_review:'待审核',pending_payment:'待付款',pending_confirmation:'待对账确认',pending_receipt:'待确认收款',settled:'已结清',overdue:'逾期',no_payment:'无需付款',payment_review:'付款待核实',disputed:'异议处理',issued:'已开卡',pending_approval:'待开卡审核',issuing:'开卡中',issue_failed:'开卡失败',cancel_pending:'取消待审核',stop_pending:'停止待审核',stopped:'已停止',unsettled:'未结清',not_charged:'未计费',insurance:'保险公司',bank:'银行',broker:'经纪代理公司',channel:'门诊渠道公司',clinic:'口腔门诊',platform:'平台',admin:'管理员',staff:'业务员',monthly:'月结',weekly:'周结',percent:'按比例',amount:'按金额',service:'服务权益',deduction:'抵用权益',discount:'折扣权益',physical:'不记名实体卡',named:'记名非实体卡',claimed:'已领取',unclaimed:'待领取',activated:'已激活',frozen:'已冻结',void:'已作废',failed:'失败',sent:'服务商已受理',delivered:'已送达',queued:'待发送',running:'执行中',succeeded:'执行成功',read:'已读',unread:'未读'};
  C.names = {id:'编号',number:'编号',name:'名称',title:'事项',kind:'机构类型',status:'状态',display_status:'状态',version:'数据版本',revision:'合同版本',internal_name:'内部展示名称',external_name:'外部展示名称',usage_rules:'使用规则',fee_cents:'单次获客费',redemption_units:'单次核销份数',validity_days:'有效天数',product_type:'产品类型',contact_name:'联系人',contact_phone:'联系电话',admin_name:'初始管理员姓名',admin_phone:'初始管理员手机号',role:'身份',phone:'手机号',active:'启用状态',platform_created:'平台开通管理员',reason:'原因',created_at:'创建时间',occurred_at:'操作时间',actor:'操作人',organization:'所属机构',organization_name:'机构名称',action:'操作',settlement_cycle:'结算周期',starts_at:'生效时间',ends_at:'到期时间',submitted_at:'提交时间',reviewed_at:'审核时间',due_at:'截止时间',attachment_ids:'附件',product_id:'推广产品',mode:'分配方式',value:'分配数值',quantity:'数量',total_cents:'金额',received_cents:'已收金额',scheduled_at:'预约时间',requested_at:'意向时间',customer_name:'客户姓名',clinic_name:'门诊',source_name:'来源展示名',review_status:'资料审核',service_status:'服务状态',confirmation_hours:'待确认时限（小时）',address:'经营地址',appointment_phone:'前台预约手机号',business_contact:'业务联系人',business_phone:'业务联系人电话',longitude:'经度',latitude:'纬度'};
  C.label = value => C.labels[value] || value;
  C.money = v => v == null ? '—' : (Number(v)/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+' 元';
  C.text = (key,value) => {
    if(value == null || value === '') return '—';
    if(typeof value === 'boolean') return value ? '是' : '否';
    if(key.endsWith('_cents')) return C.money(value);
    if(/_at$/.test(key) && !Number.isNaN(Date.parse(value))) return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
    if(key === 'role' && value === 'staff' && C.role === 'clinic') return '员工';
    return C.label(value);
  };
  C.Tag = ({value}) => h(A.Tag,{color:['active','effective','online','settled','approved'].includes(value)?'green':['rejected','overdue','failed'].includes(value)?'red':['pending','pending_payment','payment_review'].includes(value)?'orange':'gray'},C.label(value));
  C.events = new EventTarget();
  C.refresh = () => C.events.dispatchEvent(new Event('refresh'));
  C.query = params => new URLSearchParams(Object.entries(params).filter(([,v])=>v!==undefined && v!==null && v!=='')).toString();
  C.iso = value => /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? new Date(value).toISOString() : new Date(value.replace(' ','T')+(value.length===10?'T00:00:00':'')+'+08:00').toISOString();
  function message(data) {
    if(data.message) return data.message;
    const walk=(x,prefix='')=>Array.isArray(x)?x.map(v=>walk(v,prefix)).join('；'):x&&typeof x==='object'?Object.entries(x).map(([k,v])=>walk(v,(C.names[k]||'输入内容')+'：')).join('；'):prefix+String(x);
    return walk(data.details || data);
  }
  C.request = async (path,{method='GET',body,key,signal,binary=false}={}) => {
    if(!/^\/(api\/v1\/|acceptance\/sms$)/.test(path)||path.includes('..')||path.includes('\\')||path.includes('#')) throw new Error('请求地址不合法');
    const headers={};
    if(!(body instanceof FormData))headers['Content-Type']='application/json';
    if(C.token) headers['X-CHT-Authorization']='Bearer '+C.token;
    if(C.actor) headers['X-Membership-ID']=C.actor.id;
    if(key) headers['Idempotency-Key']=key;
    const response=await fetch('/chihuitong'+path,{method,headers,credentials:'same-origin',cache:'no-store',signal,body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});
    if(!response.ok){let data;try{data=await response.json();}catch{data={message:'服务暂不可用，请稍后重试'};}const error=new Error(message(data));error.status=response.status;error.requestId=response.headers.get('X-Request-ID');if(response.status===401 && C.token){C.token='';C.actor=null;C.events.dispatchEvent(new Event('expired'));}throw error;}
    return binary ? response.blob() : response.json();
  };
  C.api = (path,method='GET',body,key) => C.request(path,{method,body,key});
  C.download = async(path,name) => {const blob=await C.request(path,{binary:true});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);};
  C.Error = ({error,retry}) => error?h(A.Alert,{type:'error',content:h('div',null,error.message || String(error),error.requestId&&h('div',{className:'muted'},'问题编号：'+error.requestId),retry&&h(A.Button,{type:'text',onClick:retry},'重新加载'))}):null;
  C.useQuery = (path) => {
    const [state,set]=React.useState({data:null,loading:!!path,error:null}),[revision,bump]=React.useReducer(x=>x+1,0);
    React.useEffect(()=>{const fn=()=>bump();C.events.addEventListener('refresh',fn);return()=>C.events.removeEventListener('refresh',fn);},[]);
    React.useEffect(()=>{if(!path){set({data:null,loading:false,error:null});return;}const ctl=new AbortController();set({data:null,loading:true,error:null});C.request(path,{signal:ctl.signal}).then(data=>set({data,loading:false,error:null})).catch(error=>{if(!ctl.signal.aborted)set({data:null,loading:false,error});});return()=>ctl.abort();},[path,revision]);
    return {...state,reload:bump};
  };
  C.Panel = ({title,extra,children}) => h('section',{className:'panel'},(title||extra)&&h('div',{className:'toolbar'},h('h2',null,title),extra),children);
  C.Facts = ({data={},fields}) => h(A.Descriptions,{column:1,border:true,size:'small',data:(fields||Object.keys(data).filter(k=>C.names[k])).filter(k=>data[k]!==undefined).map(k=>({label:C.names[k]||k,value:typeof data[k]==='object'&&data[k]!==null?h(C.Facts,{data:data[k]}):C.text(k,data[k])}))});
  C.column = (key,title,width=160) => ({title:title||C.names[key]||key,dataIndex:key,width,render:v=>['status','display_status','service_status','review_status'].includes(key)?h(C.Tag,{value:v}):C.text(key,v)});
  C.List = function({path,columns,actions,toolbar,search=false,initialStatus='all',params={},rowKey='id',empty='暂无符合条件的记录'}) {
    const [status,setStatus]=React.useState(initialStatus),[page,setPage]=React.useState(1),[searchText,setSearchText]=React.useState(''),[keyword,setKeyword]=React.useState('');
    const q=C.useQuery(path+(path.includes('?')?'&':'?')+C.query({...params,status,page,search:keyword}));
    const cols=[...columns];if(actions)cols.push({title:'操作',width:180,fixed:'right',render:(_,r)=>h(A.Space,{wrap:true,size:4},actions(r))});
    return h('div',{className:'business-list'},h('div',{className:'toolbar'},h(A.Space,{wrap:true},search&&h(A.Input.Search,{value:searchText,onChange:setSearchText,onSearch:v=>{setKeyword(v);setPage(1);},allowClear:true,placeholder:'输入名称搜索','aria-label':'搜索名称',style:{width:260}}),toolbar),h(A.Button,{onClick:q.reload,loading:q.loading},'刷新')),h(C.Error,{error:q.error,retry:q.reload}),q.data?.reason&&h(A.Alert,{type:'warning',content:q.data.reason}),q.data?.counts&&h(A.Tabs,{activeTab:status,onChange:v=>{setStatus(v);setPage(1);},overflow:'scroll'},Object.entries(q.data.counts).sort(([a],[b])=>a==='all'?-1:b==='all'?1:0).map(([k,v])=>h(A.Tabs.TabPane,{key:k,title:C.label(k)+'（'+v+'）'}))),h(A.Table,{rowKey,columns:cols,data:q.data?.results||[],loading:q.loading,scroll:{x:Math.max(700,cols.reduce((n,c)=>n+(c.width||160),0))},noDataElement:h(A.Empty,{description:q.error?'加载失败，请重试':empty}),pagination:{current:page,pageSize:q.data?.page_size||20,total:q.data?.total||0,onChange:setPage,showTotal:true}}));
  };
  C.Drawer = function({title,children,onClose,width=1000,footer}) {
    return h(A.Drawer,{title,visible:true,width:Math.min(width,window.innerWidth-24),onCancel:onClose,escToExit:true,autoFocus:true,focusLock:true,tabIndex:-1,afterOpen:()=>document.querySelector('.arco-drawer-wrapper:not(.arco-drawer-wrapper-hide):last-of-type')?.focus(),footer:footer||h(A.Button,{onClick:onClose},'关闭详情')},children);
  };
  C.FormDialog = function({title,fields,initial={},hint,onSubmit,onClose,submitText='保存',width=760}) {
    const [form]=A.Form.useForm(),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(null);
    const retry=React.useRef({key:crypto.randomUUID(),payload:null});
    async function submit(){let values;try{const validated=await form.validate();values=Object.fromEntries(fields.filter(f=>validated[f.name]!==undefined).map(f=>[f.name,validated[f.name]]));}catch{return;}const payload=JSON.stringify(values);if(retry.current.payload && retry.current.payload!==payload)retry.current.key=crypto.randomUUID();retry.current.payload=payload;setBusy(true);setError(null);try{const result=await onSubmit(values,retry.current.key);if(result===false)return;C.refresh();A.Message.success('操作已完成');onClose();}catch(e){setError(e);}finally{setBusy(false);}}
    function close(){if(busy)return;const values=form.getFieldsValue();if(JSON.stringify(values)!==JSON.stringify(initial))A.Modal.confirm({title:'放弃未保存的内容？',content:'关闭后，本次尚未提交的输入不会保存。',onOk:onClose});else onClose();}
    return h(C.Drawer,{title,onClose:close,width,footer:h(A.Space,null,h(A.Button,{disabled:busy,onClick:close},'取消'),h(A.Button,{type:'primary',loading:busy,onClick:submit},submitText))},hint&&h(A.Alert,{type:'info',content:hint}),h(C.Error,{error}),h(A.Form,{form,layout:'vertical',initialValues:initial,disabled:busy,className:'business-form'},fields.map(f=>h(A.Form.Item,{key:f.name,field:f.name,label:f.label||C.names[f.name]||f.name,extra:f.hint,rules:f.rules||[{required:!f.optional,message:'请填写'+(f.label||C.names[f.name]||f.name)}]},f.render?f.render(form):f.type==='select'?h(A.Select,{options:f.options,allowClear:!!f.optional,disabled:f.disabled,'aria-label':f.label||C.names[f.name]}):f.type==='number'?h(A.InputNumber,{min:f.min??0,max:f.max,precision:f.precision??0,style:{width:'100%'},suffix:f.suffix,disabled:f.disabled}):f.type==='date'?h(A.DatePicker,{showTime:!!f.time,style:{width:'100%'},format:f.time?'YYYY-MM-DD HH:mm':'YYYY-MM-DD'}):f.type==='textarea'?h(A.Input.TextArea,{maxLength:f.max||10000,autoSize:{minRows:3,maxRows:10}}):f.type==='boolean'?h(A.Select,{options:[{label:'是',value:true},{label:'否',value:false}],disabled:f.disabled}):f.type==='files'?h(C.FileInput,{purpose:f.purpose,multiple:f.multiple!==false}):h(A.Input,{maxLength:f.max||200,disabled:f.disabled,autoComplete:'off'})))));
  };
  C.FileInput = function({value=[],onChange,purpose,multiple=true}) {
    const [error,setError]=React.useState(null),[files,setFiles]=React.useState([]);
    return h('div',null,h(C.Error,{error}),h(A.Upload,{multiple,limit:multiple?20:1,fileList:files,accept:purpose==='sales_excel'?'.xlsx,.xls':purpose==='cover'?'.jpg,.jpeg,.png':'.jpg,.jpeg,.png,.pdf',onChange:setFiles,onRemove:f=>{onChange((value||[]).filter(id=>id!==f.response?.id));return true;},customRequest:option=>{const controller=new AbortController();const body=new FormData();body.append('file',option.fileItem.originFile);body.append('purpose',purpose);C.request('/api/v1/files',{method:'POST',body,signal:controller.signal}).then(data=>{setError(null);onChange(multiple?[...(value||[]),data.id]:[data.id]);option.onSuccess(data);}).catch(e=>{if(!controller.signal.aborted){setError(e);option.onError(e);}});return {abort:()=>controller.abort()};}}),value?.length>0&&h(C.Attachments,{ids:value}));
  };
  C.Attachments = function({ids=[]}) {
    const [preview,setPreview]=React.useState(null),[error,setError]=React.useState(null),[loading,setLoading]=React.useState(null);
    React.useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url);},[preview]);
    async function open(id){setLoading(id);setError(null);try{const blob=await C.request('/api/v1/files/'+id,{binary:true});if(blob.type.startsWith('image/'))setPreview({url:URL.createObjectURL(blob),id});else await C.download('/api/v1/files/'+id,'附件-'+id+(blob.type==='application/pdf'?'.pdf':'.xlsx'));}catch(e){setError(e);}finally{setLoading(null);}}
    return h('div',null,h(C.Error,{error}),h(A.Space,{wrap:true},ids.map((id,i)=>h(A.Button,{key:id,loading:loading===id,onClick:()=>open(id)},'查看附件 '+(i+1)))),!ids.length&&h(A.Empty,{description:'未上传附件'}),preview&&h(A.Image.Preview,{src:preview.url,visible:true,onVisibleChange:v=>{if(!v)setPreview(null);}}));
  };
  C.Logs = ({type,id}) => h(C.List,{path:'/api/v1/objects/'+type+'/'+id+'/logs',columns:['occurred_at','actor','organization','role','action','reason'].map(k=>C.column(k))});
  C.Reason = {name:'reason',label:'操作原因',type:'textarea',max:500};
  C.reviewFields = [{name:'approved',label:'审核结果',type:'select',options:[{label:'审核通过',value:true},{label:'退回修改',value:false}]},C.Reason];
  C.options = object => Object.entries(object).map(([value,label])=>({value,label}));
  C.open = (type,props={}) => C.events.dispatchEvent(new CustomEvent('open',{detail:{type,props,key:crypto.randomUUID()}}));
  C.form = props => C.open('form',props);
  C.dialogs.form = C.FormDialog;
  C.action = (title,path,version,extra={},fields=[C.Reason],hint) => C.form({title,fields,hint,initial:extra,onSubmit:(values,key)=>C.api(path,'POST',{...(version?{version}:{}),...extra,...values},key)});
  C.button = (text,onClick,props={}) => h(A.Button,{size:'small',type:'text',onClick,...props},text);
})();
