/* Role-local sales prototype. No production payment, card secrets or cross-role synchronization. */
window.PrototypeSales = (() => {
  const h=React.createElement,{useState}=React,W=PrototypeWorkflows,O=PrototypeOperations;
  const {Button,Select,Input,InputNumber,Checkbox,Drawer,Modal,Alert,Descriptions,Upload,Tabs}=arco;
  const rows=(p,id)=>p.find(x=>x.id===id)?.rows||[],clone=v=>JSON.parse(JSON.stringify(v));
  const today='2026-09-07',uid=p=>p+'-'+Date.now()+'-'+Math.random().toString(36).slice(2,7);
  const physical='不记名实体卡',named='记名非实体卡',states=['待付款','付款待确认','待审核','已开卡','审核不通过','取消待审核','停止待审核','已取消','已停止'];
  const note=(text,type='info')=>h(Alert,{content:text,type,style:{marginBottom:16}}),btn=(text,onClick,props={})=>h(Button,{onClick,...props},text);
  const money=c=>(c/100).toFixed(2),integer=n=>Number.isSafeInteger(Number(n))&&Number(n)>0;
  const phone=v=>String(v??'').normalize('NFKC').replace(/[\s()-]/g,'').replace(/^(\+86|0086)/,'');
  const name=v=>String(v??'').trim();
  const active=c=>c&&['已生效','即将到期'].includes(c.status)&&c.start<=today&&c.end>=today;
  const catalog=p=>rows(p,'schemes').length?rows(p,'schemes'):PROTOTYPE.schemeCatalog||[];
  function authorized(p,productId,party){
    const product=O.product(p,productId);
    return product?.status==='已启用'&&rows(p,'contractSchemes').some(t=>t.status==='已启用'&&O.sameProduct(p,t.scheme,productId)&&rows(p,'contracts').some(c=>c.id===t.contract&&c.party===party&&active(c)));
  }
  function sources(p,party){return PROTOTYPE.role==='platform'?rows(p,'sources').filter(r=>r.owner===party&&r.status==='已启用').map(r=>r.name):PROTOTYPE.salesSources||[];}
  function inspect(items,p){
    const known=rows(p,'salesCustomers'),counts=new Map();
    items.forEach(r=>counts.set(phone(r.phone),(counts.get(phone(r.phone))||0)+1));
    return items.map((r,i)=>{
      const x={...r,id:r.id||'ROW-'+(i+1),name:name(r.name),phone:phone(r.phone),quantity:Number(r.quantity)};
      const found=known.find(c=>c.phone===x.phone);
      x.error=!x.name?'姓名必填':!/^1[3-9]\d{9}$/.test(x.phone)?'手机号格式不正确':!integer(x.quantity)||x.quantity>500?'数量须为1～500的整数':found&&found.name!==x.name?'手机号与姓名不一致':counts.get(x.phone)>1?(items.some(y=>phone(y.phone)===x.phone&&name(y.name)!==x.name)?'同表手机号与姓名冲突':'同表手机号重复，请核实原表；不会自动删除或累加'):'';
      x.status=x.error?'数据异常':found?'匹配已有客户':'新建未绑定客户';return x;
    });
  }
  function seed(role){
    const base={owner:role==='resource'?PROTOTYPE.org:'安和经纪（演示）',productId:'FA-001',productName:'舒适洁牙权益',externalName:'舒适洁牙服务',source:'安和保险客户福利',perCard:1,days:180,receipts:[],confirmedCents:0,cards:[],customers:[],history:[],refundStatus:'无需退款',shipping:'待制作',created:today,version:1};
    const a={...clone(base),id:'SALE-DEMO-FREE',name:'零元记名采购（演示）',mode:named,input:'单个客户',customers:[{id:'ROW-1',customerNo:'C001',name:'客户甲（演示）',phone:'13800000011',quantity:2}],quantity:2,unitCents:0,totalCents:0,status:'待审核'};
    const b={...clone(base),id:'SALE-DEMO-PAID',name:'实体卡采购（演示）',mode:physical,quantity:10,unitCents:200,totalCents:2000,status:role==='platform'?'付款待确认':'待付款'};
    if(role==='platform')b.receipts=[{id:'PURCHASE-REC-DEMO',status:'待确认',amountCents:2000,date:today,reference:'采购流水-DEMO',files:[W.sample('采购付款回单','付款凭证')]}];
    return [a,b];
  }
  function prepare(config){
    if(!['platform','resource'].includes(config.role))return;
    config.version='0.21';config.salesSources=config.pages.find(p=>p.id==='imports')?.create?.fields.find(f=>f.key==='source')?.options||[];
    for(const id of ['imports','orders',...(config.role==='resource'?['cards']:[])]){const p=config.pages.find(p=>p.id===id);if(p){p.hidden=true;p.actions=[];delete p.create;}}
    config.pages.splice(1,0,{id:'sales',title:'推广产品销售',custom:'sales',columns:[],rows:seed(config.role)});
    config.pages.push({id:'salesCustomers',title:'销售客户匹配样例',hidden:true,columns:[],rows:[{id:'SC-001',name:'客户甲（演示）',phone:'13800000011',registered:true}]});
    config.pages.push({id:'salesSerials',title:'演示号段登记',hidden:true,columns:[],rows:[{id:'SERIAL',next:1000001,status:'仅本地演示'}]});
  }
  function migrate(p){
    for(const r of rows(p,'sales')){r.receipts=r.receipts||[];r.history=r.history||[];r.cards=r.cards||[];r.customers=r.customers||[];}
    return p;
  }
  function validate(o,p){
    if(PROTOTYPE.role==='resource'&&o.owner!==PROTOTYPE.org)return '只能提交本机构采购订单。';
    if(![physical,named].includes(o.mode)||!authorized(p,o.productId,o.owner)||!sources(p,o.owner).includes(o.source))return '有效合同未授权该推广产品，或来源展示名不可用。';
    if(!integer(o.quantity)||o.quantity>500||!integer(o.perCard)||o.perCard>100)return '张数须为1～500、每卡份数须为1～100的整数（原型上限）。';
    if(!Number.isSafeInteger(o.unitCents)||o.unitCents<0||o.totalCents!==o.quantity*o.unitCents||!Number.isSafeInteger(o.totalCents))return '采购单价或总金额不正确。';
    if(o.mode===named){const details=inspect(o.customers,p);if(!details.length||details.some(x=>x.error)||details.reduce((n,r)=>n+r.quantity,0)!==o.quantity)return '客户资料存在异常或数量不一致，请检查逐笔明细。';}
    return '';
  }
  function approve(p,id,days,reason,agreed){
    const next=clone(p),o=rows(next,'sales').find(o=>o.id===id);
    if(PROTOTYPE.role!=='platform'||!o||o.status!=='待审核'||o.range||o.cards.length)return {error:'仅平台可审核待审核订单，已开卡不能重复生成。'};
    const error=validate(o,next);if(error)return {error};
    if(o.totalCents>0&&(o.confirmedCents!==o.totalCents||!o.receipts.some(r=>r.status==='已确认'&&r.amountCents===o.totalCents&&r.files.length&&r.files.every(W.fileOK))))return {error:'收费订单必须先由平台确认全额实际到账，才能审核开卡。'};
    if(!agreed||!reason.trim()||!integer(days)||days>3650)return {error:'请核对采购价格和资料、填写审核意见及有效期，并勾选确认。'};
    const product=O.product(next,o.productId);o.days=Number(days);o.productName=product.name;o.externalName=product.externalName;
    const serial=rows(next,'salesSerials')[0];
    if(o.mode===physical){
      const used=rows(next,'sales').map(r=>r.range?.end||0),start=Math.max(serial.next,...used.map(n=>n+1)),end=start+o.quantity-1;
      o.range={start,end,count:o.quantity,time:today,batch:'BATCH-'+o.id};serial.next=end+1;
      o.cards=Array.from({length:o.quantity},(_,i)=>({id:'DEMO-'+(start+i),name:o.productName,status:'未激活',entitlements:o.perCard}));
    }else{
      o.customers=inspect(o.customers,next);
      for(const item of o.customers){
        let customer=rows(next,'salesCustomers').find(c=>c.phone===item.phone);
        if(!customer){customer={id:uid('SC'),name:item.name,phone:item.phone,registered:false};rows(next,'salesCustomers').push(customer);}
        item.customerId=customer.id;item.status='待领取';item.error='';
        for(let n=0;n<item.quantity;n++)o.cards.push({id:uid('NAMED'),name:item.name,customerId:customer.id,phone:item.phone,status:'待领取',entitlements:o.perCard});
      }
    }
    o.status='已开卡';o.auditReason=reason.trim();o.auditBy=PROTOTYPE.user;o.auditAt=today;log(next,o,'审核通过并开卡');return {pages:next};
  }
  function log(p,o,label){o.history.unshift({id:uid('EVENT'),name:label,actor:PROTOTYPE.user,time:today,status:o.status});W.audit(p,label,o.id);}
  async function readExcel(file){
    const I=PrototypeImport,book=await I.readWorkbook(file);
    const d=I.configure(book,file.name,0,I.bestHeader(book.sheets[0]).number,PROTOTYPE.org);
    const error=I.problem(d);if(error)throw Error(error);
    const data=I.items(d);if(!data.length||data.length>200)throw Error('客户须为1～200条。');
    return data;
  }
  function Wizard({pages,save,onClose}){
    const [step,setStep]=useState(0),[draft,setDraft]=useState({mode:physical,input:'批量客户',quantity:100,perCard:1,price:0,productId:'',source:'',name:'',phone:'',customerNo:'',customerQuantity:1}),[importDraft,setImportDraft]=useState(PrototypeImport.initial),[error,setError]=useState(''),[submitting,setSubmitting]=useState(false);
    const put=(k,v)=>{setDraft(d=>({...d,[k]:v}));setError('');};
    const items=PrototypeImport.items(importDraft),file=importDraft.file,reading=importDraft.reading,batch=draft.mode===named&&draft.input==='批量客户';
    const importProblem=()=>batch?(!importDraft.confirmed?'请先确认列对应关系。':PrototypeImport.problem(importDraft)||(!items.length||items.length>200?'客户须为1～200条。':'')):'';
    const customers=draft.mode===physical?[]:draft.input==='单个客户'?[{name:draft.name,phone:draft.phone,customerNo:draft.customerNo,quantity:draft.customerQuantity}]:items;
    const checked=inspect(customers,pages),quantity=draft.mode===physical?Number(draft.quantity):checked.reduce((n,r)=>n+r.quantity,0),unitCents=Math.round(Number(draft.price)*100);
    const next=()=>{if(step===1&&importProblem()){setError(importProblem());return}if(step===1&&draft.mode===named&&(!checked.length||checked.some(c=>c.error))){setError('请先修正客户明细，异常数据不能提交。');return}setStep(step+1);setError('');};
    const submit=()=>{if(submitting)return;if(importProblem()){setError(importProblem());return}const product=O.product(pages,draft.productId),order={id:uid('SALE'),name:(draft.mode===physical?'实体卡':'记名卡')+'采购',owner:PROTOTYPE.org,ownerUserId:draft.ownerUserId||PrototypeManagement.session()?.id,mode:draft.mode,input:draft.input,customers:checked,quantity,perCard:Number(draft.perCard),unitCents,totalCents:quantity*unitCents,productId:draft.productId,productName:product?.name,externalName:product?.externalName,source:draft.source,file:batch?file:'',importSnapshot:batch?PrototypeImport.snapshot(importDraft):null,days:180,status:unitCents===0?'待审核':'待付款',confirmedCents:0,receipts:[],cards:[],history:[],refundStatus:'无需退款',shipping:'待制作',created:today,version:1};const problem=validate(order,pages);if(problem){setError(problem);return}setSubmitting(true);const next=clone(pages);rows(next,'sales').unshift(order);log(next,order,'提交采购订单');save(next);onClose(order.id);};
    return h(Drawer,{visible:true,width:900,title:'新建推广产品销售',maskClosable:false,footer:h('div',{className:'flow-actions'},step>0&&btn('上一步',()=>setStep(step-1)),step<2?btn('下一步',next,{type:'primary',disabled:reading}):btn('提交销售订单',submit,{type:'primary',disabled:submitting||reading})),onCancel:()=>Modal.confirm({title:'放弃未提交订单？',content:'关闭将放弃本次录入，已提交订单不受影响。',onOk:onClose})},
      note(['第1步：选择销售方式','第2步：录入客户或开卡数量','第3步：选择产品与采购价格'][step]),error&&note(error,'error'),
      step===0&&h(React.Fragment,null,W.field('订单负责业务员',h(Select,{value:draft.ownerUserId||PrototypeManagement.session()?.id,disabled:PrototypeManagement.session()?.role!=='管理员',options:rows(pages,'accounts').map(a=>({value:a.id,label:a.name+' · '+a.role})),onChange:v=>put('ownerUserId',v)})),W.field('销售方式',h(Select,{value:draft.mode,options:[physical,named],onChange:v=>put('mode',v)})),draft.mode===named&&W.field('客户录入方式',h(Select,{value:draft.input,options:['批量客户','单个客户'],onChange:v=>put('input',v)})),note('实体卡不提前绑定客户；记名非实体卡审核后为指定客户生成待领取权益。')),
      step===1&&(draft.mode===physical?h(React.Fragment,null,note('无需客户资料或Excel，系统审核开卡时自动分配唯一演示号段。'),W.field('开卡张数',h(InputNumber,{value:draft.quantity,onChange:v=>put('quantity',v),min:1,max:500,precision:0}))):draft.input==='批量客户'?h(PrototypeImport.Editor,{value:importDraft,onChange:setImportDraft,pages}):h(React.Fragment,null,...[['customerNo','客户编号'],['name','客户姓名'],['phone','客户手机号']].map(([k,label])=>W.field(label,h(Input,{value:draft[k],onChange:v=>put(k,v)}))),W.field('客户开卡张数',h(InputNumber,{value:draft.customerQuantity,onChange:v=>put('customerQuantity',v),min:1,max:500,precision:0})),h(W.RecordList,{items:checked,states:['匹配已有客户','新建未绑定客户','数据异常'],columns:[['name','客户'],['phone','手机号'],['quantity','开卡张数'],['status','校验结果'],['error','异常原因']]}))),
      step===2&&h(React.Fragment,null,W.field('推广产品',h(Select,{value:draft.productId,options:catalog(pages).filter(p=>authorized(pages,p.id,PROTOTYPE.org)).map(p=>({label:p.name,value:p.id})),onChange:v=>put('productId',v)})),W.field('来源展示名',h(Select,{value:draft.source,options:sources(pages,PROTOTYPE.org),onChange:v=>put('source',v)})),W.field('每卡权益份数',h(InputNumber,{value:draft.perCard,onChange:v=>put('perCard',v),min:1,max:100,precision:0})),W.field('单卡采购价（元）',h(InputNumber,{value:draft.price,onChange:v=>put('price',v),min:0,precision:2})),h(Descriptions,{column:1,border:true,data:[{label:'销售方式',value:draft.mode},{label:'客户人数',value:draft.mode===named?new Set(checked.map(r=>r.phone)).size+'人':'激活后绑定'},{label:'开卡张数',value:quantity},{label:'权益总份数',value:quantity*draft.perCard},{label:'采购总金额',value:money(quantity*unitCents)+'元'},{label:'付款关系',value:'本资源方向平台付款，不是客户付款或门诊获客费'}]}),note(unitCents===0?'零元采购：提交后平台审核，审核通过开卡。':'收费采购：提交订单后付款，平台确认全额到账才可审核开卡。')));
  }
  function View({pages,save,focusId,onClose}){
    const role=PROTOTYPE.role,[id,setId]=useState(focusId||null),[creating,setCreating]=useState(false),[action,setAction]=useState(null),[error,setError]=useState(''),[reason,setReason]=useState(''),[agreed,setAgreed]=useState(false),[files,setFiles]=useState([]),[reference,setReference]=useState(''),[days,setDays]=useState(180),[tab,setTab]=useState('销售订单'),[legacy,setLegacy]=useState(null);
    const list=rows(pages,'sales').filter(o=>role==='platform'||o.owner===PROTOTYPE.org),order=list.find(o=>o.id===id);
    const start=a=>{setAction(a);setError('');setReason('');setAgreed(false);setFiles([]);setReference('');setDays(order.days||180);};
    const change=(label,fn)=>{const next=clone(pages),o=rows(next,'sales').find(o=>o.id===id);const problem=fn(o,next);if(problem){setError(problem);return}log(next,o,label);save(next);setAction(null);setError('');};
    const submit=()=>{
      if(action==='approve'){const result=approve(pages,id,days,reason,agreed);if(result.error)setError(result.error);else{save(result.pages);setAction(null);setError('');}return;}
      if(!reason.trim()){setError('请填写处理说明。');return;}
      change(({voucher:'提交采购付款凭证',receipt:'确认采购全额到账',return:'退回付款凭证',reject:'审核不通过',cancel:'申请取消采购',cancelReview:'审核取消采购',stop:'停止剩余未领取权益',refund:'登记线下采购退款',ship:'登记制作寄送'})[action],(o,next)=>{
        if(!o||role==='resource'&&o.owner!==PROTOTYPE.org)return '无权操作该订单。';
        const paid=o.receipts.find(r=>r.status==='待确认');
        if(action==='voucher'){
          if(role!=='resource'||o.status!=='待付款'||!agreed||!reference.trim()||!files.length||files.some(f=>!W.fileOK(f)))return '请确认已全额付款，填写流水号并上传可读凭证。';
          if(rows(next,'sales').some(s=>s.receipts.some(r=>r.reference===reference.trim())))return '该采购付款流水号已登记，不可重复使用。';
          o.receipts.push({id:uid('PREC'),amountCents:o.totalCents,date:today,reference:reference.trim(),files:clone(files),status:'待确认',reason});o.status='付款待确认';
        }else if(action==='receipt'||action==='return'){
          if(role!=='platform'||o.status!=='付款待确认'||!paid)return '当前没有可审核的付款凭证。';
          if(action==='receipt'&&(!agreed||paid.amountCents!==o.totalCents||!paid.files.length||paid.files.some(f=>!W.fileOK(f))))return '请核实全额实际到账及全部可读凭证。';
          paid.status=action==='receipt'?'已确认':'已退回';paid.review=reason;paid.reviewer=PROTOTYPE.user;o.status=action==='receipt'?'待审核':'待付款';if(action==='receipt')o.confirmedCents=o.totalCents;
        }else if(action==='reject'){
          if(role!=='platform'||o.status!=='待审核')return '仅平台可拒绝待审核订单。';o.status='审核不通过';if(o.confirmedCents>0)o.refundStatus='待退款';
        }else if(action==='cancel'){
          if(role!=='resource'||!['待付款','待审核','已开卡'].includes(o.status))return '当前订单不可取消；付款待确认时先核实款项。';
          if(o.cards.some(c=>!['未激活','待领取'].includes(c.status)))return '已有客户领取或激活，不能整单取消。';o.beforeCancel=o.status;o.status='取消待审核';
        }else if(action==='cancelReview'){
          if(role!=='platform'||o.status!=='取消待审核'||!agreed||o.cards.some(c=>!['未激活','待领取'].includes(c.status)))return '请核实整单未领取/未激活后确认取消。';o.cards.forEach(c=>{c.status='已作废';c.voidAt=today;});o.status='已取消';if(o.confirmedCents>0)o.refundStatus='待退款';
        }else if(action==='stop'){
          if(o.mode!==named||!['已开卡','停止待审核'].includes(o.status)||!agreed||!o.cards.some(c=>c.status==='待领取'))return '仅存在待领取权益的记名订单可申请或审核停止。';if(role==='resource'){if(o.status!=='已开卡')return '请等待平台审核。';o.status='停止待审核';}else{o.cards.filter(c=>c.status==='待领取').forEach(c=>{c.status='已停止';c.voidAt=today;});o.status='已停止';}
        }else if(action==='refund'){
          if(role!=='platform'||o.refundStatus!=='待退款'||!agreed||!reference.trim()||!files.length||files.some(f=>!W.fileOK(f)))return '请核实全额线下退款、填写流水并上传凭证。';if(rows(next,'sales').some(s=>s.refund?.reference===reference.trim()))return '该退款流水已登记。';o.refundStatus='已登记退款';o.refund={amountCents:o.confirmedCents,date:today,reference:reference.trim(),files:clone(files),reason};
        }else if(action==='ship'){
          if(role!=='platform'||o.mode!==physical||o.status!=='已开卡'||!reference.trim())return '请填写物流公司及运单号。';o.shipping='已寄送';o.tracking=reference;o.shippingNote=reason;
        }else return '不支持的操作。';
      });
    };
    const history=rows(pages,'imports').map(r=>({...r,legacyType:'Excel批次'})).concat(rows(pages,'orders').map(r=>({...r,legacyType:'开卡订单'})),rows(pages,'cards').map(r=>({...r,legacyType:'卡批次'})));
    return h(React.Fragment,null,!focusId&&h(React.Fragment,null,h('div',{className:'page-heading'},h('div',null,h('h1',null,'推广产品销售'),h('p',null,role==='resource'?'统一向平台采购产品，查看客户、卡片与订单处理进度':'核实采购款到账，再审核开卡；与门诊回款及合作方收益结算分开'))),role==='resource'&&btn('新建销售订单',()=>setCreating(true),{type:'primary'}),h(Tabs,{activeTab:tab,onChange:setTab},...['销售订单','历史批次记录'].map(t=>h(Tabs.TabPane,{key:t,title:t},tab===t&&(t==='销售订单'?h(W.RecordList,{items:list.map(o=>({...o,amount:o.totalCents/100})),states,tableWidth:1100,columns:[['id','销售订单'],['mode','销售方式'],['owner','采购方'],['productName','推广产品'],['quantity','张数'],['amount','采购金额（元）'],['status','状态']],onView:o=>{setId(o.id);setError('');}}):h(React.Fragment,null,note('原始批次和订单只读保留，不补造采购价、付款或新卡。新业务统一在销售订单办理；历史处置需依据原材料。','warning'),h(W.RecordList,{items:history,states:[],columns:[['id','原编号'],['legacyType','原记录类型'],['name','原名称'],['quantity','数量'],['status','原状态']],onView:setLegacy}))))))),
      legacy&&h(Drawer,{visible:true,title:'历史原始记录',width:760,footer:null,onCancel:()=>setLegacy(null)},h(Descriptions,{column:1,data:Object.entries(legacy).filter(([k,v])=>!k.startsWith('legacy')&&typeof v!=='object').map(([label,value])=>({label,value:String(value)}))})),
      creating&&h(Wizard,{pages,save,onClose:newId=>{setCreating(false);if(typeof newId==='string')setTab('销售订单');}}),order&&h(Drawer,{visible:true,width:1080,title:'销售订单详情 · '+order.id,footer:null,onCancel:()=>{setId(null);setAction(null);onClose?.();}},
        h(Descriptions,{column:2,border:true,data:[['订单状态',order.status],['销售方式',order.mode],['采购方',order.owner],['推广产品',order.productName],['来源展示名',order.source],['开卡张数',order.quantity],['每卡权益份数',order.perCard],['采购单价',money(order.unitCents)+'元'],['采购总金额',money(order.totalCents)+'元'],['平台确认到账',money(order.confirmedCents)+'元'],['有效期',order.days+'天，从领取/激活起算'],['退款状态',order.refundStatus],['号段',order.range?'DEMO-'+order.range.start+' ～ DEMO-'+order.range.end:'尚未生成或无需实体号段'],['物流',order.mode===physical?(order.tracking||order.shipping):'非实体卡，无需寄送']].map(([label,value])=>({label,value}))}),
        order.mode===named&&order.input==='批量客户'&&h(PrototypeImport.Receipt,{value:order.importSnapshot}),
        note('资源方向平台支付采购款。零元仍需审核；收费必须全额到账后审核。提交后不能静默改数量、客户或价格。'),error&&!action&&note(error,'error'),h('div',{className:'flow-actions'},
          role==='resource'&&order.status==='待付款'&&btn('上传采购付款凭证',()=>start('voucher'),{type:'primary'}),role==='platform'&&order.status==='付款待确认'&&h(React.Fragment,null,btn('确认采购收款',()=>start('receipt'),{type:'primary'}),btn('退回付款凭证',()=>start('return'))),role==='platform'&&order.status==='待审核'&&h(React.Fragment,null,btn('审核通过并开卡',()=>start('approve'),{type:'primary'}),btn('审核不通过',()=>start('reject'))),role==='resource'&&['待付款','待审核','已开卡'].includes(order.status)&&btn('申请取消订单',()=>start('cancel')),role==='platform'&&order.status==='取消待审核'&&btn('审核取消',()=>start('cancelReview')),order.mode===named&&(['已开卡'].includes(order.status)||role==='platform'&&order.status==='停止待审核')&&btn(role==='resource'?'申请停止剩余未领取':'停止剩余未领取',()=>start('stop')),role==='platform'&&order.refundStatus==='待退款'&&btn('登记线下退款',()=>start('refund')),role==='platform'&&order.mode===physical&&order.status==='已开卡'&&btn('登记制作寄送',()=>start('ship'))),
        order.mode===named&&h(React.Fragment,null,h('h2',null,'客户明细与匹配校验'),h(W.RecordList,{items:inspect(order.customers,pages),states:['匹配已有客户','新建未绑定客户','数据异常'],columns:[['name','客户'],['phone','手机号'],['quantity','张数'],['status','校验'],['error','异常原因']]})),
        h('h2',null,order.mode===physical?'卡号与激活状态':'记名卡与领取状态'),h(W.RecordList,{items:order.cards,states:order.mode===physical?['未激活','已激活','已作废']:['待领取','已领取','已停止','已作废'],columns:[['id','演示卡编号'],['name','产品或客户'],['entitlements','权益份数'],['status','状态']],exportName:order.id+'-卡明细'}),
        h('h2',null,'采购付款与退款凭证'),...order.receipts.map(r=>h('section',{key:r.id},h('h3',null,r.reference+' · '+r.status+' · '+money(r.amountCents)+'元'),r.review&&note(r.review),h(W.Files,{files:r.files}))),order.refund&&h(W.Files,{files:order.refund.files}),h(PrototypeManagement.Logs,{record:order})),
      action&&h(Modal,{visible:true,title:({voucher:'上传采购付款凭证',receipt:'确认采购收款',return:'退回付款凭证',approve:'审核通过并开卡',reject:'审核不通过',cancel:'申请取消订单',cancelReview:'审核取消',stop:'停止剩余未领取',refund:'登记线下退款',ship:'登记制作寄送'})[action],maskClosable:false,style:{width:760,maxWidth:'95vw'},onCancel:()=>setAction(null),okText:'提交',onOk:submit},note(order.id+' · 采购总额 '+money(order.totalCents)+'元 · '+order.owner),error&&note(error,'error'),action==='approve'&&W.field('审核有效期（天）',h(InputNumber,{value:days,onChange:setDays,min:1,max:3650,precision:0})),['voucher','refund','ship'].includes(action)&&W.field(action==='ship'?'物流公司及运单号':'采购/退款交易流水号',h(Input,{value:reference,onChange:setReference})),['voucher','refund'].includes(action)&&h(W.Files,{files,onChange:setFiles,defaultKind:'付款凭证'}),action==='receipt'&&order.receipts.filter(r=>r.status==='待确认').map(r=>h(W.Files,{key:r.id,files:r.files})),W.field('处理说明',h(Input.TextArea,{value:reason,onChange:setReason})),['approve','receipt','voucher','cancelReview','stop','refund'].includes(action)&&h(Checkbox,{checked:agreed,onChange:setAgreed},action==='approve'?'已核对产品授权、采购价格与全部客户资料':action==='receipt'?'已核实本单采购款全额实际到账':action==='voucher'?'已在线下向平台全额付款':action==='refund'?'已在线下全额退款给原采购方':'已核实操作范围及影响')));
  }
  return {prepare,migrate,View,authorized,inspect,approve,readExcel};
})();
