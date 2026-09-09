/* REQ-030: role-local prototype transitions. Production needs authenticated transactions. */
window.PrototypeOverdue = (() => {
  const h=React.createElement, {useState}=React, {Button,Alert,Modal,Descriptions,Drawer}=arco;
  const now='2026-09-07T12:00:00+08:00', clone=x=>JSON.parse(JSON.stringify(x));
  const time=a=>Date.parse(a.date+'T'+a.time+':00+08:00');
  const elapsed=(a,at=now)=>(Date.parse(at)-time(a))/3600000;
  const changing=a=>!!a.change||['待确认','改期待确认'].includes(a.changeStatus);
  const conflict=a=>!!a.conflict||/冲突|待核实|已到诊/.test(a.feedback||'');
  const active=a=>(a.overdueTasks||[]).find(t=>t.status!=='已关闭');
  const event=(a,name,at=now)=>{a.overdueHistory=(a.overdueHistory||[]).concat({name,at,status:a.status,held:a.held,used:a.used});};
  function task(a,kind,at=now){if(active(a))return;const list=a.overdueTasks||(a.overdueTasks=[]);list.push({id:a.id+'-T'+(list.length+1),kind,status:kind==='待补核销'?'待补核销':'待处理',at});}
  function close(a,reason,at=now){for(const t of a.overdueTasks||[])if(t.status!=='已关闭'){t.status='已关闭';t.reason=reason;t.closedAt=at;}}
  function check(a,at=now){
    if(a.status!=='成功'||a.redemptionId||a.used>0||elapsed(a,at)<24||!Number.isFinite(elapsed(a,at)))return a;
    a.overdueManaged=true;
    if(!active(a)){task(a,'过期预约待办',at);event(a,'24小时生成过期预约待办，提醒门诊（模拟）',at);}
    if(changing(a)||conflict(a)||a.feedback){return a;}
    if(elapsed(a,at)>=72){a.status='完成';a.completionSource='系统超时处理';a.completionNote='预约时间已过72小时，系统自动处理，尚未核销';a.customerPending=true;close(a,'72小时系统自动处理',at);event(a,'系统自动完成；保留占用，不核销、不计费',at);}
    return a;
  }
  function redeemError(a,at=now){
    if(!a)return '未找到预约';
    if(a.redemptionId||a.used>0)return '本次预约已经核销，不能重复扣减';
    if(a.status!=='成功'&&!(a.status==='完成'&&a.completionSource==='系统超时处理'))return '当前预约不能核销；已取消或已恢复权益不能补核销';
    if(changing(a)||conflict(a)&&!/^已到诊/.test(a.feedback||'')||a.conflict)return '存在改期待确认或反馈冲突，请先核实，不能核销';
    if(a.pendingRestore>0)return '补核销已撤销，权益待客户申请恢复，不能再次核销';
    if(!a.expiry||!a.date||a.date>a.expiry||a.frozen)return '预约日期超过权益有效期、权益冻结或有效期缺失，不能核销';
    if(!Number.isFinite(a.used)||!Number.isFinite(a.held)||!Number.isFinite(a.quantity)||a.quantity<=0||a.held<a.quantity||a.released)return '原预约权益占用不足或已恢复，不能补核销';
    if(!Number.isFinite(a.fee)||a.fee<0)return '当前适用获客费规则缺失，请联系平台核实';
    if(!Number.isFinite(time(a))||time(a)>Date.parse(at))return '尚未到预约时间或时间资料不完整';
    return '';
  }
  function act(a,action,role,at=now){
    if(!a||!['clinic','customer'].includes(role))throw Error('无权处理该预约');
    if(action==='absent'&&role!=='clinic'||['restore','attended'].includes(action)&&role!=='customer'||action==='redeem'&&role!=='clinic')throw Error('当前角色无权执行此操作');
    if(action==='absent'){
      if(a.status!=='成功'||elapsed(a,at)<0||a.redemptionId||a.used>0||changing(a)||conflict(a))throw Error('预约已变化，或存在到诊反馈/改期，请先核实');
      a.overdueManaged=true;a.status='取消';a.reason='门诊反馈患者未到';a.clinicFeedback='患者未到';a.customerPending=true;close(a,'门诊反馈患者未到；权益保留',at);event(a,'门诊报患者未到：取消但不释放，提醒客户（模拟）',at);
    }else if(action==='restore'&&a.pendingRestore>0){
      if(!a.restoreEvent||a.restoredEvent===a.restoreEvent||a.redemptionId||a.used>0||a.released||a.pendingRestore<a.quantity||changing(a)||a.frozen)throw Error('本次撤销状态已变化，不能重复恢复');
      a.pendingRestore-=a.quantity;a.restoredEvent=a.restoreEvent;a.released=true;a.status='取消';a.reason='补核销撤销后客户申请恢复权益';a.customerPending=false;close(a,'客户申请恢复权益',at);event(a,'补核销撤销后恢复申请自动通过；不延长有效期',at);
    }else if(action==='restore'){
      if(a.released||a.redemptionId||a.used>0||changing(a)||conflict(a)||a.customerFeedback==='已到诊')throw Error('已恢复、已核销或存在到诊/改期冲突，不能自动恢复');
      if(!a.customerPending&&!(a.status==='成功'&&elapsed(a,at)>=0))throw Error('当前无可提交的未到诊申请');
      if(!(a.held>=a.quantity&&a.quantity>0))throw Error('原预约占用不足，不能重复恢复');
      a.status='取消';a.reason='客户申请未到诊';a.held-=a.quantity;a.released=true;a.customerFeedback='未到诊';a.feedback='未到诊';a.customerPending=false;close(a,'客户申请恢复权益',at);event(a,'客户未到诊申请自动通过；解除占用，不延长有效期',at);
    }else if(action==='attended'){
      if(a.released||a.redemptionId||a.used>0||(!a.customerPending&&a.status!=='成功'))throw Error('当前预约不能提交已到诊反馈');
      if(elapsed(a,at)<0)throw Error('尚未到预约时间，不能确认已完成治疗');
      if(a.customerFeedback==='已到诊')throw Error('已提交到诊反馈，请等待门诊处理');
      a.customerFeedback='已到诊';a.feedback='已到诊，完成治疗';a.customerPending=false;
      close(a,'客户反馈已到诊，转补核销',at);task(a,'待补核销',at);
      if(a.clinicFeedback==='患者未到'){a.conflict=true;active(a).status='异常搁置';}
      event(a,a.conflict?'双方反馈冲突，保留占用并提醒门诊核实':'客户确认到诊；新建待补核销，不直接收费',at);
    }else if(action==='redeem'){
      const error=redeemError(a,at);if(error)throw Error(error);
      a.preRedemption={status:a.status,completionSource:a.completionSource,completionNote:a.completionNote};a.feeSnapshot={amount:a.fee,ruleVersion:a.feeRuleVersion||'演示当前规则V1',lockedAt:at};a.status='完成';a.completionSource='门诊核销完成';a.completionNote='原预约补核销完成';a.held-=a.quantity;a.used+=a.quantity;a.redemptionId='OD-R-'+a.id+'-'+((a.overdueHistory||[]).length+1);a.customerPending=false;a.followup=false;close(a,'已补核销',at);event(a,'核销时锁定费用；核销 '+a.quantity+'份，记费 '+a.fee+'元',at);
    }else throw Error('不支持的处理操作');
    a.overdueManaged=true;
    return a;
  }
  function reverse(a,r,at=now){
    if(r.settled)throw Error('账单已完成结算，不能撤销核销');
    if(r.status!=='已核销'||a.used<r.quantity)throw Error('核销或数量已变化');
    r.status='已撤销';delete a.redemptionId;a.used-=r.quantity;
    if(a.preRedemption?.completionSource==='系统超时处理'){
      a.status='完成';a.completionSource='系统超时处理';a.completionNote='系统自动完成（补核销已撤销）';a.pendingRestore=(a.pendingRestore||0)+r.quantity;a.restoreEvent='RESTORE-'+r.id;a.customerPending=true;a.released=false;close(a,'补核销已撤销，不再生成门诊待办',at);
    }else{a.status='成功';delete a.completionSource;delete a.completionNote;a.held+=r.quantity;}
    event(a,'撤销核销：保留原交易审计，不再计费',at);return a;
  }
  function rescheduled(a){close(a,'已确认改期');a.followup=false;event(a,'按新的确认时间重新计时');}
  function fixtures(){return ['OD24','OD72','ODABS'].map((id,i)=>{
    const a={id,name:'预约客户（演示）'+(i+1),clinic:'M1',benefit:'B-'+id,scheme:'舒适洁牙权益',externalName:'舒适洁牙服务',source:'安和保险客户福利',date:i===1?'2026-09-04':'2026-09-06',time:'10:00',intent:(i===1?'2026-09-04':'2026-09-06')+' 10:00',status:'成功',expiry:'2027-03-06',quantity:1,fee:60,held:1,used:0,token:'VISIT-'+id,canRedeem:true,overdueManaged:true};
    check(a);if(i===2)act(a,'absent','clinic');return a;
  });}
  function miniMigrate(data,role){
    if(!data.overdueVersion){
      for(const a of fixtures())if(!data.appointments.some(r=>r.id===a.id)){
        if(role==='customer'){a.name=data.profile.name;data.benefits.push({id:a.benefit,name:a.externalName,source:a.source,mode:'记名非实体卡',total:1,held:1,used:0,state:'已领取',expiry:a.expiry});}
        data.appointments.push(a);
      }
      for(const a of data.appointments)if(a.followup&&a.status==='成功'&&!a.overdueManaged){a.overdueManaged=true;task(a,'过期预约待办');}
      data.overdueVersion=23;
    }
    if(!data.rules29Fixtures){
      const late={...fixtures()[0],id:'ODLATE',benefit:'B-ODLATE',token:'VISIT-ODLATE',expiry:'2026-09-06',overdueTasks:[],overdueHistory:[]};
      const special={...fixtures()[1],id:'ODREV',benefit:'B-ODREV',token:'VISIT-ODREV',overdueTasks:[],overdueHistory:[],customerFeedback:'已到诊',feedback:'已到诊，完成治疗'};
      act(special,'redeem','clinic');const r={id:'DEMO-REV-R',status:'已核销',quantity:1,settled:false};reverse(special,r);
      for(const a of [late,special])if(!data.appointments.some(x=>x.id===a.id)){data.appointments.push(a);if(role==='customer')data.benefits.push({id:a.benefit,name:a.externalName,source:a.source,mode:'记名非实体卡',total:1,held:a.held,used:a.used,pendingRestore:a.pendingRestore||0,state:'已领取',expiry:a.expiry});}
      data.rules29Fixtures=true;
    }return data;
  }
  const summary=a=>a.pendingRestore>0?'补核销已撤销，您有'+a.pendingRestore+'份权益待恢复；申请后释放，有效期不延长':a.redemptionId?'门诊核销完成':a.conflict?'双方反馈待核实，权益继续占用':a.customerFeedback==='已到诊'?'已反馈完成治疗，等待门诊补核销，权益继续占用':a.completionSource==='系统超时处理'?a.completionNote:a.status==='取消'&&a.held>0?'已取消，权益仍占用；待客户申请恢复':a.released?'已恢复权益；有效期不延长':'尚未核销；不计费';
  function Details({a,role,onAction,onScan,onReschedule}){
    const confirm=(action,title,content)=>Modal.confirm({title,content,okText:'确认',cancelText:'返回',onOk:()=>onAction(action)});
    const buttons=[];
    if(role==='customer'&&a.pendingRestore>0){buttons.push(h(Button,{key:'restore-reversal',type:'primary',onClick:()=>confirm('restore','申请恢复权益？','核实本次补核销撤销记录后释放一次，不修改既有到诊反馈，不延长有效期。')},'申请恢复权益'));}
    else if(role==='customer'&&(a.customerPending||a.status==='成功'&&elapsed(a)>=0)&&!a.released&&!a.redemptionId){
      buttons.push(h(Button,{key:'restore',onClick:()=>confirm('restore','确认未到诊，申请恢复权益？','请如实确认未使用本次服务。系统复核通过后取消预约、解除原占用；已过期权益不会延期。')},'未到诊，申请恢复权益'));
      buttons.push(h(Button,{key:'attended',type:'primary',onClick:()=>confirm('attended','确认已到诊并完成治疗？','将提醒门诊补核销，权益继续占用，此操作不直接计费。')},'已到诊，完成治疗'));
    }
    if(role==='clinic'){
      if(a.status==='成功'&&elapsed(a)>=0)buttons.push(h(Button,{key:'absent',status:'danger',disabled:changing(a)||conflict(a),onClick:()=>confirm('absent','确认患者未到？','将取消本次预约，但不释放权益。客户需要在自己的小程序提交未到诊申请；系统不会因此向门诊收费。')},'患者未到，取消预约'));
      if(a.status==='成功'||a.status==='完成'&&a.completionSource==='系统超时处理')buttons.push(h(Button,{key:'scan',type:'primary',disabled:!!redeemError(a),onClick:onScan},'补核销'));
      if(a.status==='成功'&&!changing(a)&&onReschedule)buttons.push(h(Button,{key:'change',onClick:onReschedule},'协商后改期'));
    }
    return h('div',{className:window.Mini?'overdue-details card':'overdue-details'},h(Alert,{type:'warning',content:summary(a)}),h(Descriptions,{column:1,data:[['预约编号',a.id],['预约状态',a.status],['预约时间',a.date+' '+a.time],['推广产品',window.Mini?a.externalName:a.scheme],['权益占用',a.held+'份'],['已使用',a.used+'份'],['待恢复',(a.pendingRestore||0)+'份'],['权益到期',a.expiry],['完成来源',a.completionSource||'—'],['客户反馈',a.customerFeedback||a.feedback||'未反馈'],['门诊反馈',a.clinicFeedback||'未反馈'],['当前待办',active(a)?.status||'已关闭'],['费用',a.redemptionId?'已核销，按原快照计费':'未核销，不计费']].filter(([label])=>role!=='customer'||!['已使用','完成来源','门诊反馈','当前待办','费用'].includes(label)).map(([label,value])=>({label,value}))}),role==='clinic'&&redeemError(a)&&h(Alert,{type:'info',content:redeemError(a)}),a.conflict&&h(Alert,{type:'error',content:'双方反馈冲突，仅保留事实，等待核实；本期不提供裁决操作。'}),h('div',{className:'stack',style:{display:'flex',flexDirection:'column',gap:8,marginTop:16}},...buttons),h('h3',null,'处理记录'),...(a.overdueHistory||[]).map((e,i)=>h('p',{key:i},e.at.replace('T',' ').replace('+08:00','')+' · '+(role==='customer'?e.name.replace(/核销时锁定费用；核销 (\d+)份，记费 [\d.]+元/,'已完成核销 $1份').replace('撤销核销：保留原交易审计，不再计费','门诊已撤销本次核销，保留处理记录'):e.name))),...(a.overdueTasks||[]).map(t=>h('p',{key:t.id},t.id+' · '+t.kind+' · '+t.status+(t.reason?' / '+t.reason:''))));
  }
  function prepare(config){config.version='0.23';const ap=config.pages.find(p=>p.id==='appointments');if(!ap)return;ap.columns.push(['completionSource','完成来源'],['completionNote','完成说明']);if(config.role!=='clinic'){ap.rows.push({...fixtures()[1],name:'本方预约客户（演示）',clinic:'明禾口腔（演示）'});return;}const f=config.pages.find(p=>p.id==='followups');ap.rows.push(...fixtures());f.title='过期预约待办';f.custom='overdue';f.actions=[];f.description='24小时提醒 · 72小时系统完成不核销、不释放、不计费';}
  function migrate(pages){if(window.PROTOTYPE?.role!=='clinic')return pages;const ap=pages.find(p=>p.id==='appointments'),f=pages.find(p=>p.id==='followups');if(!ap||!f)return pages;
    const legacy=f.rows.filter(r=>!r.overdueLink).map(r=>({...r,legacyReadOnly:true}));
    const tasks=ap.rows.flatMap(a=>(a.overdueTasks||[]).map(t=>({id:t.id,name:a.name,date:a.date,appointment:a.id,overdueLink:true,status:t.status,note:t.reason||t.kind,kind:t.kind})));
    f.rows=[...tasks,...legacy];return pages;
  }
  function View({pages,save,focusId,onClose}){
    const [selected,setSelected]=useState(focusId||null),[change,setChange]=useState(false),[date,setDate]=useState('2026-09-08'),[clock,setClock]=useState('10:00'),[agreed,setAgreed]=useState(false),[error,setError]=useState(''),ap=pages.find(p=>p.id==='appointments'),rows=pages.find(p=>p.id==='followups').rows;
    const target=rows.find(r=>r.id===selected),a=ap.rows.find(a=>a.id===target?.appointment);
    const commit=action=>{try{const p=clone(pages),r=p.find(p=>p.id==='appointments').rows.find(r=>r.id===a.id);act(r,action,'clinic');save(migrate(p));}catch(e){arco.Message.error(e.message)}};
    const tick=()=>{const p=clone(pages);for(const a of p.find(p=>p.id==='appointments').rows)if(a.overdueManaged)check(a);save(migrate(p));arco.Message.success('已按评审时间检查演示预约，不运行真实定时任务');};
    const closeDetail=()=>{setSelected(null);setChange(false);setError('');if(onClose)onClose()};
    return h('div',{className:'workflow'},!focusId&&h(React.Fragment,null,h('h1',null,'过期预约待办'),h(Alert,{type:'info',content:'24小时生成待办；72小时无反馈且无未决改期/冲突时系统自动完成，仍占用权益且不计费。当前评审时间：2026-09-07 12:00。'}),h(Button,{style:{margin:'16px 0'},onClick:tick},'模拟定时检查（评审）'),h(PrototypeWorkflows.RecordList,{items:rows,states:['待处理','待补核销','异常搁置','已关闭'],columns:[['name','客户'],['appointment','预约编号'],['date','预约日期'],['kind','任务类型'],['note','处理说明'],['status','状态']],actions:r=>h(Button,{type:'text',onClick:()=>setSelected(r.id)},'查看并处理'),tableWidth:1050})),selected&&h(Drawer,{visible:true,width:'min(720px, 100vw)',title:'过期预约处理',footer:null,onCancel:closeDetail},a?h(React.Fragment,null,h(Details,{a,role:'clinic',onAction:commit,onScan:()=>Modal.info({title:'在门诊小程序补核销',content:'使用原预约客户的固定权益凭证，在门诊小程序核对并完成补核销。此后台不直接记费。独立原型不跨端同步，可在门诊小程序试用同编号 '+a.id+'，凭证 '+a.token+'。'}),onReschedule:()=>{setChange(true);setAgreed(false)}}),change&&h('section',{className:'panel'},h('h3',null,'协商后改期'),PrototypeWorkflows.field('新的预约日期',h(arco.DatePicker,{value:date,allowClear:false,onChange:setDate,style:{width:'100%'}})),PrototypeWorkflows.field('新的预约时间',h(arco.TimePicker,{value:clock,format:'HH:mm',allowClear:false,onChange:setClock,style:{width:'100%'}})),h(arco.Checkbox,{checked:agreed,onChange:setAgreed},'已与客户协商一致'),error&&h(Alert,{type:'error',content:error}),h(Button,{type:'primary',onClick:()=>{if(!agreed){setError('请确认已与客户协商一致');return}if(date>a.expiry||!date||!clock||Date.parse(date+'T'+clock+':00+08:00')<=Date.parse(now)){setError('新的时间须晚于评审时间且不超过权益到期日');return}const p=clone(pages),item=p.find(p=>p.id==='appointments').rows.find(r=>r.id===a.id);if(item.status!=='成功'||changing(item)){setError('预约状态已变化或存在待确认改期');return}item.date=date;item.time=clock;item.agreed=true;rescheduled(item);save(migrate(p));setChange(false);setError('');}},'确认改期'))):h(Alert,{type:'info',content:'历史待办未关联可验证预约，仅保留原记录，不推断核销或权益状态。'})));
  }
  return {reverse,now,elapsed,changing,active,check,act,redeemError,rescheduled,fixtures,miniMigrate,summary,Details,prepare,migrate,View};
})();
