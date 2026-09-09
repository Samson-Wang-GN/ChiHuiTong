/* REQ-036. Role-local financial interaction demo; no payment provider requests. */
window.ClinicFinance=(()=>{
  const {h,clone,btn,note,field,row,card,heading,confirm}=Mini,{useState}=React;
  const initial=()=>({id:'BILL1',amount:600,status:'待付款',payment:'未发起',version:1,logs:[],submissions:[]});
  const admin=d=>d.logged&&d.identity==='管理员';
  function migrate(d){if(!['管理员','员工'].includes(d.identity)){d.logged=false;d.identity='员工';}if(!d.bill)d.bill=initial();const b=d.bill;if(!b.items)b.items=[...Array.from({length:9},(_,i)=>({id:'HISTORY-'+i,amount:60,status:'有效交易'})),{id:'R1',amount:60,status:'有效交易'}];b.removed=b.removed||[];b.issueDate=b.issueDate||'2026-09-07';b.deadline=PrototypeRules.deadline(b.issueDate,'周结');return d;}
  function act(data,action,values={}){
    if(!admin(data))throw Error('仅门诊管理员可处理合同和账单');
    const d=clone(data),b=d.bill;
    if(b.status==='已结清')throw Error('账单已结清，不能重复付款');
    if(b.items.some(t=>d.redemptions.some(r=>r.id===t.id&&r.status==='已撤销')))throw Error('账单版本未更新，请先核实关联交易');
    if(b.status==='已取消'||b.amount<=0)throw Error('账单已取消，无需付款');
    if(values.version!==b.version)throw Error('账单版本已变化，请重新核对');
    let label;
    if(action==='voucher'){
      if(['支付中','结果未知'].includes(b.payment)||b.status==='付款待审核')throw Error('已有未决支付或待审核凭证，请先等待处理');
      if(Number(values.amount)!==b.amount)throw Error('请提交本账单全额'+b.amount.toFixed(2)+'元付款凭证');
      const stamp=Date.parse(values.date+'Z');
      if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(values.date)||!Number.isFinite(stamp)||new Date(stamp).toISOString().slice(0,16)!==values.date||values.date>Mini.today+'T23:59'||!values.payer?.trim()||!values.reference?.trim())throw Error('请填写付款时间、付款方和交易参考号');
      if(!values.files?.length||values.files.length>3||values.files.some(f=>!/^data:image\/(png|jpeg);base64,/.test(f.url)||!f.verified))throw Error('请上传可读的PNG/JPG付款凭证，最多3张');
      b.submissions.push({date:values.date,amount:b.amount,payer:values.payer.trim(),reference:values.reference.trim(),files:clone(values.files),status:'待审核'});
      b.status='付款待审核';label='提交付款凭证，等待平台审核';
    }else if(action==='start'){
      if(b.status==='付款待审核'||['支付中','结果未知'].includes(b.payment))throw Error('请先处理当前付款，不能重复发起');
      b.payment='支付中';b.paymentId='PAY-'+Date.now();label='发起微信支付（演示）';
    }else if(action==='result'){
      if(!['支付中','结果未知'].includes(b.payment))throw Error('没有待核实的支付订单');
      if(!['支付取消','支付失败','结果未知','已关单','支付成功'].includes(values.result))throw Error('无效的演示结果');
      b.payment=values.result;if(values.result==='支付成功'){b.status='已结清';d.baseDebt=Math.max(0,d.baseDebt-b.items.filter(t=>t.id.startsWith('HISTORY-')).reduce((n,t)=>n+t.amount,0));for(const r of d.redemptions)if(b.items.some(t=>t.id===r.id))r.settled=true;}
      label='模拟服务端支付结果：'+values.result;
    }else throw Error('不支持的操作');
    b.logs.push({id:'LOG-'+Date.now(),time:new Date().toISOString(),actor:'门诊管理员（演示）',label,status:b.status});
    return d;
  }
  function reverse(data,id,reason){
    const d=clone(data),r=d.redemptions.find(r=>r.id===id),b=d.bill,linked=b.items.some(t=>t.id===id),error=PrototypeRules.reversalError(r,linked?b:null);
    if(!d.logged||!['管理员','员工'].includes(d.identity))throw Error('当前账号无权撤销');if(error)throw Error(error);if(!reason.trim())throw Error('请填写撤销原因');
    const a=d.appointments.find(a=>a.id===r.appointment);PrototypeOverdue.reverse(a,r);
    if(linked){b.removed.push({...b.items.find(t=>t.id===id),reason:reason.trim(),revision:b.version});b.items=b.items.filter(t=>t.id!==id);b.amount=b.items.reduce((n,t)=>n+PrototypeRules.cents(t.amount),0)/100;b.version++;if(!b.items.length){b.status='已取消';b.cancelReason='所有有效交易已撤销';}b.logs.push({id:'REV-'+id,time:new Date().toISOString(),actor:'门诊'+d.identity+'（演示）',label:'撤销 '+id+'，交易移出有效账单；保留原版本，原因：'+reason.trim(),status:b.status});}
    d.reversals.push({id:'REV-'+id,redemption:id,reason:reason.trim(),effect:'移除未结算费用 '+r.amount+'元；保留审计',special:!!a.pendingRestore});return d;
  }
  function Bill({data,save,go}){
    const [mode,setMode]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[files,setFiles]=useState([]),[amount,setAmount]=useState(data.bill.amount.toFixed(2)),[date,setDate]=useState('2026-09-07T10:00'),[payer,setPayer]=useState(''),[reference,setReference]=useState(''),[result,setResult]=useState('结果未知');
    if(!admin(data))return note('仅门诊管理员可查看和处理账单。','error');
    const b=data.bill,unresolved=['支付中','结果未知'].includes(b.payment),locked=b.status==='付款待审核'||unresolved||['已结清','已取消'].includes(b.status);
    const run=(action,values={})=>{try{save(act(data,action,{...values,version:b.version}));setError('');setMode('')}catch(e){setError(e.message)}};
    const read=async file=>{
      setBusy(true);setError('');
      try{
        if(!['image/png','image/jpeg'].includes(file.type)||file.size>512*1024||file.size===0)throw Error('请选择512KB以内的PNG/JPG图片');
        if(files.length>=3)throw Error('最多上传3张付款凭证');
        const url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('图片读取失败，请重新选择'));reader.readAsDataURL(file)});
        await new Promise((resolve,reject)=>{const img=new Image();img.onload=resolve;img.onerror=()=>reject(Error('图片无法解码，请更换文件'));img.src=url});
        setFiles(old=>old.length<3?[...old,{name:file.name,url,verified:true}]:old);
      }catch(e){setError(e.message)}finally{setBusy(false)}
      return false;
    };
    return h(React.Fragment,null,heading('周结账单'),card('2026-08-31 至 09-06',b.status,h(React.Fragment,null,row('账单编号',b.id),row('应付金额',b.amount.toFixed(2)+'元'),row('出账日期',b.issueDate),row('付款截止',b.deadline),row('付款主体',data.clinic+'经营主体（演示）'),row('收款方','齿慧通平台经营主体（演示）'),note('全额确认到账才结清；上传凭证不代表已到账。固定历史样例，今日核销不会重出本账单。')),!['已结清','已取消'].includes(b.status)&&h(React.Fragment,null,btn('微信支付',()=>confirm('微信支付','本次应付'+b.amount.toFixed(2)+'元；原型只演示同手机支付，不实际扣款。',()=>run('start')),{disabled:locked}),btn('上传付款凭证',()=>setMode('voucher'),{type:'secondary',disabled:locked}))),error&&note(error,'error'),locked&&b.status!=='已结清'&&note(unresolved?'支付结果未决，先核实或确认关单，再切换线下付款。':'付款凭证待平台审核，暂不重复支付。','warn'),
      mode==='voucher'&&card('上传付款凭证',null,h(React.Fragment,null,field('付款金额（元）',h(arco.Input,{value:amount,onChange:setAmount})),field('付款时间',h('input',{type:'datetime-local',value:date,onChange:e=>setDate(e.target.value)})),field('付款方',h(arco.Input,{value:payer,onChange:setPayer})),field('交易参考号',h(arco.Input,{value:reference,onChange:setReference})),note('最多3张PNG/JPG，每张512KB以内；仅使用虚构凭证。'),h(arco.Upload,{accept:'image/png,image/jpeg',showUploadList:false,beforeUpload:read,disabled:busy},btn(busy?'正在读取':'选择凭证图片',()=>{},{type:'secondary',disabled:busy})),...files.map((f,i)=>h('div',{key:i},h(arco.Image,{src:f.url,alt:'付款凭证预览',width:120}),h('p',null,f.name),btn('移除凭证 '+(i+1),()=>setFiles(files.filter((_,n)=>n!==i)),{type:'text'})))),h(React.Fragment,null,btn('提交平台审核',()=>confirm('提交付款凭证？','提交后仅等待平台核实到账，不能自行结清。',()=>run('voucher',{amount,date,payer,reference,files})),{disabled:busy}),btn('取消上传',()=>setMode(''),{type:'secondary'}))),
      b.payment!=='未发起'&&card('微信支付进度',b.payment,h(React.Fragment,null,row('支付订单',b.paymentId),note('未接入真实微信支付。支付成功仅能由正式服务端核实，前端返回和截图均不能作为到账依据。'),unresolved&&h(React.Fragment,null,field('模拟服务端结果（仅评审）',h(arco.Select,{value:result,onChange:setResult,options:['结果未知','支付取消','支付失败','已关单','支付成功']})),btn('模拟返回支付结果',()=>run('result',{result}),{type:'outline'})))),
      card('账单逐笔交易',null,h(Mini.StateList,{states:['有效交易'],items:b.items,render:t=>h('div',{key:t.id},row('交易编号',t.id),row('金额',t.amount.toFixed(2)+'元'))})),b.removed.length>0&&card('已移出交易（仅审计，不计入合计）',null,...b.removed.map(t=>h('p',{key:t.id},t.id+' · '+t.amount+'元 · '+t.reason))),
      ...b.submissions.map((s,i)=>card('付款凭证 '+(i+1),s.status,h(React.Fragment,null,row('金额',s.amount.toFixed(2)+'元'),row('付款时间',s.date.replace('T',' ')),...s.files.map((f,n)=>h(arco.Image,{key:n,src:f.url,alt:'已提交付款凭证',width:100})),note('由平台管理员审核，门诊没有审核确认收款入口。')))),
      card('操作记录',null,h(Mini.StateList,{states:['已记录'],items:b.logs.map(l=>({...l,status:'已记录'})),render:l=>h('div',{key:l.id},row('操作时间',new Date(l.time).toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'})),h('p',null,l.actor+' · '+l.label))})),btn('返回账单与收款',()=>go('bills'),{type:'secondary'}));
  }
  function Contract(){return h(React.Fragment,null,heading('门诊三方合同'),card('平台 / 启明渠道 / 明禾口腔','生效中',h(React.Fragment,null,row('合同编号','HT-MH-DEMO'),row('生效日期','2026-01-01'),row('到期日期','2026-09-30'),row('结算周期','周结'),row('付款期限','出账次日起3个自然日'),note('合同即将到期，请联系渠道业务员签订续签，由平台审核。门诊不可自行修改或审核。'),note('原型合同摘要为虚构样例，未接入真实合同附件。'))));}
  return {reverse,admin,migrate,act,Bill,Contract};
})();
