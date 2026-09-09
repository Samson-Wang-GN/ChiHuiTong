/* REQ-034/035: local prototype identities and object-scoped operation records. */
window.PrototypeManagement=(()=>{
  const h=React.createElement,{useState}=React,W=PrototypeWorkflows,clone=x=>JSON.parse(JSON.stringify(x));
  const rows=(p,id)=>p.find(x=>x.id===id)?.rows||[];
  const eligible=()=>['resource','channel'].includes(PROTOTYPE.role);
  let actor=null;
  const session=()=>actor;
  const safe=s=>String(s??'').replace(/1\d{10}/g,'[手机号已隐藏]');
  function prepare(c){
    if(eligible()){const p=c.pages.find(p=>p.id==='accounts');p.custom='orgAccounts';p.title='账号管理';p.actions=[];delete p.create;}
    if(c.role==='platform'){
      const p=c.pages.find(p=>p.id==='institutions');
      p.create.fields.push({key:'adminName',label:'初始管理员姓名',type:'text'},{key:'adminPhone',label:'初始管理员登录手机号',type:'text'});
    }
  }
  function migrate(p){
    if(PROTOTYPE.role==='clinic')for(const a of rows(p,'accounts')){if(a.role==='机构管理员')a.role='管理员';if(['业务操作员','业务员'].includes(a.role))a.role='员工';}
    if(eligible()){
      for(const a of rows(p,'accounts')){if(!a.identityVersion){a.role=/管理员/.test(a.role)?'管理员':'业务员';a.institution=PROTOTYPE.org;a.identityVersion=1;if(a.id==='USER-001')a.platformCreated=true;} }
      if(!actor){const wanted=sessionStorage.getItem('chihuitong-demo-account-'+PROTOTYPE.role);actor=wanted?(rows(p,'accounts').find(a=>a.id===wanted)||{id:wanted,role:'业务员',status:'已停用'}):rows(p,'accounts').find(a=>a.platformCreated)||rows(p,'accounts')[0];}
      else actor=rows(p,'accounts').find(a=>a.id===actor.id)||actor;
      if(PROTOTYPE.role==='channel')for(const c of rows(p,'clinics'))if(!('ownerUserId' in c)){const matches=rows(p,'accounts').filter(a=>a.name===c.rep);if(matches.length===1)c.ownerUserId=matches[0].id;else if(c.rep)c.ownerUserId=null;}
    }
    return p;
  }
  function project(p){
    if(eligible()&&(!actor?.id||actor.status==='已停用'))return p.map(page=>({...page,rows:[]}));
    if(!eligible()||actor?.role==='管理员')return p;
    const id=actor?.id,clinicRows=rows(p,'clinics').filter(c=>c.ownerUserId===id),clinicIds=new Set(clinicRows.map(c=>c.id)),names=new Set(clinicRows.filter(c=>rows(p,'clinics').filter(x=>x.name===c.name).length===1).map(c=>c.name));
    const sales=rows(p,'sales').filter(o=>o.ownerUserId===id),orders=new Set(sales.map(o=>o.id)),cards=new Set(sales.flatMap(o=>(o.cards||[]).map(c=>c.id))),customers=new Set(sales.flatMap(o=>(o.cards||[]).map(c=>c.customerId).filter(Boolean)));
    const related=r=>r.ownerUserId===id||(PROTOTYPE.role==='channel'?(clinicIds.has(r.clinicId)||names.has(r.clinic)||names.has(r.name)):orders.has(r.orderId)||orders.has(r.order)||orders.has(r.salesOrderId)||cards.has(r.cardId));
    const common=new Set(['contracts','contractSchemes','sources']);
    const out=p.map(page=>({...page,rows:common.has(page.id)?page.rows:page.id==='accounts'?page.rows.filter(a=>a.id===id):page.id==='clinics'?clinicRows:page.id==='sales'?sales:page.id==='salesCustomers'?page.rows.filter(c=>customers.has(c.id)):page.id==='earnings'?page.rows.map(r=>({id:r.id,kind:r.kind,status:'本人明细',scopeOnly:true,items:(r.items||[]).filter(related)})).filter(r=>r.items.length):page.rows.filter(related)}));
    const visible=new Set(out.flatMap(page=>page.rows.map(r=>r.id)));
    for(const page of out)if(['audit','tasks'].includes(page.id))page.rows=rows(p,page.id).filter(r=>visible.has(r.subject)||visible.has(r.target));
    return out;
  }
  function merge(full,before,next){
    if(eligible()&&(!actor?.id||actor.status==='已停用'))throw Error('当前账号不可操作。');
    if(!eligible()||actor?.role==='管理员')return next;
    const copy=clone(full);
    for(const page of next){
      const target=copy.find(p=>p.id===page.id);if(!target)continue;if(page.id==='earnings'){if(JSON.stringify(page.rows)!==JSON.stringify(rows(before,'earnings')))throw Error('业务员只可查看本人明细，不得处理整张结算单');continue;}
      const allowed=new Set(rows(before,page.id).map(r=>r.id));
      for(const r of page.rows){const old=target.rows.find(x=>x.id===r.id);if(old&&!allowed.has(r.id))throw Error('不能更新范围外数据。');if(old){if(['accounts','contracts','contractSchemes','sources'].includes(page.id)&&JSON.stringify(old)!==JSON.stringify(r))throw Error('业务员不能修改机构管理数据。');if(old.ownerUserId&&r.ownerUserId!==old.ownerUserId)throw Error('不能修改业务归属。');Object.assign(old,r);}else{if(['accounts','contracts','contractSchemes','sources'].includes(page.id))throw Error('不能新增机构管理数据。');target.rows.push({...r,ownerUserId:actor.id});}}
    }
    return copy;
  }
  function record(before,after){
    for(const page of after)if(['clinics','profile','bills','earnings','sales'].includes(page.id))for(const r of page.rows){
      const old=rows(before,page.id).find(x=>x.id===r.id);
      if(page.id==='clinics'&&PROTOTYPE.role==='channel'&&old?.rep!==r.rep){const candidates=rows(after,'accounts').filter(a=>a.name===r.rep);r.ownerUserId=candidates.length===1?candidates[0].id:null;}
      const keys=Object.keys(r).filter(k=>!['operationLogs','history','infoHistory'].includes(k)&&JSON.stringify(old?.[k])!==JSON.stringify(r[k]));
      if(!keys.length)continue;
      const change=r.profileChanges?.find(n=>old?.profileChanges?.find(o=>o.id===n.id)?.status!==n.status),event=r.history?.find(n=>typeof n==='object'&&!old?.history?.some(o=>o.id===n.id));
      const action=change?(change.status==='待审核'?'提交资料变更':change.status==='审核通过'?'通过资料变更':'退回资料变更'):r.status!==old?.status?(r.status==='已暂停'?'门诊下线':r.status==='服务中'?'门诊上线':'状态更新'):event?.name||(!old?'创建记录':'更新业务资料');
      const receipt=r.receipts?.find(n=>JSON.stringify(old?.receipts?.find(o=>o.id===n.id))!==JSON.stringify(n));
      const reason=change?.reason||(r.serviceReason!==old?.serviceReason?r.serviceReason:null)||receipt?.reason||receipt?.review||event?.reason||r.reason||'—';
      r.operationLogs=[{id:'OP-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),time:new Date().toISOString(),actor:actor?.name||PROTOTYPE.user,institution:PROTOTYPE.org,identity:actor?.role||PROTOTYPE.role,action:safe(action),reason:safe(reason),before:old?.status||'无',after:r.status||'已记录',fields:keys.join('、'),status:'已记录'},...(old?.operationLogs||[])];
    }
    return after;
  }
  function Logs({record:r}){
    const display=x=>({...x,time:/^\d{4}-.*T/.test(x.time||'')?new Date(x.time).toLocaleString('sv-SE',{timeZone:'Asia/Shanghai',hour12:false}):x.time,identity:({platform:'平台管理员',clinic:'门诊员工',channel:'渠道账号',resource:'资源方账号'})[x.identity]||x.identity});
    const legacy=(r.history||[]).map((x,i)=>({id:x.id||'OLD-'+i,time:x.time||x.date||'未记录',actor:x.actor||x.operator||'未记录',identity:'历史记录',action:safe(typeof x==='string'?x:x.name),reason:safe(x.reason||'未记录'),before:'未记录',after:x.status||'未记录',status:'历史记录'}));
    return h('section',{className:'panel management-logs'},h('h3',null,'操作记录'),h('p',{className:'muted'},'仅当前对象记录；历史缺失信息不补造。'),h(W.RecordList,{items:[...(r.operationLogs||[]),...legacy].map(display),states:['已记录','历史记录'],columns:[['time','时间（北京时间）'],['actor','操作人'],['identity','身份'],['action','操作'],['reason','原因'],['before','操作前'],['after','操作后'],['status','记录类型']],tableWidth:1200}));
  }
  function accountError(accounts,existing,d){
    if(actor?.role!=='管理员')return '仅机构管理员可管理账号。';
    if(!d.name?.trim()||!/^1\d{10}$/.test(d.phone||'')||!['管理员','业务员'].includes(d.role))return '请填写姓名、11位手机号并选择身份。';
    if(accounts.some(a=>a.id!==existing?.id&&a.phone===d.phone))return '该手机号已有本机构账号。';
    if(existing?.platformCreated&&d.role!=='管理员')return '平台创建的初始管理员角色不可修改。';
    if(existing?.id===actor.id&&(d.role!=='管理员'||d.status==='已停用'))return '不能降低自己的管理员身份。';
    if(existing?.role==='管理员'&&(d.role!=='管理员'||d.status==='已停用')&&!accounts.some(a=>a.id!==existing.id&&a.role==='管理员'&&a.status!=='已停用'))return '至少保留一个有效管理员。';
    return null;
  }
  function Accounts({pages,save}){
    const [edit,setEdit]=useState(null),[d,setD]=useState({}),[error,setError]=useState('');const accounts=rows(pages,'accounts');
    const open=a=>{setEdit(a||{});setD(a?clone(a):{name:'',phone:'',role:'业务员',status:'正常'});setError('')};
    const submit=()=>{const err=accountError(accounts,edit?.id?edit:null,d);if(err){setError(err);return}const next=clone(pages),list=rows(next,'accounts');if(edit.id)Object.assign(list.find(a=>a.id===edit.id),{name:d.name,phone:d.phone,role:d.role,status:d.status});else list.push({id:'USER-'+Date.now(),name:d.name,phone:d.phone,role:d.role,status:d.status,institution:PROTOTYPE.org,platformCreated:false,identityVersion:1});W.audit(next,edit.id?'修改机构账号':'创建机构账号',edit.id||'新账号');save(next);setEdit(null)};
    return h('div',{className:'workflow'},h('h1',null,'账号管理'),h(arco.Alert,{type:'info',content:'管理员查看本机构全部数据；业务员仅本人关联数据。初始管理员角色由平台锁定。当前仅演示账号，不发送邀请。'}),actor?.role==='管理员'&&h(arco.Button,{type:'primary',onClick:()=>open(null)},'创建账号'),h(W.RecordList,{items:accounts,states:['正常','待绑定','已停用'],columns:[['name','姓名'],['phone','登录手机号'],['role','身份'],['status','状态']],actions:a=>h(arco.Button,{type:'text',disabled:actor?.role!=='管理员',onClick:()=>open(a)},a.platformCreated?'编辑（初始管理员）':'编辑')}),edit&&h(arco.Modal,{visible:true,title:edit.id?'编辑机构账号':'创建机构账号',onCancel:()=>setEdit(null),onOk:submit,okText:'保存账号'},error&&h(arco.Alert,{type:'error',content:error}),W.field('姓名',h(arco.Input,{value:d.name,onChange:name=>setD({...d,name})})),W.field('登录手机号',h(arco.Input,{value:d.phone,onChange:phone=>setD({...d,phone})})),W.field('身份',h(arco.Select,{value:d.role,disabled:!!edit.platformCreated,options:['管理员','业务员'],onChange:role=>setD({...d,role})})),W.field('账号状态',h(arco.Select,{value:d.status,options:['正常','待绑定','已停用'],onChange:status=>setD({...d,status})})),edit.platformCreated&&h(arco.Alert,{type:'info',content:'平台创建的初始管理员，身份不可修改。'})));
  }
  function Switch({pages,onChange}){return eligible()?h(arco.Select,{'aria-label':'本机构演示账号',value:actor?.id,style:{width:210},options:rows(pages,'accounts').filter(a=>a.status!=='已停用').map(a=>({value:a.id,label:a.name+' · '+a.role})),onChange:id=>{actor=rows(pages,'accounts').find(a=>a.id===id);PROTOTYPE.user=actor.name;sessionStorage.setItem('chihuitong-demo-account-'+PROTOTYPE.role,id);onChange()}}):null;}
  function ServiceDialog({clinic:c,pages,onSave,onClose}){
    const [reason,setReason]=useState(''),[error,setError]=useState(''),up=!['正常','服务中','审核通过'].includes(c.status);
    const submit=()=>{if(PROTOTYPE.role!=='platform'){setError('仅平台可操作。');return}if(!reason.trim()){setError('请填写上下线原因。');return}if(up&&(c.qualification!=='审核通过'||!c.contractVersions?.some(v=>['已生效','即将到期'].includes(v.status)&&v.start<='2026-09-07'&&v.end>='2026-09-07')||/冻结|退出|终止/.test(c.status))){setError('资质、合同或其他业务限制未解除，不能上线。');return}const next=clone(pages),r=rows(next,'clinics').find(r=>r.id===c.id);if(r.status!==c.status){setError('门诊状态已变化，请重新打开。');return}r.status=up?'服务中':'已暂停';r.serviceReason=reason.trim();onSave(next);onClose()};
    return h(arco.Modal,{visible:true,title:(up?'上线':'下线')+'门诊',maskClosable:false,onCancel:onClose,onOk:submit,okText:up?'确认上线':'确认下线'},h('p',null,c.name+' · '+c.id),h(arco.Alert,{type:'warning',content:up?'满足资质、合同及账单条件后才接收新预约。':'下线后不接收新预约，存量预约继续履约。'}),error&&h(arco.Alert,{type:'error',content:error}),W.field('上下线原因',h(arco.Input.TextArea,{value:reason,onChange:setReason})));
  }
  return {prepare,migrate,project,merge,record,Logs,Accounts,Switch,ServiceDialog,session,accountError};
})();
