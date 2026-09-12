(function () {
  'use strict';
  const h = React.createElement;
  const {Button, Input, Card, Alert, Typography, Table, Tabs, Drawer: ArcoDrawer, Space, Select, Modal, Spin} = arco;
  const Drawer = props => h(ArcoDrawer, {...props, escToExit:true, autoFocus:true, focusLock:true, tabIndex:-1, afterOpen:()=>document.querySelector('.arco-drawer-wrapper:not(.arco-drawer-wrapper-hide)')?.focus(), footer:h(Button,{onClick:props.onCancel},'关闭详情')});
  const role = window.ACCEPTANCE_ROLE;
  const names = {platform:'平台管理',resource:'客户资源方',channel:'门诊渠道',clinic:'口腔门诊'};
  const phones = {platform:'13800000001',resource:'13800000002',channel:'13800000003',clinic:'13800000004'};
  const labels = {all:'全部',pending:'待确认',success:'成功',completed:'完成',cancelled:'取消',active:'生效',disabled:'停用',approved:'已通过',rejected:'已退回',pending_review:'待审核',pending_payment:'待付款',pending_confirmation:'待对账确认',pending_receipt:'待确认收款',settled:'已结清',overdue:'逾期',no_payment:'无需付款',payment_review:'付款待核实',disputed:'异议处理',draft:'草稿',online:'上线',offline:'下线',issued:'已开卡'};
  const fieldNames = {id:'编号',name:'名称',title:'待处理事项',customer_name:'客户',phone:'手机号',internal_name:'推广产品',external_name:'外部名称',clinic_name:'门诊',organization_name:'机构',status:'状态',display_status:'状态',scheduled_at:'预约时间',requested_at:'意向时间',due_at:'截止时间',issued_on:'出账日期',total_cents:'金额（元）',received_cents:'已收（元）',quantity:'数量',source_name:'权益来源',version:'版本',kind:'类型',category:'类型',description:'说明',settlement_status:'门诊结算',month:'账期'};
  let token = '', membership = null;
  async function api(path, method='GET', body) {
    if (!/^\/(api\/v1\/|acceptance\/sms$)/.test(path) || path.includes('..') || path.includes('\\') || path.includes('#')) throw new Error('仅可请求本验收环境API');
    const headers = {'Content-Type':'application/json'};
    if(token) headers['X-CHT-Authorization']='Bearer '+token;
    if(membership) headers['X-Membership-ID']=membership.id;
    if(method !== 'GET') headers['Idempotency-Key']=crypto.randomUUID();
    const response = await fetch('/chihuitong'+path, {method,headers,credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
    const data = await response.json();
    if(!response.ok) throw new Error(data.message || JSON.stringify(data.details || data));
    return data;
  }
  function App() {
    const [phone,setPhone]=React.useState(phones[role]||''), [code,setCode]=React.useState(''), [sms,setSms]=React.useState('');
    const [logged,setLogged]=React.useState(false), [busy,setBusy]=React.useState(false), [error,setError]=React.useState('');
    const [section,setSection]=React.useState('/api/v1/workbench/tasks'), [data,setData]=React.useState(null), [status,setStatus]=React.useState('all'), [page,setPage]=React.useState(1), [detail,setDetail]=React.useState(null);
    const [rawPath,setRawPath]=React.useState('/api/v1/workbench'), [rawMethod,setRawMethod]=React.useState('GET'), [rawBody,setRawBody]=React.useState('{}'), [rawResult,setRawResult]=React.useState(null);
    const sequence = React.useRef(0);
    async function act(fn) { setBusy(true);setError('');try {await fn();} catch(e){setError(e.message);} finally {setBusy(false);} }
    async function load() {
      const id=++sequence.current;setBusy(true);setError('');
      try {const result=await api(section+(section.includes('?')?'&':'?')+'page='+page+'&status='+status);if(id===sequence.current)setData(result);}
      catch(e){if(id===sequence.current){setData(null);setError(e.message);}}
      finally{if(id===sequence.current)setBusy(false);}
    }
    React.useEffect(()=>{if(logged)load();},[logged,section,status,page]);
    const banner=h(Alert,{type:'warning',content:'仅合成数据的后端验收台 · 不是完整业务前端 · 不发送真实短信、不进行真实支付，请勿上传真实客户或付款资料。'});
    if(!role) return h('div',{className:'shell'},h(Typography.Title,{heading:3},'齿慧通 · 后端验收入口'),banner,h(Space,{direction:'vertical',style:{marginTop:24}},Object.entries(names).map(([key,name])=>h(Button,{key,href:'/chihuitong/'+key+'/'},'进入'+name+'验收'))));
    const login = () => act(async()=>{const result=await api('/api/v1/auth/login','POST',{phone,code});token=result.token;const me=await api('/api/v1/auth/me');membership=me.memberships.find(m=>role==='resource'?['broker','bank','insurance'].includes(m.kind):m.kind===role);if(!membership){await api('/api/v1/auth/logout','POST',{});token='';throw new Error('此手机号不属于当前角色，请使用本页指定账号');}setCode('');setSms('');setLogged(true);});
    if(!logged) return h('div',{className:'shell'},banner,h(Card,{className:'login',title:names[role]+' · 验收登录'},h(Space,{direction:'vertical',size:16,style:{width:'100%'}},h('label',null,'手机号',h(Input,{value:phone,onChange:setPhone,'aria-label':'手机号',autoComplete:'off'})),h(Button,{loading:busy,onClick:()=>act(async()=>{await api('/api/v1/auth/code','POST',{phone});setSms('验证码已进入测试短信箱，请点击查看。');})},'获取验证码'),h(Button,{loading:busy,onClick:()=>act(async()=>{const box=await api('/acceptance/sms','POST',{phone});setSms('本次验证码：'+box.code+'（5分钟内有效，仅可使用一次）');})},'查看测试短信箱'),sms&&h(Alert,{type:'info',content:sms}),h('label',null,'验证码',h(Input,{value:code,onChange:setCode,maxLength:6,'aria-label':'验证码',autoComplete:'off'})),error&&h(Alert,{type:'error',content:error}),h(Button,{type:'primary',loading:busy,onClick:login},'登录'),h('span',null,'本页测试账号：'+phones[role]))));
    const menu=[['待处理任务','/api/v1/workbench/tasks'],['预约与履约','/api/v1/appointments']];
    if(role==='platform')menu.push(['机构管理','/api/v1/organizations'],['推广产品','/api/v1/products']);
    if(role==='platform'||role==='resource')menu.push(['推广产品销售','/api/v1/sales-orders']);
    if(role!=='resource')menu.push(['门诊管理','/api/v1/clinics'],['门诊账单','/api/v1/clinic-bills']);
    if(role!=='clinic')menu.push(['合作方结算单','/api/v1/partner-bills']);
    if(role!=='platform')menu.push(['合同与推广产品','/api/v1/organizations/'+membership.organization_id+'/cooperation']);
    const rows=data?.results||[];
    const preferred=['title','name','customer_name','internal_name','clinic_name','source_name','quantity','total_cents','received_cents','scheduled_at','issued_on','display_status','status','settlement_status','id'];
    let columns=preferred.filter(k=>rows.some(r=>r[k]!==undefined)).slice(0,7).map(k=>({title:fieldNames[k]||k,dataIndex:k,width:k==='id'?250:150,render:v=>k.endsWith('_cents')?(Number(v)/100).toFixed(2):labels[v]||String(v??'—')}));
    const showDetails=(row)=>act(async()=>{let endpoint=row.detail_endpoint;if(!endpoint&&row.id&&!['/api/v1/workbench/tasks','/api/v1/products'].includes(section))endpoint=section+'/'+row.id;setDetail(endpoint?await api(endpoint):row);});
    columns.push({title:'操作',width:95,fixed:'right',render:(_,row)=>h(Button,{size:'small',onClick:()=>showDetails(row)},'详情')});
    function rawSend(){const perform=()=>act(async()=>setRawResult(await api(rawPath,rawMethod,rawMethod==='GET'?undefined:JSON.parse(rawBody))));if(rawMethod==='GET')perform();else Modal.confirm({title:'确认操作演示数据',content:'将以当前角色提交真实后端操作，并持久保存和记录日志。请核对目标和版本。',onOk:perform});}
    return h('div',{className:'shell'},h('div',{className:'header'},h(Typography.Title,{heading:3,style:{margin:0}},names[role]+' · 后端验收'),h(Space,null,membership.organization_name,h(Button,{onClick:()=>act(async()=>{await api('/api/v1/auth/logout','POST',{});token='';membership=null;sequence.current++;setData(null);setDetail(null);setRawResult(null);setLogged(false);})},'退出账号'))),banner,h('div',{className:'content'},h('nav',{className:'panel menu'},menu.map(([title,path])=>h(Button,{key:path,type:section===path?'primary':'text',onClick:()=>{setSection(path);setStatus(path.endsWith('/tasks')?'pending':'all');setPage(1);setData(null);}},title))),h('main',{className:'panel'},h('div',{className:'toolbar'},h(Typography.Title,{heading:5,style:{margin:0}},menu.find(x=>x[1]===section)?.[0]),h(Button,{loading:busy,onClick:load},'刷新')),error&&h(Alert,{type:'error',content:error}),data?.counts&&h(Tabs,{activeTab:status,onChange:v=>{setStatus(v);setPage(1);},overflow:'scroll'},Object.entries(data.counts).map(([key,n])=>h(Tabs.TabPane,{key,title:(labels[key]||key)+'（'+n+'）'}))),h(Spin,{loading:busy,style:{width:'100%'}},data?.results?h(Table,{columns,data:rows,rowKey:'id',scroll:{x:1000},pagination:{current:page,total:data.total,pageSize:data.page_size||20,onChange:setPage}}):h('pre',null,data?JSON.stringify(data,null,2):'暂无数据')),h('details',{className:'raw'},h('summary',null,'技术验收：API 请求与响应（非正式业务表单）'),h(Space,{direction:'vertical',style:{width:'100%',marginTop:16}},h(Select,{value:rawMethod,onChange:setRawMethod,options:['GET','POST'],style:{width:120}}),h(Input,{value:rawPath,onChange:setRawPath,'aria-label':'API路径'}),rawMethod==='POST'&&h(Input.TextArea,{value:rawBody,onChange:setRawBody,autoSize:{minRows:4},'aria-label':'JSON请求'}),h(Button,{onClick:rawSend,loading:busy},'发送验收请求'),h('pre',null,rawResult?JSON.stringify(rawResult,null,2):'仅允许当前环境API；服务端继续执行角色和数据权限检查。'))))),h(Drawer,{title:'业务详情（真实接口结果）',visible:!!detail,width:'min(720px, 95vw)',onCancel:()=>setDetail(null),footer:null},h('pre',null,detail?JSON.stringify(detail,null,2):'')));
  }
  ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();
