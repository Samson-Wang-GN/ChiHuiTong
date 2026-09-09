/* Task projections reuse business pages and actions, with role-local completion history. */
window.PrototypeTasks = (() => {
  const h=React.createElement,{useState}=React,W=PrototypeWorkflows,O=PrototypeOperations;
  const rows=(p,id)=>p.find(x=>x.id===id)?.rows||[],today='2026-09-07';
  const groups={platform:[['institutions','机构审核'],['clinics','门诊与合同审核'],['contracts','合作合同审核'],['sales','销售审核与采购收款'],['bills','收款审核'],['earnings','对账与付款']],resource:[['sales','销售订单处理'],['earnings','对账与收款确认']],channel:[['clinics','门诊资料与续签'],['bills','账单催收'],['earnings','收益确认']],clinic:[['appointments','预约处理'],['followups','过期预约待办'],['bills','账单付款']]};
  function pending(pages) {
    const role=PROTOTYPE.role,out=[];
    const add=(page,r,title,phase,extra={})=>out.push({id:page+':'+r.id+':'+phase,page,target:r.id,name:page==='followups'?(r.name+' · '+r.appointment):(r.name||r.party||r.id),title,group:groups[role].find(g=>g[0]===page)?.[1]||title,phase,businessStatus:r.status,status:'待处理',deadline:r.deadline||r.end||'按业务处理要求',...extra});
    for(const [page] of groups[role])for(const r of rows(pages,page)) {
      if(page==='earnings'){
        if(!r.items)continue;
        if(role==='platform'&&['resource','channel'].includes(r.kind)&&['待付款','有异议'].includes(r.status))add(page,r,r.status==='待付款'?'向合作方付款':'处理对账异议',r.status+'-V'+r.version);
        if(role!=='platform'&&r.kind===role&&r.status==='待对账确认')add(page,r,'确认本方对账单','确认-V'+r.version);
        if(role!=='platform'&&r.kind===role&&r.status==='待确认收款')add(page,r,'确认本方收款','收款-V'+r.version);
        if(role==='platform'&&r.status==='待确认收款')for(const i of r.receiptIssues||[])if(i.status==='待处理')add(page,r,'核查合作方收款异常','收款异常-'+i.id);
      }else if(page==='sales'){
        if(role==='platform'&&['待审核','付款待确认','取消待审核','停止待审核'].includes(r.status))add(page,r,'处理采购订单',r.status,{name:r.id});
        if(role==='platform'&&r.refundStatus==='待退款')add(page,r,'登记采购退款','退款',{name:r.id});
        if(role==='platform'&&r.mode==='不记名实体卡'&&r.status==='已开卡'&&r.shipping!=='已寄送')add(page,r,'登记实体卡寄送','寄送',{name:r.id});
        if(role==='resource'&&r.status==='待付款')add(page,r,'提交采购付款凭证','付款',{name:r.id});
      }else if(page==='clinics'){
        if(role==='platform'){
          if(r.cycleRequest?.status==='待审核')add(page,r,'审核结算周期变更','账期-'+r.cycleRequest.id,{focusTab:'合同与续签',businessStatus:'账期待审核'});
          for(const change of r.profileChanges||[])if(change.status==='待审核')add(page,r,'审核门诊资料变更','资料变更-'+change.id,{focusTab:'资料与资质',businessStatus:'资料变更待审核'});
          if(r.qualification==='待审核')add(page,r,'审核门诊资质','资质审核',{focusTab:'资料与资质'});
          for(const c of r.contractVersions||[])if(c.status==='待审核')add(page,r,'审核三方合同 '+c.number,'合同-'+c.id,{focusTab:'合同与续签'});
        }else{
          if(['草稿','审核不通过'].includes(r.qualification))add(page,r,'补充并提交门诊资料','资料-'+r.qualification,{focusTab:'资料与资质'});
          const versions=r.contractVersions||[],c=versions.find(c=>['已生效','即将到期'].includes(c.status));
          if(!versions.some(c=>['待审核','已审核待生效'].includes(c.status))&&(!c||c.end<='2026-10-07'))add(page,r,c?'续签即将到期合同':'提交门诊三方合同','续签-'+(c?.id||'首签'),{focusTab:'合同与续签'});
        }
      }else if(page==='bills'){
        const status=W.billStatus(r);
        if(role==='platform'){for(const rec of r.receipts||[])if(rec.status==='待审核')add(page,r,'审核付款凭证','凭证-'+rec.id);}
        else if(role==='channel'){if(!['已结清','已取消'].includes(status)&&!r.history.some(x=>typeof x==='object'&&x.date===today&&x.name.startsWith('催收：')))add(page,r,'提醒门诊付款','催收-'+today);}
        else if(!['已结清','已取消'].includes(status))add(page,r,(r.receipts||[]).some(p=>p.status==='待审核')?'等待平台审核付款':(r.attempts||[]).some(a=>['待支付','结果待核实'].includes(a.status))?'核实在线支付结果':'处理门诊账单付款',status,{waiting:(r.receipts||[]).some(p=>p.status==='待审核')});
      }else{
        let actionable=false;
        if(role==='platform')actionable=page==='orders'?['待审核','待收款','已收款待开卡','制作中','取消待审核','待线下退款'].includes(r.status):['待审核'].includes(r.status);
        if(role==='resource')actionable=page==='orders'?r.status==='待收款'&&!r.paymentSubmitted:['校验失败','审核不通过','已退回','部分异常'].includes(r.status);
        if(role==='clinic')actionable=page==='appointments'?r.status==='待确认'||r.changeStatus==='待确认'||r.changeStatus==='改期待确认':!r.legacyReadOnly&&['待处理','待补核销','异常搁置'].includes(r.status);
        if(actionable)add(page,r,page==='appointments'?'处理客户预约':groups[role].find(g=>g[0]===page)[1],r.status+(r.changeStatus||''));
      }
    }
    return out;
  }
  function record(before,after){const target=after.find(p=>p.id==='tasks');if(!target)return after;const remains=new Set(pending(after).map(t=>t.id));for(const t of pending(before))if(!remains.has(t.id)&&!target.rows.some(r=>r.id===t.id)){target.rows.unshift({...t,status:'已处理',result:'业务状态已更新',handledAt:new Date().toLocaleString('zh-CN',{hour12:false})})}return after}
  function Workbench({pages,navigate}) {
    const pendingTasks=pending(pages).filter(t=>!t.waiting);
    return h(React.Fragment,null,h('div',{className:'page-heading'},h('div',null,h('h1',null,PROTOTYPE.greeting),h('p',null,'待办直接进入任务页处理 · 数量与本角色业务记录同步'))),h(arco.Alert,{type:'info',content:'待处理 '+pendingTasks.length+' 项；确认、审核与付款均保持原有权限。'}),h('div',{className:'cards'},...groups[PROTOTYPE.role].map(([id,title])=>h('button',{className:'task-card',key:id,onClick:()=>navigate('tasks?type='+id)},h('div',null,title),h('div',{className:'number'},pendingTasks.filter(t=>t.page===id).length),h('div',{className:'foot'},'查看具体任务 →')))),h('section',{className:'panel'},h('h2',null,'优先处理'),pendingTasks.length?pendingTasks.slice(0,6).map(t=>h('div',{className:'todo-row',key:t.id},h('div',null,h('strong',null,t.title+' · '+t.name),h('span',{className:'muted'},t.businessStatus+' · '+t.target)),h(arco.Button,{type:'text',onClick:()=>navigate('tasks?type='+t.page)},'去处理'))):h(arco.Empty,{description:'当前没有待处理任务'})));
  }
  function View({pages,save,onGeneric}) {
    const [focus,setFocus]=useState(null),[done,setDone]=useState(null),type=new URLSearchParams(location.hash.split('?')[1]||'').get('type')||'all';
    const all=[...pending(pages).filter(t=>!t.waiting),...rows(pages,'tasks').filter(t=>t.page!=='earnings'||rows(pages,'earnings').some(r=>r.id===t.target))],items=all.filter(t=>type==='all'||t.page===type);
    const open=t=>{if(t.status==='已处理'){setDone(t);return}if(['clinics','bills','earnings','sales','followups'].includes(t.page)){setFocus(t);return}const p=pages.find(p=>p.id===t.page),r=p?.rows.find(r=>r.id===t.target);if(r)onGeneric(p,r)};
    return h('div',{className:'workflow'},h('div',{className:'page-heading'},h('div',null,h('h1',null,'待处理任务'),h('p',null,'直接处理具体记录；关闭详情后保持任务列表与筛选'))),h('div',{className:'toolbar'},h(arco.Select,{'aria-label':'任务类型',value:type,style:{width:250},options:[{label:'全部任务类型',value:'all'},...groups[PROTOTYPE.role].map(([value,label])=>({value,label}))],onChange:value=>{location.hash='tasks?type='+value}})),h(W.RecordList,{items,initialStatus:'待处理',states:['待处理','已处理'],columns:[['title','具体任务'],['name','业务对象'],['group','任务类型'],['businessStatus','业务状态'],['deadline','截止/提醒'],['handledAt','处理时间'],['status','任务状态']],actions:t=>h(arco.Button,{type:'text',onClick:()=>open(t)},t.status==='待处理'?'立即处理':'查看结果'),tableWidth:1100}),
      focus?.page==='followups'&&h(PrototypeOverdue.View,{key:focus.id,pages,save,focusId:focus.target,onClose:()=>setFocus(null)}),focus?.page==='sales'&&h(PrototypeSales.View,{key:focus.id,pages,save,focusId:focus.target,onClose:()=>setFocus(null)}),focus?.page==='clinics'&&h(W.Clinics,{key:focus.id,pages,save,focusId:focus.target,focusTab:focus.focusTab,onClose:()=>setFocus(null)}),focus?.page==='bills'&&h(W.Bills,{key:focus.id,pages,save,focusId:focus.target,onClose:()=>setFocus(null)}),focus?.page==='earnings'&&h(O.Statements,{key:focus.id,pages,save,focusId:focus.target,onClose:()=>setFocus(null)}),done&&h(arco.Modal,{visible:true,title:'任务处理结果',footer:null,onCancel:()=>setDone(null)},h(arco.Descriptions,{column:1,data:[['任务',done.title],['对象',done.target],['结果',done.result],['时间',done.handledAt]].map(([label,value])=>({label,value}))})));
  }
  return {pending,record,Workbench,View};
})();
