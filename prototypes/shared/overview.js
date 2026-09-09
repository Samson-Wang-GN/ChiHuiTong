/* Read-only, role-local analysis. Event snapshots are not a production analytics service. */
window.PrototypeOverview = (() => {
  const h=React.createElement,{useState}=React,W=PrototypeWorkflows,O=PrototypeOperations;
  const {Button,Select,DatePicker,Drawer,Alert,Descriptions,Card,Empty}=arco;
  const rows=(p,id)=>p.find(x=>x.id===id)?.rows||[],endDate='2026-09-09';
  const named='记名非实体卡',physical='不记名实体卡';
  const date=d=>d.toISOString().slice(0,10),day=(s,n)=>date(new Date(Date.parse(s+'T00:00:00Z')+n*86400000));
  const notice=(content,type='info')=>h(Alert,{content,type,style:{marginBottom:16}});
  const metrics={
    customers:['客户总数','人','已建立关系的客户去重；记名包括未注册客户，不记名激活前不计人。'],
    purchased:['有效采购数量','张','已审核开卡，扣除截至观察时点已取消、作废或停止的卡。'],
    voided:['取消/作废/停止','张','退出有效采购的卡张数；不删除原开卡事实。'],
    activated:['已激活数量','张','不记名激活或记名领取成功；已用完或过期不抹去激活事实。'],
    appointments:['累计有效预约','次','截至观察时点待确认＋成功＋完成（含系统超时完成）；不代表到诊，取消不计，改期不新增次数。'],
    redemptions:['有效核销','次','真实核销且未撤销的记录；系统超时完成不计核销，与是否结算无关。'],
    units:['核销权益份数','份','有效核销实际消耗的份数，与卡张数、核销次数分开。'],
    activePeople:['激活客户数','人','当前范围内至少激活一张有效卡的去重客户。'],
    bookingPeople:['预约客户数','人','当前范围内至少有一笔有效预约的去重客户。'],
    redeemedPeople:['核销客户数','人','当前范围内至少有一笔有效核销的去重客户。'],
    activationRate:['卡片激活率','%','同一批次集合：已激活卡张数 ÷ 有效采购张数。','activated','purchased'],
    bookingRate:['客户预约率','%','同一批次集合：预约客户数 ÷ 激活客户数。','bookingPeople','activePeople'],
    redemptionRate:['客户核销率','%','同一批次集合：核销客户数 ÷ 预约客户数。','redeemedPeople','bookingPeople']
  };
  const format=(k,v)=>v===null?'—':metrics[k][1]==='%'?v.toFixed(1)+'%':String(v);
  function seed(role,org){
    const facts=[];
    const parties=role==='platform'?['安和经纪（演示）','星海银行（演示）']:[org];
    for(const [ownerIndex,owner] of parties.entries())for(let i=0;i<36;i++){
      const productId=i<24?'FA-001':'FA-002',mode=i%2?physical:named;
      const purchasedAt=day('2026-08-01',i%18*2),activatedAt=i%4===0?null:day(purchasedAt,2);
      const customerId='SC-'+String(i%15+1).padStart(3,'0');
      const card={id:'AN-CARD-'+ownerIndex+'-'+i,order:'AN-ORDER-'+ownerIndex+'-'+Math.floor(i/6),owner,productId,productName:i<24?'舒适洁牙权益':'种植牙抵用权益',mode,purchasedAt,customerId:mode===named||activatedAt?customerId:null,customerName:i%15===0?'客户甲（演示）':'分析客户'+(i%15+1)+'（演示）',boundAt:mode===named?purchasedAt:activatedAt,activatedAt,voidAt:i%12===0?day(purchasedAt,6):null,appointments:[],origin:'独立分析样例'};
      if(activatedAt&&i%3!==0){
        const createdAt=day(activatedAt,2),a={id:'AN-APPT-'+ownerIndex+'-'+i,createdAt,changes:[{at:createdAt,status:'待确认'}],redemptions:[]};
        if(i%5!==0)a.changes.push({at:day(createdAt,1),status:'成功'});
        if(i%5===1){a.changes.push({at:day(createdAt,5),status:'取消'});}
        else if(i%5>=2){a.changes.push({at:day(createdAt,3),status:'完成'});a.redemptions.push({id:'AN-REDEEM-'+ownerIndex+'-'+i,at:day(createdAt,3),units:i%2+1,revokedAt:i%7===0?day(createdAt,5):null});if(i%7===0)a.changes.push({at:day(createdAt,5),status:'成功'});}
        card.appointments.push(a);
      }
      facts.push(card);
    }
    return facts;
  }
  function prepare(config){
    if(!['platform','resource'].includes(config.role))return;
    config.version='0.22';
    const existing=config.pages.find(p=>p.id==='customers');
    if(existing){existing.title='客户与权益概览';existing.custom='overview';existing.actions=[];delete existing.create;}
    else config.pages.splice(2,0,{id:'customers',title:'客户与权益概览',custom:'overview',columns:[],rows:[]});
    config.pages.push({id:'overviewFacts',title:'分析事件样例',hidden:true,columns:[],rows:seed(config.role,config.org)});
  }
  function facts(pages,role=PROTOTYPE.role,org=PROTOTYPE.org){
    if(!['platform','resource'].includes(role))return {cards:[],excluded:0};
    const allowed=x=>role==='platform'||x.owner===org;
    const result=rows(pages,'overviewFacts').filter(allowed).map(x=>({...x}));let excluded=0;
    for(const o of rows(pages,'sales').filter(allowed)){
      if(!o.cards?.length)continue;
      for(const c of o.cards){
        if(!o.auditAt||(['已作废','已停止'].includes(c.status)&&!c.voidAt)||(['已领取','已激活','已核销'].includes(c.status)&&(!c.activatedAt||!c.customerId))){excluded++;continue;}
        result.push({id:o.id+':'+c.id,order:o.id,owner:o.owner,productId:o.productId,productName:o.productName,mode:o.mode,purchasedAt:o.auditAt.slice(0,10),customerId:c.customerId||null,customerName:o.mode===named?c.name:'未绑定',boundAt:o.mode===named?o.auditAt.slice(0,10):c.activatedAt,activatedAt:c.activatedAt||null,voidAt:c.voidAt||null,appointments:[],origin:'本角色销售订单'});
      }
    }
    return {cards:[...new Map(result.map(c=>[c.id,c])).values()],excluded};
  }
  function filter(cards,f){return cards.filter(c=>(f.owner==='all'||c.owner===f.owner)&&(f.product==='all'||c.productId===f.product)&&(f.mode==='all'||c.mode===f.mode)&&c.purchasedAt>=f.from&&c.purchasedAt<=f.to);}
  const before=(d,at)=>!!d&&d<=at;
  const unique=(list,key)=>[...new Map(list.map(x=>[key(x),x])).values()];
  function snapshot(cards,at){
    const issued=cards.filter(c=>before(c.purchasedAt,at)),voided=issued.filter(c=>before(c.voidAt,at)),valid=issued.filter(c=>!before(c.voidAt,at));
    const customers=unique(issued.filter(c=>c.customerId&&before(c.boundAt,at)),c=>c.customerId);
    const activated=valid.filter(c=>c.customerId&&before(c.activatedAt,at));
    const appointments=[];
    for(const card of activated)for(const a of card.appointments||[]){
      if(!before(a.createdAt,at))continue;
      const changes=a.changes.filter(s=>before(s.at,at)).sort((a,b)=>a.at.localeCompare(b.at));
      const status=changes.at(-1)?.status;
      if(['待确认','成功','完成'].includes(status))appointments.push({...a,status,completionSource:status==='完成'?(changes.at(-1)?.completionSource||((a.redemptions||[]).some(r=>before(r.at,at)&&!before(r.revokedAt,at))?'门诊核销完成':'来源待补充')):'—',card});
    }
    const bookings=unique(appointments,a=>a.id),redemptions=[];
    for(const a of bookings)for(const r of a.redemptions||[])if(before(r.at,at)&&!before(r.revokedAt,at))redemptions.push({...r,card:a.card,appointment:a.id});
    const checks=unique(redemptions,r=>r.id),people=(list,get)=>unique(list,get);
    const sets={customers,purchased:valid,voided,activated,appointments:bookings,redemptions:checks,units:checks,activePeople:people(activated,c=>c.customerId),bookingPeople:people(bookings,a=>a.card.customerId),redeemedPeople:people(checks,r=>r.card.customerId)};
    const values=Object.fromEntries(Object.entries(sets).map(([k,v])=>[k,k==='units'?v.reduce((n,r)=>n+r.units,0):v.length]));
    for(const [k,m]of Object.entries(metrics))if(m[3])values[k]=values[m[4]]?values[m[3]]/values[m[4]]*100:null;
    return {values,sets};
  }
  function buckets(from,to,unit){
    const out=[];let start=from;
    while(start<=to){let end=start;
      if(unit==='week'){const d=new Date(start+'T00:00:00Z');end=day(start,(7-d.getUTCDay())%7);}
      if(unit==='month'){const d=new Date(start+'T00:00:00Z');end=date(new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)));}
      end=end>to?to:end;out.push({start,end});start=day(end,1);
    }
    return out;
  }
  function series(cards,k,from,to,unit,mode){
    const m=metrics[k];return buckets(from,to,unit).map(b=>{
      const now=snapshot(cards,b.end).values,previous=snapshot(cards,day(b.start,-1)).values;
      const value=m[3]||mode==='累计'?now[k]:now[k]-previous[k];
      return {id:b.end,start:b.start,end:b.end,label:b.start===b.end?b.end:b.start+' ～ '+b.end,value,display:format(k,value),numerator:m[3]?now[m[3]]:'—',denominator:m[4]?now[m[4]]:'—',status:value===null?'无分母':'有数据'};
    });
  }
  function details(cards,k,at){
    const s=snapshot(cards,at);return s.sets[k].map(x=>{
      const c=x.card||x,person=k.endsWith('People')||k==='customers';
      const activated=before(c.activatedAt,at),voided=before(c.voidAt,at);
      return {id:person?c.customerId:x.id,name:person?c.customerName:x.id,customer:c.customerId?c.customerName:'未绑定',owner:c.owner,product:c.productName,order:c.order,card:c.id,time:x.createdAt||x.at||c.purchasedAt,units:k==='units'?x.units:'—',completionSource:k==='appointments'?x.completionSource:'—',status:person?(k==='customers'?'已关联':k==='activePeople'?'已激活':k==='bookingPeople'?'已预约':'已核销'):k==='appointments'?x.status:k==='redemptions'||k==='units'?'有效核销':voided?'已作废/停止':activated?'已激活':c.mode===named?'待领取':'未激活'};
    });
  }
  function Chart({points,metric,onPoint}){
    const values=points.map(p=>p.value).filter(v=>v!==null),min=Math.min(0,...values),max=Math.max(metrics[metric][3]?100:1,...values),height=210;
    const x=i=>60+i*700/Math.max(1,points.length-1),y=v=>30+(max-v)/(max-min)*height;
    const parts=[];let part=[];points.forEach((p,i)=>{if(p.value===null){if(part.length)parts.push(part);part=[];}else part.push([x(i),y(p.value)]);});if(part.length)parts.push(part);
    if(!points.length)return h(Empty,{description:'当前范围没有时间点'});
    return h('div',{className:'overview-chart'},h('svg',{viewBox:'0 0 820 300',role:'img','aria-label':metrics[metric][0]+'变化曲线'},h('title',null,metrics[metric][0]+'；精确数值与分子分母见下方列表'),...[0,1,2,3].map(i=>{const v=min+(max-min)*i/3;return h('g',{key:i},h('line',{x1:60,x2:760,y1:y(v),y2:y(v),stroke:'var(--color-border-2)'}),h('text',{x:50,y:y(v)+4,textAnchor:'end',fill:'var(--color-text-3)',fontSize:12},v.toFixed(metrics[metric][3]?1:0)))}),...parts.map((p,i)=>h('polyline',{key:'line'+i,points:p.map(v=>v.join(',')).join(' '),fill:'none',stroke:'rgb(var(--primary-6))',strokeWidth:2})),...points.map((p,i)=>h('g',{key:p.id},p.value!==null&&h('circle',{cx:x(i),cy:y(p.value),r:4,fill:'rgb(var(--primary-6))',onClick:()=>onPoint(p.end)},h('title',null,p.label+'：'+p.display)),(i===0||i===points.length-1||i%Math.max(1,Math.ceil(points.length/6))===0)&&h('text',{x:x(i),y:265,textAnchor:'middle',fill:'var(--color-text-3)',fontSize:12},p.end.slice(5))))),!values.length&&notice('全部时间点分母为0，暂不绘制百分比曲线。'));
  }
  function View({pages,viewState='正常',onRetry}){
    const source=facts(pages),all=source.cards;
    const defaults={owner:'all',product:'all',mode:'all',from:'2026-08-01',to:endDate};
    const [draft,setDraft]=useState(defaults),[f,setF]=useState(defaults),[error,setError]=useState(''),[focus,setFocus]=useState(null),[unit,setUnit]=useState('day'),[trendMode,setTrendMode]=useState('累计'),[side,setSide]=useState('分子'),[point,setPoint]=useState(endDate),[record,setRecord]=useState(null),[legacy,setLegacy]=useState(false);
    const allowed=filter(all,f),cards=viewState==='空状态'?[]:allowed,summary=snapshot(cards,endDate).values;
    const owners=[...new Set(all.map(c=>c.owner))],products=[...new Map(all.map(c=>[c.productId,{id:c.productId,name:O.product(pages,c.productId)?.name||c.productName,status:O.product(pages,c.productId)?.status||'历史产品'}])).values()];
    const put=(k,v)=>setDraft(d=>({...d,[k]:v}));
    const open=(metric,product='all')=>{setFocus({metric,product});setUnit('day');setTrendMode('累计');setSide('分子');setPoint(endDate);setRecord(null);};
    const productRows=products.filter(p=>f.product==='all'||f.product===p.id).map(p=>({...p,...snapshot(cards.filter(c=>c.productId===p.id),endDate).values}));
    const keys=['customers','purchased','activated','appointments','redemptions','activationRate','bookingRate','redemptionRate'];
    const tableRows=productRows.map(p=>({...p,...Object.fromEntries(keys.map(k=>[k+'Cell',h(Button,{type:'text',onClick:()=>open(k,p.id),'aria-label':p.name+' '+metrics[k][0]+'趋势'},format(k,p[k]))]))}));
    const exportSummary=(selected,scope)=>PrototypeExcel.download('客户权益产品汇总-演示',[{name:'统计说明',rows:[['项目','内容'],['范围',scope],['开卡批次',f.from+' 至 '+f.to],['资源方',PROTOTYPE.role==='resource'?PROTOTYPE.org:f.owner],['观察截止',endDate],['销售方式',f.mode],['口径','同一开卡批次集合；比例为百分比数值，零分母为空']]},{name:'产品汇总',rows:[['产品编号','推广产品','状态',...keys.map(k=>metrics[k][0]+'（'+metrics[k][1]+'）')],...selected.map(p=>[p.id,p.name,p.status,...keys.map(k=>p[k]??'')])]}]);
    const m=focus&&metrics[focus.metric],focused=focus?(focus.product==='all'?cards:cards.filter(c=>c.productId===focus.product)):[];
    const points=focus?series(focused,focus.metric,f.from,endDate,unit,trendMode):[],detailKey=m?.[3]?(side==='分子'?m[3]:m[4]):focus?.metric;
    const detailRows=focus?details(focused,detailKey,point):[],productTitle=focus?.product==='all'?'当前筛选全部产品':products.find(p=>p.id===focus?.product)?.name;
    const downloadDetails=(selected,scope)=>PrototypeExcel.download('客户权益指标明细-演示',[{name:'统计说明',rows:[['项目','内容'],['指标',m[0]],['说明',m[2]],['明细口径',metrics[detailKey][0]],['产品',productTitle],['开卡批次',f.from+' 至 '+f.to],['资源方',PROTOTYPE.role==='resource'?PROTOTYPE.org:f.owner],['销售方式',f.mode],['观察时点',point],['筛选',scope],['记录数',selected.length]]},{name:'指标明细',rows:[['编号','客户','资源方','推广产品','来源订单','来源卡','时间','权益份数','状态','完成来源'],...selected.map(r=>[r.id,r.customer,r.owner,r.product,r.order,r.card,r.time,r.units,r.status,r.completionSource])]}]);
    return h('div',{className:'workflow overview'},h('div',{className:'page-heading'},h('div',null,h('h1',null,'客户与权益概览'),h('p',null,PROTOTYPE.role==='platform'?'查看全平台或指定资源方的产品投放及客户转化':'仅统计本机构来源权益 · 查看产品投放及客户转化'))),
      notice('分析样例＋本角色可追溯销售卡 · 观察截止 '+endDate+'（北京时间）· 不含尚未审核开卡的采购申请。'),
      h('section',{className:'panel overview-filters'},PROTOTYPE.role==='platform'&&W.field('客户资源方',h(Select,{value:draft.owner,options:[{label:'全部资源方',value:'all'},...owners.map(value=>({label:value,value}))],onChange:v=>put('owner',v)})),W.field('推广产品',h(Select,{value:draft.product,options:[{label:'全部推广产品',value:'all'},...products.map(p=>({label:p.name,value:p.id}))],onChange:v=>put('product',v)})),W.field('销售方式',h(Select,{value:draft.mode,options:[{label:'全部销售方式',value:'all'},named,physical],onChange:v=>put('mode',v)})),W.field('开卡批次起日',h(DatePicker,{value:draft.from,allowClear:false,onChange:v=>put('from',v)})),W.field('开卡批次止日',h(DatePicker,{value:draft.to,allowClear:false,onChange:v=>put('to',v)})),h('div',{className:'flow-actions'},h(Button,{type:'primary',onClick:()=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(draft.from)||!/^\d{4}-\d{2}-\d{2}$/.test(draft.to)||draft.from>draft.to||draft.to>endDate||draft.from<'2025-01-01'){setError('请选择2025-01-01至观察截止日内的有效起止日期。');return}setF({...draft});setError('');setFocus(null);}},'查询'),h(Button,{onClick:()=>{setDraft(defaults);setF(defaults);setError('');setFocus(null);}},'重置条件'))),error&&notice(error,'error'),
      h('p',{className:'muted'},'批次 '+f.from+' ～ '+f.to+'；下方观察这些卡截至 '+endDate+' 的后续转化。人数跨产品/资源方去重，不直接相加。'),source.excluded>0&&notice(source.excluded+'张历史销售卡缺少开卡、激活或作废日期，未纳入分析；请补充可信记录。','warning'),
      viewState==='加载中'?h(arco.Spin,{loading:true,tip:'正在汇总客户权益'},h('div',{style:{height:180}})):viewState==='加载失败'?h(arco.Result,{status:'error',title:'统计数据加载失败',subTitle:'筛选条件已保留，请重试。',extra:h(Button,{onClick:onRetry},'重试')}):h(React.Fragment,null,...[false,true].map(rate=>h('div',{className:'overview-metrics'+(rate?' overview-rates':''),key:String(rate)},...Object.keys(metrics).filter(k=>!!metrics[k][3]===rate).map(k=>h(Card,{key:k,size:'small'},h(Button,{type:'text',className:'overview-metric','aria-label':metrics[k][0]+'趋势',onClick:()=>open(k)},h('span',null,metrics[k][0]),h('strong',null,format(k,summary[k]),metrics[k][1]!=='%'&&h('small',null,' '+metrics[k][1])),h('span',{className:'muted'},'查看趋势与明细 →')))))),h('section',{className:'panel'},h('h2',null,'推广产品汇总'),h('p',{className:'muted'},'点击指标查看该产品趋势；采购按张、预约与核销按次，比率按同批次计算。'),h(W.RecordList,{items:tableRows,states:['已启用','草稿','已停用','历史产品'],columns:[['id','产品编号'],['name','推广产品（内部）'],...keys.map(k=>[k+'Cell',metrics[k][0]]),['status','产品状态']],tableWidth:1700,onExport:exportSummary})),PROTOTYPE.role==='resource'&&h(Button,{onClick:()=>setLegacy(true)},'查看旧客户记录（只读）')),
      legacy&&h(Drawer,{visible:true,title:'旧客户记录（只读）',width:'min(900px, 100vw)',footer:null,onCancel:()=>setLegacy(false)},notice('原列表保留原始演示记录；缺少事件日期，不混入上方趋势。'),h(W.RecordList,{items:rows(pages,'customers'),states:[],columns:[['name','客户'],['phone','本方手机号'],['quantity','份数'],['status','原状态']],exportName:'旧客户记录'})),
      focus&&h(Drawer,{visible:true,width:'min(1120px, 100vw)',title:m[0]+' · '+productTitle,footer:null,onCancel:()=>{setFocus(null);setRecord(null);}},notice(m[2]),h('p',null,'开卡批次：'+f.from+' ～ '+f.to+'；趋势观察至 '+endDate+'；'+(PROTOTYPE.role==='resource'?PROTOTYPE.org:f.owner==='all'?'全部资源方':f.owner)),h('div',{className:'overview-filters'},W.field('趋势粒度',h(Select,{value:unit,options:[{label:'按天',value:'day'},{label:'按周',value:'week'},{label:'按月',value:'month'}],onChange:setUnit})),W.field('趋势口径',h(Select,{value:m[3]?'期末比率':trendMode,disabled:!!m[3],options:m[3]?['期末比率']:['累计','本期净变化'],onChange:setTrendMode}))),h('p',{className:'muted'},'周一至周日，自然月；首尾不足整周/月按范围截断。净变化可为负；无分母不画0%。'),h(Chart,{points,metric:focus.metric,onPoint:setPoint}),
        h('h2',null,'趋势数据'),h(W.RecordList,{items:points,states:['有数据','无分母'],columns:[['label','时间区间'],['display','数值（'+m[1]+'）'],...(m[3]?[['numerator','分子'],['denominator','分母']]:[])],onView:r=>setPoint(r.end),onExport:(selected,scope)=>PrototypeExcel.download('指标趋势-演示',[{name:'说明',rows:[['项目','内容'],['指标',m[0]],['单位',m[1]],['口径',m[2]],['产品',productTitle],['资源方',PROTOTYPE.role==='resource'?PROTOTYPE.org:f.owner],['销售方式',f.mode],['开卡批次',f.from+' 至 '+f.to],['趋势口径',m[3]?'期末比率':trendMode],['粒度',unit],['范围',scope]]},{name:'趋势',rows:[['起日','止日','数值','分子','分母'],...selected.map(r=>[r.start,r.end,r.value??'',r.numerator,r.denominator])]}])}),
        h('h2',null,'指标明细'),h('div',{className:'overview-filters'},W.field('明细观察时点',h(Select,{value:point,options:points.map(p=>({label:p.end,value:p.end})),onChange:setPoint})),m[3]&&W.field('比例明细范围',h(Select,{value:side,options:['分子','分母'],onChange:setSide}))),notice(metrics[detailKey][0]+' · '+detailRows.length+'条；人数明细已去重，展示一条代表性来源，详情可查全部关联卡。'),h(W.RecordList,{key:focus.metric+side+point,items:detailRows,states:[],tableWidth:1300,columns:[['id','编号'],['customer','客户'],['owner','资源方'],['product','推广产品'],['order','来源订单'],['time','时间'],['status','状态'],['completionSource','完成来源']],onView:setRecord,onExport:downloadDetails})),
      record&&h(Drawer,{visible:true,width:'min(800px, 100vw)',title:'指标记录详情',footer:null,onCancel:()=>setRecord(null)},h(Descriptions,{column:1,border:true,data:[['编号',record.id],['客户',record.customer],['资源方',record.owner],['推广产品',record.product],['来源订单',record.order],['来源卡',record.card],['时间',record.time],['状态',record.status],['完成来源',record.completionSource]].map(([label,value])=>({label,value}))}),h('h3',null,'当前范围关联卡'),h(W.RecordList,{items:focused.filter(c=>c.customerId===record.id||c.id===record.card).filter(c=>before(c.purchasedAt,point)).map(c=>({id:c.id,order:c.order,owner:c.owner,status:before(c.voidAt,point)?'已作废/停止':before(c.activatedAt,point)?'已激活':'待激活'})),columns:[['id','卡编号'],['order','来源订单'],['owner','资源方'],['status','状态']],states:[]})));
  }
  return {prepare,facts,filter,snapshot,buckets,series,details,metrics,View};
})();
