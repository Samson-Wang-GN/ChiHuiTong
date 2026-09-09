/* 0.20: role-local statement, product and task prototypes. No remote writes. */
window.PrototypeOperations = (() => {
  const h=React.createElement,{useState}=React,{Button,Input,InputNumber,DatePicker,Checkbox,Modal,Drawer,Select,Tag,Alert}=arco;
  const W=window.PrototypeWorkflows,clone=v=>JSON.parse(JSON.stringify(v)),rows=(p,id)=>p.find(x=>x.id===id)?.rows||[];
  const today='2026-09-07',now=()=>new Date().toLocaleString('zh-CN',{hour12:false}),uid=p=>p+'-'+Date.now()+'-'+Math.random().toString(36).slice(2,6);
  const cents=n=>PrototypeRules.cents(n),money=n=>(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
  const btn=(name,fn,props={})=>h(Button,{onClick:fn,...props},name),note=(text,type='info')=>h(Alert,{type,content:text,style:{marginBottom:16}});
  const defaults=[['FA-001','舒适洁牙权益','舒适洁牙服务'],['FA-002','种植牙抵用权益','种植牙专享抵用券'],['FA-003','正畸抵用权益','正畸专享抵用券'],['FA-004','儿童涂氟权益','儿童防龋涂氟服务'],['FA-005','口腔检查权益','口腔健康检查']];
  const vocabulary=s=>s.replace(/优惠方案|权益方案/g,'推广产品').replace(/合同授权方案/g,'合同授权产品').replace(/方案名称/g,'内部展示名称').replace(/创建方案/g,'创建推广产品').replace(/启用方案/g,'启用推广产品').replace(/停用方案/g,'停用推广产品').replace(/添加方案/g,'添加推广产品');
  function words(obj){if(!obj||typeof obj!=='object')return obj;for(const k of Object.keys(obj)){if(typeof obj[k]==='string'&&!['url','before','after'].includes(k))obj[k]=vocabulary(obj[k]);else if(typeof obj[k]==='object')words(obj[k])}return obj}
  const catalog=pages=>rows(pages,'schemes').length?rows(pages,'schemes'):window.PROTOTYPE.schemeCatalog||[];
  const product=(pages,key)=>catalog(pages).find(s=>s.id===key||s.name===key||(s.aliases||[]).includes(key));
  const sameProduct=(pages,a,b)=>a===b||!!product(pages,a)&&product(pages,a).id===product(pages,b)?.id;
  function prepare(config) {
    words(config);config.version='0.20';
    if(config.role==='clinic'){for(const r of config.pages.find(p=>p.id==='appointments').rows)if(r.note?.includes('客户申请改至'))r.changeStatus='待确认';}
    const ap=config.pages.find(p=>p.id==='appointments');if(ap&&!ap.columns.some(c=>c[0]==='clinicSettlement'))ap.columns.push(['clinicSettlement','门诊结算状态']);
    if(ap)for(const key of ['HISTORY','UNPAID'])ap.rows.push({id:'DEMO-YY-'+key,name:'跨月客户（演示）',clinic:'明禾口腔（演示）',scheme:'舒适洁牙权益',date:'2026-07-12',time:'10:00',status:'完成',note:key==='HISTORY'?'历史核销，本月门诊结清，待合作方当期归集':'历史核销，门诊尚未付款，不进入合作方结算',legacyClinicEvidence:{bill:'DEMO-CLINIC-'+key,state:key==='HISTORY'?'已结清':'未结清',date:key==='HISTORY'?'2026-09-05':'—'}});
    if(config.role==='platform')config.pages.push({id:'settlementPool',hidden:true,title:'结算归集演示数据',columns:[],rows:poolSeed()});
    const p=config.pages.find(p=>p.id==='schemes');
    if(p){p.title='推广产品';p.columns.splice(1,0,['externalName','外部产品展示名称']);for(const a of [p.create,...p.actions].filter(Boolean)){if(a.fields?.some(f=>f.key==='name'))a.fields.splice(1,0,{key:'externalName',label:'外部产品展示名称',type:'text'});}}
    for(const s of p?.rows||config.schemeCatalog||[]){const def=defaults.find(d=>d[1]===s.name);s.id=s.id||def?.[0]||uid('PRODUCT');s.externalName=s.externalName||def?.[2]||s.name;s.aliases=s.aliases||[s.name]}
    const e=config.pages.find(p=>p.id==='earnings');if(e){if(config.role==='platform')e.rows=[];e.custom='statements';e.title=config.role==='platform'?'合作方对账与付款':'收益对账';e.description='逐笔交易 · 合作方确认 · 平台付款凭证';e.actions=[];delete e.create;}
    if(config.role==='resource'){
      config.pages.find(p=>p.id==='orders').actions.push({label:'登记开卡付款',when:['待收款'],fields:[{key:'voucher',label:'付款凭证（演示文件名）',type:'file'},{key:'paymentSubmitted',label:'已在线下付款，等待平台确认收款',type:'checkbox'}],hint:'仅向平台提交付款说明，不代表已收款或已开卡。'});
      config.pages.find(p=>p.id==='imports').actions.push({label:'补充导入资料',when:['校验失败','审核不通过','已退回','部分异常'],next:'待审核',fields:[{key:'file',label:'修正后的Excel文件',type:'excel'},{key:'reason',label:'修正说明',type:'textarea'}],hint:'仅演示重新提交资料；真实Excel解析和匹配未接入。'});
    }
    config.pages.unshift({id:'tasks',title:'待处理任务',custom:'tasks',description:'直接处理具体任务，结果与原业务记录同步',columns:[],rows:[]});
  }
  function transactions(id,kind,count=12) {
    const share=kind==='resource'?1200:kind==='channel'?1800:kind==='clinic'?0:3000;
    const items=Array.from({length:count},(_,i)=>({id:id+'-T'+String(i+1).padStart(3,'0'),redemption:'HX-'+id+'-'+(i+1),appointment:'YY-'+id+'-'+(i+1),date:'2026-08-'+String(i+1).padStart(2,'0')+' 10:30',clinic:kind!=='clinic'&&i%2?'映禾口腔（演示）':'明禾口腔（演示）',customer:'客户编号-C'+String(i+1).padStart(3,'0'),productId:'FA-001',productName:'舒适洁牙权益',externalName:'舒适洁牙服务',quantity:1,feeCents:6000,amountCents:share,rule:kind==='resource'?'20%':kind==='channel'?'18元/次':kind==='clinic'?'获客服务费':'平台余额30元/次',contract:kind==='resource'?'HT-AH-001 / V1':kind==='channel'?'HT-2026-002 / V1':'核销组合快照 V1',clinicSettlement:kind==='clinic'?'未结清':'已结清',clinicSettledAt:kind==='clinic'?'':'2026-08-28',clinicBill:kind==='clinic'?'DEMO-BILL-AUG':'DEMO-PAID-CLINIC-AUG',status:'有效核销',source:'安和经纪（演示）',channel:'启明渠道（演示）'}));
    items.push({...items[0],id:id+'-ADJ1',date:'2026-08-25 11:00',original:items[0].id,quantity:-1,feeCents:-6000,amountCents:-share,status:'撤销调整'});return items;
  }
  function statement(id,kind,party,status){const items=transactions(id,kind);return {id,name:'2026年08月 · '+party,party,kind,period:'2026-08-01 至 2026-08-31',status,version:1,items,totalCents:items.reduce((n,x)=>n+x.amountCents,0),history:[],payments:[],confirmation:status==='待付款'?{version:1,actor:party+'对账员（演示）',time:'2026-09-02 10:00'}:null,demo:true};}

  function poolSeed() {
    const result=[];
    for(const [kind,party] of [['resource','安和经纪（演示）'],['channel','启明渠道（演示）']]){
      const base=transactions('POOL-'+kind,kind,1)[0];
      for(const [key,date,settledAt,state] of [['HISTORY','2026-07-12','2026-09-05','已结清'],['RECENT','2026-08-15','2026-09-06','已结清'],['UNPAID','2026-07-18','','未结清'],['PARTIAL','2026-08-20','','部分到账'],['REVIEW','2026-08-22','','付款待确认'],['AFTER','2026-08-23','2026-10-02','已结清'],['ASSIGNED','2026-07-20','2026-08-10','已结清']]){
        result.push({...base,id:'POOL-'+kind+'-'+key,kind,party,date:date+' 10:00',appointment:'DEMO-YY-'+key,redemption:'DEMO-HX-'+key,clinic:'明禾口腔（演示）',clinicSettlement:state,clinicSettledAt:settledAt,clinicBill:'DEMO-CLINIC-'+key,statementId:key==='ASSIGNED'?'历史已入单-待付款':''});
      }
    }return result;
  }
  function collectionReason(t,pages,month='2026-09'){
    const start=new Date(month+'-01T00:00:00Z');start.setUTCMonth(start.getUTCMonth()+1);start.setUTCDate(0);const cutoff=start.toISOString().slice(0,10),allocated=rows(pages,'earnings').some(s=>(s.items||[]).some(i=>i.id===t.id));
    if(t.statementId||allocated)return '已入单';
    if(t.clinicSettlement!=='已结清'||!t.clinicBill||!t.clinicSettledAt)return '门诊未结清';
    if(t.clinicSettledAt>cutoff||t.date.slice(0,10)>cutoff)return '下期待归集';
    if(t.cancelledBeforeBilling)return '已撤销不入单';
    if(t.amountCents<0&&(!t.adjustmentConfirmed||!t.original||!rows(pages,'earnings').some(s=>(s.items||[]).some(i=>i.id===t.original))))return '调整待核实';
    return '可归集';
  }
  function collect(pages,month='2026-09'){
    if(PROTOTYPE.role!=='platform'||month!=='2026-09')return {error:'仅平台可执行固定2026年09月归集演示。'};
    const next=clone(pages),target=next.find(p=>p.id==='earnings'),groups=new Map();
    for(const t of rows(next,'settlementPool'))if(collectionReason(t,next,month)==='可归集'){
      const key=t.kind+'|'+t.party;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(t);
    }
    if(!groups.size)return {error:'没有可归集交易；已入单、未结清或截止后到账的交易不会重复纳入。'};
    for(const items of groups.values()){
      const first=items[0];
      if(target.rows.some(r=>r.kind===first.kind&&r.party===first.party&&r.period?.startsWith(month)))return {error:'该机构当期已有结算单，不能重复生成或追加覆盖；迟到记录保留后续归集。'};
      const id=uid('DEMO-SETTLE-'+month+'-'+first.kind),total=items.reduce((n,t)=>n+t.amountCents,0);
      if(total<=0)return {error:'零或负金额整单处置待确认，本次不生成或占用交易。'};
      target.rows.unshift({id,name:'2026年09月 · '+first.party,kind:first.kind,party:first.party,period:'2026-09-01 至 2026-09-30',status:'待对账确认',issueDate:'2026-10-01',deadline:'2026-10-06',version:1,totalCents:total,items:items.map(t=>({...t,statementMonth:month})),history:[{id:uid('GEN'),name:'模拟10月1日历史交易归集',actor:PROTOTYPE.user,time:now(),status:'待对账确认'}],payments:[],receiptIssues:[],confirmation:null,demo:true});
      items.forEach(t=>{t.statementId=id});
    }
    W.audit(next,'模拟月度出账：仅已回款历史未入单交易',month);return {pages:next,count:groups.size};
  }
  function Pool({pages,save}){
    const [open,setOpen]=useState(false),[message,setMessage]=useState('');
    return h('section',{className:'panel'},btn(open?'收起历史交易归集':'查看历史交易归集',()=>setOpen(!open)),open&&h(React.Fragment,null,
      note('独立演示：模拟2026年10月1日出9月单，截止9月30日。扫描全部历史，不按核销月截断；不是实际定时出账。'),
      message&&note(message),btn('模拟生成9月结算单',()=>Modal.confirm({title:'模拟月度归集？',content:'只把门诊已结清且尚未入单的历史交易纳入各自9月单；不会修改已有单或实际转账。',onOk:()=>{const result=collect(pages);if(result.error)setMessage(result.error);else {save(result.pages);setMessage('已生成 '+result.count+' 张独立结算单，重复执行不会重复入单。')}}}),{type:'primary'}),
      h(W.RecordList,{items:rows(pages,'settlementPool').map(t=>({...t,status:collectionReason(t,pages),amount:t.amountCents/100})),states:['可归集','门诊未结清','已入单','下期待归集','已撤销不入单','调整待核实'],tableWidth:1300,columns:[['id','分配记录'],['party','收款机构'],['date','原核销日期'],['clinicSettlement','门诊结算状态'],['clinicSettledAt','门诊结清日期'],['amount','本方金额（元）'],['statementId','已归入结算单'],['status','归集状态']]})));
  }

  function migrate(pages) {
    const role=window.PROTOTYPE.role;
    words(pages);
    for(const s of catalog(pages)){const def=defaults.find(d=>d[0]===s.id||d[1]===s.name);s.id=s.id||def?.[0]||uid('PRODUCT');s.externalName=s.externalName||def?.[2]||s.name;s.aliases=[...new Set([...(s.aliases||[]),s.name,def?.[1]].filter(Boolean))];}
    for(const p of pages)for(const r of p.rows){if(r.scheme){r.productId=r.productId||product(pages,r.scheme)?.id;if(['contractSchemes','offers'].includes(p.id))r.scheme=product(pages,r.productId)?.name||r.scheme;}if(r.schemeStates){const state={};for(const [name,value]of Object.entries(r.schemeStates))state[product(pages,name)?.name||name]=value;r.schemeStates=state}}
    const e=pages.find(p=>p.id==='earnings');
    if(e){if(role==='platform')e.rows=e.rows.filter(r=>['resource','channel'].includes(r.kind));for(const r of e.rows){if(r.status==='待确认'&&r.items)r.status='待对账确认';if(r.status==='已付款'&&r.items)r.status='待确认收款';r.payments=r.payments||[];r.history=r.history||[];r.receiptIssues=r.receiptIssues||[];}for(const r of e.rows)if(!r.items){r.legacyStatement=true;r.legacyStatus=r.legacyStatus||r.status;r.status=r.legacyStatus==='已结账'?'历史已结账':'明细待补充';}
      const seeds=role==='platform'?[statement('DEMO-RES-AUG','resource','安和经纪（演示）','待确认'),statement('DEMO-CHAN-AUG','channel','启明渠道（演示）','待付款')]:[statement('DEMO-'+role.toUpperCase()+'-AUG',role,window.PROTOTYPE.org,'待确认')];
      for(const s of seeds){if(s.status==='待确认')s.status='待对账确认';s.receiptIssues=[];if(!e.rows.some(x=>x.id===s.id))e.rows.unshift(s);}
      if(['resource','channel'].includes(role)){const sid='DEMO-RECEIVE-'+role.toUpperCase()+'-JUL';if(!e.rows.some(x=>x.id===sid)){const r=statement(sid,role,PROTOTYPE.org,'待付款');r.name='2026年07月 · '+r.party;r.period='2026-07-01 至 2026-07-31';r.items.forEach(t=>{t.date=t.date.replace('2026-08','2026-07');t.clinicSettledAt='2026-07-28';t.clinicBill='DEMO-PAID-CLINIC-JUL'});r.status='待确认收款';r.receiptIssues=[];r.payments=[{id:sid+'-PAY',amountCents:r.totalCents,date:'2026-09-03',reference:sid+'-BANK',payee:r.party,files:[W.sample('七月收益付款回单','付款凭证')],status:'已登记',version:1}];e.rows.push(r);}}
      for(const r of e.rows)for(const t of r.items||[]){t.statementMonth=r.period?.slice(0,7)||'历史待补';t.clinicSettlement=t.clinicSettlement||'依据待补充';}
    }
    const bills=pages.find(p=>p.id==='bills');
    if(bills&&!bills.rows.some(r=>r.id==='DEMO-BILL-AUG')){const items=transactions('DEMO-BILL-AUG','clinic');bills.rows.push({id:'DEMO-BILL-AUG',name:'明禾口腔（演示）',note:'演示逐笔账单',period:'2026-08-01 至 2026-08-31（逐笔演示）',amount:items.reduce((n,r)=>n+r.feeCents,0)/100,items,status:'待付款',deadline:'2026-09-09',flowVersion:18,receipts:[],attempts:[],history:[],confirmed:0,revision:1,cycle:'月结'})}
    if(bills&&!bills.rows.some(b=>b.id==='DEMO-CLINIC-UNPAID'))bills.rows.push({id:'DEMO-CLINIC-UNPAID',name:'明禾口腔（演示）',period:'2026-07 历史核销回款演示',amount:60,confirmed:0,status:'待付款',deadline:'2026-09-09',cycle:'月结',flowVersion:18,revision:1,receipts:[],attempts:[],history:[],items:[{...transactions('DEMO-CLINIC-UNPAID','clinic',1)[0],appointment:'DEMO-YY-UNPAID',date:'2026-07-18 10:00',clinicBill:'DEMO-CLINIC-UNPAID'}]});
    for(const r of e?.rows||[]){if(r.demo&&!r.issueDate){r.issueDate=PrototypeRules.addDays(r.period.match(/\d{4}-\d{2}-\d{2}/g).at(-1),1);r.deadline=PrototypeRules.deadline(r.issueDate,'月结');}}
    for(const b of bills?.rows||[])if(b.id==='DEMO-BILL-AUG'||b.id==='DEMO-CLINIC-UNPAID'){b.issueDate=b.issueDate||'2026-09-01';b.deadline=PrototypeRules.deadline(b.issueDate,b.cycle);}
    const billingState=b=>W.billStatus(b)==='已结清'?'已结清':b.receipts.some(p=>p.status==='待审核')||b.attempts.some(p=>['待支付','结果待核实'].includes(p.status))?'付款待确认':'未结清';
    for(const b of bills?.rows||[])for(const t of b.items||[]){t.clinicSettlement=billingState(b);t.clinicSettledAt=b.settledAt||'';}
    for(const t of rows(pages,'settlementPool')){const b=rows(pages,'bills').find(b=>b.id===t.clinicBill);if(b){t.clinicSettlement=billingState(b);t.clinicSettledAt=b.settledAt||'';}}
    for(const a of rows(pages,'appointments')){const bill=rows(pages,'bills').find(b=>(b.items||[]).some(t=>t.appointment===a.id));a.clinicSettlement=bill?(billingState(bill)):a.legacyClinicEvidence?.state||(a.completionSource==='系统超时处理'||a.overdueManaged&&!a.redemptionId||a.status!=='完成'?'未产生费用':'依据待补充');a.clinicBill=bill?.id||a.legacyClinicEvidence?.bill||'—';a.clinicSettledAt=bill&&W.billStatus(bill)==='已结清'?(bill.settledAt||'日期待补充'):a.legacyClinicEvidence?.date||'—';}
    return pages;
  }
  const columns=[['id','交易编号'],['date','交易时间'],['clinic','履约门诊'],['productName','推广产品（内部）'],['quantity','份数'],['fee','获客费（元）'],['rule','分配规则快照'],['amount','本方金额（元）'],['status','交易状态']];
  function TransactionList({statement:s,feeOnly=false}) {
    const [selected,setSelected]=useState(null);
    const items=s.items||[];
    const cs=feeOnly?columns.filter(c=>c[0]!=='rule').map(c=>c[0]==='amount'?['amount','费用金额（元）']:c):columns;
    const mapped=items.map(t=>({...t,fee:t.feeCents/100,amount:(feeOnly?t.feeCents:t.amountCents)/100}));
    const exportRows=(shown,scope)=>{const total=shown.reduce((n,r)=>n+cents(r.amount),0);PrototypeExcel.download(s.id+'-交易明细-演示',[{name:'导出说明',rows:[['项目','内容'],['对账单',s.id],['合作方/门诊',s.party||s.name],['状态与关键词',scope],['导出笔数',shown.length],['筛选金额（元）',total/100],[s.scopeOnly?'本人明细合计（非整单金额）':'完整单据金额（元）',s.scopeOnly?items.reduce((n,t)=>n+t.amountCents,0)/100:(s.totalCents??cents(s.amount))/100],['数据说明','虚构原型；导出包含筛选后的全部分页，编号按文本存储。']]},{name:'交易明细',rows:[[...cs.map(c=>c[1]),'产品编号','核销编号','预约编号','客户业务标识','关联合同版本','原交易编号','门诊结算状态','门诊账单','门诊结清日期','归集账期'],...shown.map(r=>[...cs.map(c=>r[c[0]]),r.productId,r.redemption,r.appointment,r.customer,r.contract,r.original||'',r.clinicSettlement||'依据待补充',r.clinicBill||'',r.clinicSettledAt||'',r.statementMonth||''])]}])};
    return h(React.Fragment,null,note('全部 '+items.length+' 笔 · 合计 '+money(items.reduce((n,t)=>n+(feeOnly?t.feeCents:t.amountCents),0))+' 元；调整记录与原交易分别保留。'),h(W.RecordList,{items:mapped,columns:cs,states:['有效核销','撤销调整'],onView:setSelected,onExport:exportRows,exportLabel:'下载Excel',tableWidth:1400}),selected&&h(Drawer,{visible:true,escToExit:false,title:'逐笔交易详情',width:740,footer:null,onCancel:()=>setSelected(null)},h(arco.Descriptions,{column:1,border:true,data:[...cs,['productId','产品编号'],['externalName','外部产品名称快照'],['redemption','核销编号'],['appointment','预约编号'],['customer','客户业务标识'],['contract','合同版本'],['original','调整对应原交易'],['clinicSettlement','门诊结算状态'],['clinicBill','门诊账单'],['clinicSettledAt','门诊结清日期'],['statementMonth','归集账期']].map(([k,label])=>({label,value:selected[k]??'—'}))})));
  }
  function Statements({pages,save,focusId,onClose}) {
    const role=window.PROTOTYPE.role,[id,setId]=useState(focusId||null),[action,setAction]=useState(null),[error,setError]=useState(''),[reason,setReason]=useState(''),[agreed,setAgreed]=useState(false),[files,setFiles]=useState([]),[amount,setAmount]=useState(0),[date,setDate]=useState(today),[reference,setReference]=useState(''),[actionVersion,setActionVersion]=useState(null);
    const list=rows(pages,'earnings').filter(s=>role==='platform'?['resource','channel'].includes(s.kind):!s.kind||s.kind===role),s=list.find(s=>s.id===id);
    const complete=s=>s?.items?.length&&s.items.every(t=>t.clinicSettlement==='已结清'&&t.clinicBill&&t.clinicSettledAt)&&s.items.reduce((n,t)=>n+t.amountCents,0)===s.totalCents;
    const receiptOK=s=>s?.payments?.length===1&&s.confirmation?.version===s.version&&s.payments.every(p=>p.version===s.version&&p.amountCents===s.totalCents&&p.payee===s.party&&p.reference&&p.files?.length&&p.files.every(W.fileOK));
    const change=(label,fn)=>{const next=clone(pages),live=rows(next,'earnings').find(s=>s.id===id);if(fn(live)===false)return;live.history.unshift({id:uid('EVENT'),name:label,time:now(),actor:window.PROTOTYPE.user,status:live.status});W.audit(next,label,id);save(next);setError('');setAction(null)};
    const start=a=>{setAction(a);setActionVersion(s.version);setDate(today);setError('');setReason('');setAgreed(false);setFiles([]);setReference('');setAmount((s.totalCents||0)/100)};
    const submit=()=>{
      if(['resource','channel'].includes(role)&&PrototypeManagement.session()?.role!=='管理员'){setError('仅机构管理员可处理整张结算单');return}const live=rows(pages,'earnings').find(r=>r.id===id);
      if(!live||live.version!==actionVersion||!complete(live)){setError('门诊回款依据或明细未补齐、合计不符或版本变化，不能处理。');return}
      if(action==='confirm'){
        if(!['resource','channel'].includes(role)||live.kind!==role||live.status!=='待对账确认'||!agreed){setError('请核对本方完整明细并勾选确认；只有本合作方可以确认。');return}
        change('合作方确认版本 '+s.version,r=>{r.status='待付款';r.confirmation={version:r.version,actor:window.PROTOTYPE.user,time:now()}});
      }else if(action==='pay'){
        if(role!=='platform'||live.kind==='platform'||live.status!=='待付款'||live.confirmation?.version!==live.version){setError('只有已由合作方确认的当前版本可以付款。');return}
        if(!agreed||!date||date>today||!reference.trim()||!files.length||files.some(f=>!W.fileOK(f))||cents(amount)!==live.totalCents||live.totalCents<=0){setError('请填写准确的全额付款金额、有效日期、交易参考号、可读凭证，并确认已实际付款。');return}
        if(rows(pages,'earnings').some(r=>r.payments?.some(p=>p.reference===reference.trim()))){setError('该付款交易参考号已登记，不能重复使用。');return}
        Modal.confirm({title:'登记已完成线下付款？',content:'收款方：'+s.party+'；金额：'+money(s.totalCents)+'元。仅登记事实，不执行转账。',onOk:()=>change('平台登记付款',r=>{if(r.status!=='待付款')return;r.payments.push({id:uid('OUT'),amountCents:r.totalCents,date,reference:reference.trim(),payee:r.party,files:clone(files),status:'已登记',version:r.version});r.status='待确认收款'})});
      }else if(action==='receive'){
        if(!['resource','channel'].includes(role)||live.kind!==role||live.status!=='待确认收款'||!receiptOK(live)||!agreed||!date||date>today||date<live.payments[0].date){setError('仅本方可确认全额实际到账；请核对完整付款依据、版本并填写有效到账日期及勾选确认。');return}
        change('合作方确认收款',r=>{if(r.status!=='待确认收款'||r.receipt)return false;r.receipt={actor:PROTOTYPE.user,party:r.party,time:now(),date,amountCents:r.totalCents,paymentId:r.payments[0].id,version:r.version};r.status='已完成';r.receiptIssues.forEach(i=>{i.status='已关闭'})});
      }else if(action==='receiptIssue'){
        if(!['resource','channel'].includes(role)||live.kind!==role||live.status!=='待确认收款'||!reason.trim()||live.receiptIssues.some(i=>i.status==='待处理')){setError('请填写未到账或金额不符的原因；已有待处理反馈时不能重复提交。');return}
        change('收款异常反馈：'+reason,r=>r.receiptIssues.unshift({id:uid('ISSUE'),name:reason.trim(),actor:PROTOTYPE.user,time:now(),status:'待处理'}));
      }else if(action==='receiptReply'){
        if(role!=='platform'||live.status!=='待确认收款'||!reason.trim()||!live.receiptIssues.some(i=>i.status==='待处理')){setError('请填写本单待处理收款异常的核查意见。');return}
        change('平台核查收款异常：'+reason,r=>r.receiptIssues.filter(i=>i.status==='待处理').forEach(i=>{i.status='已回复';i.reply=reason.trim();i.replyAt=now();i.replyBy=PROTOTYPE.user}));
      }else if(action==='remind'){
        if(role!=='platform'||live.status!=='待确认收款'||!agreed){setError('请确认登记提醒，不代表收款或重新付款。');return}
        change('登记确认收款提醒（本地演示，未发送短信）',r=>{r.lastReceiptReminder=now()});
      }else if(action==='dispute'){
        if(!['resource','channel'].includes(role)||live.kind!==role||live.status!=='待对账确认'||!reason.trim()){setError('请填写本方对账异议说明。');return}change('合作方异议：'+reason,r=>{r.status='有异议';r.dispute=reason});
      }else if(action==='reply'){
        if(role!=='platform'||live.status!=='有异议'||!reason.trim()){setError('请填写异议处理意见。');return}change('平台回复：'+reason,r=>{r.status='待对账确认';r.confirmation=null});
      }
    };
    if(['resource','channel'].includes(role)&&PrototypeManagement.session()?.role!=='管理员')return h(React.Fragment,null,h('h2',null,'本人收益明细'),note('仅显示本人负责业务的交易及小计，不展示整单金额；对账确认、异议及收款确认由机构管理员处理。'),h(TransactionList,{statement:{id:'MY-DETAILS',scopeOnly:true,items:list.flatMap(s=>s.items||[])}}));
    return h(React.Fragment,null,!focusId&&note('每月1日归集截至上月末全部历史：仅门诊已结清且本方尚未入单的交易。对账确认 → 平台付款 → 合作方确认收款 → 完成。'),!focusId&&role==='platform'&&h(Pool,{pages,save}),!focusId&&h(W.RecordList,{items:list.map(s=>({...s,amount:(s.totalCents??cents(s.amount))/100})),states:['待对账确认','有异议','待付款','待确认收款','已完成','明细待补充','历史已结账'],columns:[['name','对账单'],['period','归集账期'],['party','收款机构'],['amount','应结金额（元）'],['version','版本'],['status','状态']],onView:r=>{setId(r.id);setError('')}}),s&&h(Drawer,{visible:true,escToExit:false,title:'对账单详情 · '+s.name,width:1160,footer:null,onCancel:()=>{setId(null);onClose?.()}},
      h(arco.Descriptions,{column:2,border:true,data:[{label:'编号',value:s.id},{label:'收款机构',value:s.party||window.PROTOTYPE.org},{label:'状态',value:s.status},{label:'应结金额',value:money(s.totalCents??cents(s.amount))+'元'},{label:'出账日期',value:s.issueDate||'历史未记录'},{label:'付款截止',value:s.deadline||'历史未记录'},{label:'期限口径',value:'月结：出账次日起5个自然日'},{label:'版本',value:s.version||'历史'},{label:'对账确认',value:s.confirmation?s.confirmation.actor+' / '+s.confirmation.time:'未确认'},{label:'收款确认',value:s.receipt?s.receipt.actor+' / '+s.receipt.time:'尚未确认到账'},{label:'实际到账日期',value:s.receipt?.date||'—'},{label:'收款确认金额',value:s.receipt?money(s.receipt.amountCents)+'元':'—'}]}),
      s.legacyStatement?note('旧记录只有汇总，没有逐笔明细或完整付款依据。保留历史状态，请补充原始交易；不能据此确认或付款。','warning'):h(React.Fragment,null,note('付款凭证不等于对方已到账；仅收款方确认后完成。推广产品、分配规则及门诊回款依据按交易保留。'),error&&!action&&note(error,'error'),h('div',{className:'flow-actions'},['resource','channel'].includes(role)&&s.kind===role&&s.status==='待对账确认'&&h(React.Fragment,null,btn('确认对账单',()=>start('confirm'),{type:'primary'}),btn('提出异议',()=>start('dispute'))),role==='platform'&&s.kind!=='platform'&&s.status==='待付款'&&btn('登记付款',()=>start('pay'),{type:'primary'}),role==='platform'&&s.status==='有异议'&&btn('处理异议',()=>start('reply'))),s.status==='待确认收款'&&h(React.Fragment,null,note('平台已登记付款，等待收款方核实到账；未到账请反馈，不重新付款。','warning'),h('div',{className:'flow-actions'},role===s.kind&&btn('确认收款',()=>start('receive'),{type:'primary'}),role===s.kind&&btn('反馈收款异常',()=>start('receiptIssue'),{disabled:s.receiptIssues.some(i=>i.status==='待处理')}),role==='platform'&&btn('提醒确认收款',()=>start('remind')),role==='platform'&&s.receiptIssues.some(i=>i.status==='待处理')&&btn('回复收款异常',()=>start('receiptReply')))),h(TransactionList,{statement:s}),h('h2',null,'收款异常与核查'),h(W.RecordList,{items:s.receiptIssues,states:['待处理','已回复','已关闭'],columns:[['name','反馈说明'],['actor','反馈人'],['time','反馈时间'],['reply','核查意见'],['replyBy','核查人'],['replyAt','核查时间'],['status','状态']]}),
      h('h2',null,'平台付款记录'),h(W.RecordList,{items:s.payments.map(p=>({...p,amount:p.amountCents/100})),states:['已登记'],columns:[['date','付款日期'],['payee','收款方'],['amount','金额（元）'],['reference','交易参考号'],['status','状态']]}),...s.payments.map(p=>h('section',{key:p.id},h('h3',null,'付款凭证 · '+p.reference),h(W.Files,{files:p.files}))),h(PrototypeManagement.Logs,{record:s}))),
      action&&h(Modal,{visible:true,title:({confirm:'确认对账单',pay:'登记平台付款',dispute:'提出异议',reply:'处理异议',receive:'确认收款',receiptIssue:'反馈收款异常',receiptReply:'回复收款异常',remind:'提醒确认收款'})[action],maskClosable:false,style:{width:760,maxWidth:'95vw'},onCancel:()=>setAction(null),okText:'提交',onOk:submit},note('当前单据 '+s.id+' · '+s.party+' · '+money(s.totalCents)+'元 · 版本'+s.version),error&&note(error,'error'),action==='pay'&&h(React.Fragment,null,W.field('付款金额（元）',h(InputNumber,{value:amount,onChange:v=>{setAmount(v);setError('')},precision:2,min:0})),W.field('付款日期',h(DatePicker,{value:date,onChange:v=>{setDate(v);setError('')}})),W.field('交易参考号',h(Input,{value:reference,onChange:v=>{setReference(v);setError('')}})),h(W.Files,{files,onChange:v=>{setFiles(v);setError('')},defaultKind:'付款凭证'})),action==='receive'&&W.field('实际到账日期',h(DatePicker,{value:date,onChange:setDate})),['dispute','reply','receiptIssue','receiptReply'].includes(action)?W.field('处理说明',h(Input.TextArea,{value:reason,onChange:setReason})):h(Checkbox,{checked:agreed,onChange:setAgreed},action==='receive'?'已核实本单款项全额实际到账':action==='remind'?'登记提醒收款方核实到账（演示不发送通知）':action==='pay'?'已在线下向本单收款机构全额付款，凭证与本笔交易一致':'已核对完整交易明细及金额，确认当前版本')));
  }
  return {prepare,migrate,product,sameProduct,words,TransactionList,Statements,transactions,collect,collectionReason};
})();
