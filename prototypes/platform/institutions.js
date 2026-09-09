/* Platform-only institution workspace. Contract/term records remain separate. */
window.PrototypeInstitutions = (() => {
  const h=React.createElement,{useState,useEffect}=React,{Button,Tabs,Alert,Descriptions,Select,Drawer,Empty}=arco;
  const W=PrototypeWorkflows,rows=(p,id)=>p.find(x=>x.id===id)?.rows||[];
  const type=i=>i.type==='门诊渠道公司'?'平台—渠道公司':['保险公司','银行','经纪代理公司'].includes(i.type)?'平台—资源方':null;
  function owner(pages,c){
    if(!c)return null;
    if(c.institutionId)return rows(pages,'institutions').find(i=>i.id===c.institutionId&&type(i)===c.type)||null;
    const found=rows(pages,'institutions').filter(i=>i.name===c.party&&type(i)===c.type);
    return found.length===1?found[0]:null;
  }
  const contracts=(pages,id)=>rows(pages,'contracts').filter(c=>owner(pages,c)?.id===id);
  function migrate(pages){for(const c of rows(pages,'contracts')){if(!c.institutionId){const i=owner(pages,c);if(i)c.institutionId=i.id;}}return pages;}
  function prepare(config){
    const page=id=>config.pages.find(p=>p.id===id);
    page('institutions').custom='institutions';page('institutions').description='以机构为中心管理合作合同和推广产品配置';
    page('contracts').hidden=true;page('contractSchemes').hidden=true;
    page('contractSchemes').title='推广产品配置';page('contractSchemes').create.label='添加推广产品';
    for(const a of page('contracts').actions)if(a.link==='contractSchemes')a.label='推广产品配置';
    migrate(config.pages);config.version='0.24.1';
  }
  function target(pages){
    const [path,query='']=location.hash.slice(1).split('?'),q=new URLSearchParams(query);
    const section=q.get('section')||'info',id=q.get('institution'),contract=q.get('contract');
    if(['contracts','contractSchemes'].includes(path)){
      const c=contract&&rows(pages,'contracts').find(c=>c.id===contract);
      const candidates=q.get('party')?rows(pages,'institutions').filter(i=>i.name===q.get('party')):[];
      const i=c?owner(pages,c):candidates.length===1?candidates[0]:null;
      if(contract&&!c||i&&q.get('party')&&q.get('party')!==i.name)return {message:'机构或合同范围不匹配，请重新选择；未加载其他机构配置。'};
      if(i)return {id:i.id,section:path==='contractSchemes'?'products':'contracts',contract:c?.id};
      return {message:contract||q.get('party')?'未找到唯一匹配的机构与合同，请核对原链接。':'合同与推广产品配置已整合，请先选择机构。'};
    }
    if(!id)return {message:contract?'缺少机构范围，请先选择机构。':null};
    const i=rows(pages,'institutions').find(i=>i.id===id);
    if(!i||!['info','contracts','products'].includes(section)||contract&&!contracts(pages,id).some(c=>c.id===contract))return {message:'机构或合同范围不匹配，请重新选择；未加载其他机构配置。'};
    return {id,section,contract};
  }
  const url=(id,section='info',contract)=>'institutions?institution='+encodeURIComponent(id)+'&section='+section+(contract?'&contract='+encodeURIComponent(contract):'');
  function guard(pages,operation,values){
    const {page,row,action,institutionId}=operation;
    if(!['contracts','contractSchemes'].includes(page.id))return null;
    const i=rows(pages,'institutions').find(i=>i.id===institutionId);
    if(!i)return '缺少有效机构范围，请从机构管理重新进入。';
    if(values.institutionId!==undefined&&values.institutionId!==i.id)return '机构归属不能修改。';
    if(page.id==='contracts'){
      if(action.create&&(!type(i)||values.party!==i.name||values.type!==type(i)))return '请使用当前机构的合同主体和类型。';
      if(values.party!==undefined&&values.party!==i.name||values.type!==undefined&&values.type!==type(i)||row&&owner(pages,rows(pages,'contracts').find(c=>c.id===row.id))?.id!==i.id)return '合同主体或类型与当前机构不一致，不能提交。';
      if(!action.create&&(!row||action.when&&!action.when.includes(rows(pages,'contracts').find(c=>c.id===row.id)?.status)))return '合同状态已变化，请重新打开。';
    }else{
      const c=rows(pages,'contracts').find(c=>c.id===(values.contract||row?.contract));
      if(owner(pages,c)?.id!==i.id)return '只能配置当前机构的合作合同，不能跨机构提交。';
      if(row){const live=rows(pages,'contractSchemes').find(r=>r.id===row.id);if(!live||live.contract!==c.id||values.scheme&&values.scheme!==live.scheme||action.when&&!action.when.includes(live.status))return '配置已变化或试图替换原合同/产品，请重新打开。';}
    }
    return null;
  }
  function View({pages,onBegin,onDetail,termView,taskContext,onClose,viewState='正常',onRetry}){
    const route=taskContext||target(pages),[local,setLocal]=useState(null),[selectedContract,setSelectedContract]=useState(null);
    useEffect(()=>{setLocal(null);setSelectedContract(null)},[route.id,route.section,route.contract]);
    const section=local||route.section||'info',id=route.id,i=rows(pages,'institutions').find(i=>i.id===id);
    const ip=pages.find(p=>p.id==='institutions'),cp=pages.find(p=>p.id==='contracts'),tp=pages.find(p=>p.id==='contractSchemes');
    const cs=i?contracts(pages,i.id):[],filterContract=selectedContract??route.contract??'all';
    const terms=rows(pages,'contractSchemes').filter(r=>cs.some(c=>c.id===r.contract)&&(filterContract==='all'||r.contract===filterContract)).map(r=>termView(r,pages));
    const open=(institution,tab='info',contract)=>{location.hash=url(institution.id,tab,contract)};
    const begin=(action,row,page)=>onBegin(action,row,page,{institutionId:i.id,contractId:filterContract!=='all'?filterContract:cs.length===1?cs[0].id:null});
    const controls=(page,r)=>h('div',{className:'detail-actions',style:{marginTop:0}},h(Button,{type:'text',onClick:()=>onDetail(page,r)},'详情'),...(page.actions||[]).filter(a=>!a.when||a.when.includes(r.status)).map(a=>h(Button,{key:a.label,type:'text',status:a.danger?'danger':undefined,onClick:()=>a.link==='contractSchemes'?(setLocal('products'),setSelectedContract(r.id)):begin(a,r,page)},a.label)));
    const info=i&&h('section',{className:'panel'},h(Descriptions,{column:1,border:true,data:[['机构编号',i.id],['机构名称',i.name],['机构类型',i.type],['机构状态',i.status],['联系人',i.contact],['联系手机号',i.phone||'尚未填写'],['初始管理员',i.adminAccount?i.adminAccount.name+' · '+i.adminAccount.phone+' · 管理员（平台锁定）':'历史账号待平台核对']].map(([label,value])=>({label,value}))}),h('div',{className:'detail-actions'},...(ip.actions||[]).filter(a=>!a.link&&(!a.when||a.when.includes(i.status))).map(a=>h(Button,{key:a.label,type:'primary',onClick:()=>begin(a,i,ip)},a.label)),type(i)==='平台—资源方'&&h(Button,{onClick:()=>{location.hash='sources?owner='+encodeURIComponent(i.name)}},'来源展示名')));
    const contractSection=i&&h('section',{className:'panel'},h(Alert,{type:'info',content:type(i)==='平台—资源方'?'本机构仅一份平台主合同，可配置多个推广产品；历史条款和业务快照保留。':'本机构同一时点仅一个生效平台合同。门诊三方合同仍在门诊管理办理。'}),h('div',{className:'detail-actions'},h(Button,{type:'primary',disabled:type(i)==='平台—资源方'&&cs.length>0,onClick:()=>begin({...cp.create,defaults:{...cp.create.defaults,party:i.name,type:type(i)}},null,cp)},'登记合同')),h(W.RecordList,{key:i.id,items:taskContext?.contract?cs.filter(c=>c.id===taskContext.contract):cs,states:['待审核','已审核待生效','已生效','即将到期','已到期','审核不通过','已终止'],columns:[['id','合同编号'],...cp.columns],actionWidth:220,actions:r=>controls(cp,r),tableWidth:1100}));
    const productsSection=i&&h('section',{className:'panel'},h(Alert,{type:'info',content:'只管理本机构合同授权及分配，不修改全局产品定义。停用仅影响新业务，存量预约继续履约，费用在核销时锁定；历史核销保留费用快照。'}),h('div',{className:'toolbar',style:{marginTop:16}},W.field('本机构合作合同',h(Select,{value:filterContract,style:{width:340,maxWidth:'100%'},options:[{label:'全部本机构合同',value:'all'},...cs.map(c=>({value:c.id,label:c.id+' · '+c.status}))],onChange:setSelectedContract})),h(Button,{type:'primary',disabled:!cs.length,onClick:()=>begin(tp.create,null,tp)},'添加推广产品')),!cs.length&&h(Alert,{type:'warning',content:'尚无合作合同，请先在合作合同区登记。'}),filterContract!=='all'&&h('p',null,'当前范围：'+filterContract),h(W.RecordList,{key:i.id+'-'+filterContract,items:terms,states:['已启用','已停用'],columns:tp.columns,actionWidth:220,actions:r=>controls(tp,r),tableWidth:1400}));
    const detail=i&&h('div',{className:'clinic-context'},h(Alert,{type:'info',content:i.name+' · '+i.type+' · '+i.id}),h(Tabs,{activeTab:section,destroyOnHide:true,animation:false,type:'line',overflow:'scroll',onChange:setLocal},h(Tabs.TabPane,{key:'info',title:'机构资料'},info),h(Tabs.TabPane,{key:'contracts',title:'合作合同'},contractSection),h(Tabs.TabPane,{key:'products',title:'推广产品配置'},productsSection)));

    const list=h('div',null,h('div',{className:'page-heading'},h('div',null,h('h1',null,'机构管理'),h('p',null,'机构资料、合作合同与推广产品配置，一处办理'))),h('div',{className:'flow-actions'},h(Button,{type:'primary',onClick:()=>onBegin(ip.create,null,ip)},'新增机构')),route.message&&h(Alert,{type:'warning',content:route.message}),rows(pages,'contracts').some(c=>!owner(pages,c))&&h(Alert,{type:'warning',content:'有历史合同尚未匹配唯一机构，原记录已保留；请核对机构资料后处理，不自动分配归属。'}),viewState==='加载失败'?h(React.Fragment,null,h(Alert,{type:'error',content:'机构加载失败，请重试'}),h(Button,{onClick:onRetry},'重新加载')):viewState==='加载中'?h(arco.Spin,{tip:'正在加载机构'}):h(W.RecordList,{items:viewState==='空状态'?[]:ip.rows.map(i=>({...i,contractCount:contracts(pages,i.id).length})),states:['正常','待审核','审核通过','审核不通过'],columns:[...ip.columns,['contractCount','合同数量']],tableWidth:1000,onView:r=>open(r)}));
    const drawer=(i||taskContext)&&h(Drawer,{visible:true,escToExit:false,width:1000,title:i?i.name+' · 机构管理':'机构管理',footer:null,onCancel:()=>{if(taskContext)onClose?.();else location.hash='institutions'}},detail||h(Empty,{description:'未找到当前机构，请重新打开任务'}));
    return h('div',{className:'workflow institution-workspace'},!taskContext&&list,drawer);
  }
  return {prepare,migrate,owner,contracts,target,url,guard,View,type};
})();
