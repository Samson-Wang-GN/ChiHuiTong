(function(){
  'use strict';
  const C=window.CHT,{h,A}=C,base='/api/v1/';
  Object.assign(C.names,{legal_entity:'经营主体',province:'省 / 直辖市',city:'城市',district:'区 / 县',business_hours:'营业时间',frontdesk_phone:'前台预约手机号',cover_id:'小程序展示图片',business_license_ids:'营业执照',medical_license_ids:'医疗执业许可证',responsible_id:'负责业务员'});
  const keys=['name','legal_entity','province','city','district','address','business_hours','frontdesk_phone','business_contact','business_phone'];
  function ProfileView({profile={}}){return h('div',null,h(C.Facts,{data:profile,fields:keys}),h(C.Panel,{title:'门诊定位'},h(A.Alert,{type:profile.location?.status==='confirmed'?'success':'warning',content:profile.location?.status==='confirmed'?'已确认位置 · '+profile.location.address_snapshot:'尚未确认地图位置，不能上线接收新预约'}),profile.location?.status==='confirmed'&&h(C.Facts,{data:profile.location,fields:['longitude','latitude']})),h(C.Panel,{title:'小程序展示图片'},h(C.Attachments,{ids:profile.cover_id?[profile.cover_id]:[]})),h('div',{className:'attachment-grid'},h(C.Panel,{title:'营业执照（全部附件）'},h(C.Attachments,{ids:profile.business_license_ids||[]})),h(C.Panel,{title:'医疗执业许可证（全部附件）'},h(C.Attachments,{ids:profile.medical_license_ids||[]}))));}
  function profileForm(row,draft){C.open('clinicForm',{row,draft});}
  function ClinicProducts({clinicId}){return h(C.List,{path:base+'clinics/'+clinicId+'/products',rowKey:'product_id',columns:['internal_name','external_name','fee_cents','status'].map(k=>C.column(k)),actions:r=>C.button(r.status==='online'?'下线':'上线',()=>C.action((r.status==='online'?'下线':'上线')+'推广产品',base+'clinics/'+clinicId+'/products',null,{product_id:r.product_id,online:r.status!=='online'},[C.Reason],'上线/下线只影响新预约，已有权益和确认预约仍按履约规则处理。'),{disabled:r.status!=='online'&&!r.can_online})});}
  C.ClinicProducts=ClinicProducts;
  C.pages.clinics=()=>h(C.Panel,{title:C.role==='clinic'?'门诊资料':'门诊管理',extra:['platform','channel'].includes(C.role)&&h(A.Button,{type:'primary',onClick:()=>profileForm()},'新增门诊')},h(C.List,{path:base+'clinics',search:true,columns:[{title:'门诊名称',width:240,render:(_,r)=>r.profile.name||'待完善门诊'},{title:'经营地址',width:260,render:(_,r)=>[r.profile.province,r.profile.city,r.profile.district,r.profile.address].filter(Boolean).join('')},C.column('review_status'),C.column('service_status'),C.column('confirmation_hours')],actions:r=>[C.button('详情',()=>C.open('clinic',{id:r.id})),C.role==='platform'&&C.button('上线 / 下线',()=>C.form({title:'门诊上线 / 下线 · '+r.profile.name,fields:[{name:'status',label:'服务状态',type:'select',options:C.options({online:'上线',offline:'下线',paused:'暂停接入',exited:'结束合作'})},C.Reason],initial:{status:r.service_status},hint:'下线或暂停后不能新增预约，已有预约继续履约。逾期不自动下线；每次操作都记录原因。',onSubmit:v=>C.api(base+'clinics/'+r.id+'/service-status','POST',{...v,version:r.version})}))]}));
  C.dialogs.clinic=function({id,onClose,tab='info'}){const q=C.useChoices(base+'clinics/'+id),r=q.data;return h(C.Drawer,{title:(r?.profile.name||'门诊')+' · 管理模块',onClose},h(C.Error,{error:q.error,retry:q.reload}),h(A.Spin,{loading:q.loading,style:{width:'100%'}},r&&h('div',null,h(A.Alert,{type:'info',content:r.profile.name+' · 已发布资料与待审修改分开保存，审核退回不覆盖原资料。'}),h(A.Tabs,{defaultActiveTab:tab},h(A.Tabs.TabPane,{key:'info',title:'门诊资料'},h(A.Space,{wrap:true,className:'detail-actions'},h(A.Button,{type:'primary',onClick:()=>profileForm(r)},'维护门诊资料'),C.role==='platform'&&C.button('设置待确认时限',()=>C.action('修改待确认时限',base+'clinics/'+id+'/confirmation-hours',r.version,{hours:r.confirmation_hours},[{name:'hours',label:'待确认时限（小时）',type:'number',min:1,max:168},C.Reason])),C.role==='platform'&&C.button('变更所属渠道',()=>C.open('clinicChannel',{row:r}))),h(C.Facts,{data:r,fields:['review_status','service_status','confirmation_hours']}),h(ProfileView,{profile:r.profile})),h(A.Tabs.TabPane,{key:'review',title:'资料变更审核'},h(C.List,{path:base+'clinics/'+id+'/profile-changes',columns:[C.column('id','申请编号',280),C.column('status'),C.column('due_at'),C.column('reason')],actions:change=>C.button('对照详情',()=>C.open('profileChange',{row:change,clinic:r}))})),h(A.Tabs.TabPane,{key:'contracts',title:'合同与续签'},h(C.Contracts,{orgId:r.organization_id,canManage:C.role!=='clinic'})),h(A.Tabs.TabPane,{key:'products',title:'推广产品'},h(A.Alert,{type:'info',content:'默认显示本渠道可用的全部推广产品。未上线产品不接收新预约，不能在此修改产品规则或分配。'}),h(ClinicProducts,{clinicId:id})),C.role==='platform'&&h(A.Tabs.TabPane,{key:'members',title:'门诊账号'},h(C.Members,{orgId:r.organization_id,kind:'clinic'})),h(A.Tabs.TabPane,{key:'logs',title:'操作记录'},h(C.Logs,{type:'clinic',id}))))));};
  C.dialogs.profileChange=function({row,clinic,onClose}){return h(C.Drawer,{title:'门诊资料变更对照',onClose,width:960},h(C.Facts,{data:row,fields:['status','due_at','reason']}),h(A.Table,{rowKey:'key',pagination:false,columns:[{title:'字段',dataIndex:'label',width:150},{title:'原生效资料',dataIndex:'before',width:260},{title:'本次申请资料',dataIndex:'after',width:260},{title:'变化',width:90,render:(_,r)=>r.before!==r.after?h(A.Tag,{color:'orange'},'已修改'):'未变'}],data:keys.map(key=>({key,label:C.names[key],before:row.before[key]||'—',after:row.after[key]||'—'})),scroll:{x:760}}),h(A.Tabs,{defaultActiveTab:'after'},h(A.Tabs.TabPane,{key:'after',title:'申请资料及全部附件'},h(ProfileView,{profile:row.after})),h(A.Tabs.TabPane,{key:'before',title:'原资料及全部附件'},h(ProfileView,{profile:row.before}))),h(A.Space,{className:'detail-actions'},C.role==='platform'&&row.status==='pending'&&h(A.Button,{type:'primary',onClick:()=>C.action('审核门诊资料',base+'profile-changes/'+row.id+'/review',row.version,{approved:true},C.reviewFields,'请核对变更字段、定位、全部营业执照及医疗执业许可证。通过后整版发布；退回保留旧版。')},'审核资料'),row.status==='rejected'&&h(A.Button,{onClick:()=>profileForm(clinic,row.after)},'修改后重新提交')));};
  C.dialogs.clinicForm=function({row,draft,onClose}){
    const [channel,setChannel]=React.useState(row?.channel_id||(C.role==='channel'?C.actor.organization_id:''));
    const channels=C.useChoices(C.role==='platform'?base+'organizations?status=active&page_size=100':null);
    const owners=C.useChoices(channel && C.role!=='clinic' && C.actor.role==='admin'?base+'organizations/'+channel+'/members?status=active&page_size=100':null);
    const profile=draft||row?.profile||{};
    const fields=[...(!row?[{name:'channel_id',label:'所属渠道',render:()=>h(A.Select,{options:C.role==='channel'?[{value:C.actor.organization_id,label:C.actor.organization_name}]:(channels.data?.results||[]).filter(o=>o.kind==='channel').map(o=>({value:o.id,label:o.name})),disabled:C.role==='channel',onChange:setChannel})}]:[]),...keys.map(name=>({name,label:name==='name'?'门诊名称':C.names[name]})),{name:'responsible_id',label:'负责业务员',type:'select',disabled:C.role==='clinic'||C.actor.role!=='admin',options:owners.data?.results.map(m=>({value:m.id,label:m.name+' · '+C.text('role',m.role)}))||[{value:profile.responsible_id||C.actor.id,label:row?'当前负责业务员':'本人'}]},{name:'cover_ids',label:'小程序展示图片（一张）',type:'files',purpose:'cover',multiple:false,optional:true},{name:'business_license_ids',type:'files',purpose:'license'},{name:'medical_license_ids',type:'files',purpose:'license'},{name:'location',label:'地址定位与地图核对',render:form=>h(LocationField,{form,clinicId:row?.id})},...(!row?[{name:'admin_name',label:'门诊管理员姓名'},{name:'admin_phone',label:'门诊管理员手机号'}]:[])];
    return h(C.FormDialog,{title:row?'维护门诊资料':'新增门诊',onClose,fields,initial:{...profile,channel_id:channel,responsible_id:profile.responsible_id||C.actor.id,cover_ids:profile.cover_id?[profile.cover_id]:[],location:profile.location||{status:'unconfirmed'}},submitText:row?'提交变更审核':'保存门诊资料',hint:'已审核门诊的所有修改均须再次审核。业务联系人及电话必填，不在客户小程序公开。地址变化后须重新核对地图。',onSubmit:async v=>{const {channel_id,admin_name,admin_phone,cover_ids,...next}=v;next.cover_id=cover_ids?.[0]||null;const address=keys.filter(k=>['province','city','district','address'].includes(k)).map(k=>next[k]).join('');if(next.location?.address_snapshot!==address)next.location={status:'unconfirmed'};return row?C.api(base+'clinics/'+row.id+'/profile-changes','POST',{profile:next,version:row.version}):C.api(base+'clinics','POST',{channel_id,admin_name,admin_phone,profile:next});}});
  };
  function LocationField({form,clinicId,value,onChange}){
    const [error,setError]=React.useState(null),[busy,setBusy]=React.useState(false);
    function address(){const v=form.getFieldsValue();return ['province','city','district','address'].map(k=>v[k]||'').join('');}
    function show(candidate){
      const snapshot=address();
      C.open('locationMap',{clinicId,candidate,address:snapshot,onConfirm:position=>{
        if(address()!==snapshot)throw new Error('门诊地址已改变，请重新按地址定位后确认。');
        onChange({...position,status:'confirmed',confirmed:true,coordinate_system:'GCJ-02',address_snapshot:snapshot,source:'map_manual'});
      }});
    }
    async function locate(){
      setBusy(true);setError(null);
      try{const v=form.getFieldsValue();const data=await C.api(base+'clinics/geocode','POST',{...(clinicId?{clinic_id:clinicId}:{}),province:v.province,city:v.city,district:v.district,address:v.address});show(data.candidate);}
      catch(e){setError(e);}finally{setBusy(false);}
    }
    return h('div',null,h(C.Error,{error}),
      h(A.Alert,{type:'info',content:value?.status==='confirmed'?'已确认门诊位置；地址改变后须重新定位。':'先按地址定位，再在真实地图中核对门诊所在建筑并确认。'}),
      h(A.Space,null,h(A.Button,{loading:busy,onClick:locate},'按地址定位'),
      value?.status==='confirmed'&&h(A.Button,{onClick:()=>show(value)},'查看 / 调整地图位置')));
  }
  C.mapPoint=function(center,zoom,dx,dy){
    const size=256*Math.pow(2,zoom),sin=Math.sin(Number(center.latitude)*Math.PI/180);
    const x=(Number(center.longitude)+180)/360*size+dx;
    const y=(0.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size+dy;
    const lng=((x/size*360)%360+540)%360-180;
    const lat=Math.atan(Math.sinh(Math.PI*(1-2*y/size)))*180/Math.PI;
    return {latitude:Math.max(-85,Math.min(85,lat)).toFixed(6),longitude:lng.toFixed(6)};
  };
  C.dialogs.locationMap=function({clinicId,candidate,address,onConfirm,onClose}){
    const [center,setCenter]=React.useState({latitude:Number(candidate.latitude).toFixed(6),longitude:Number(candidate.longitude).toFixed(6)});
    const [zoom,setZoom]=React.useState(17),[url,setUrl]=React.useState(null),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(null),[retry,setRetry]=React.useState(0);
    React.useEffect(()=>{
      const controller=new AbortController();let imageUrl=null;
      setBusy(true);setError(null);setUrl(null);
      C.request(base+'clinics/map-preview',{method:'POST',body:{...(clinicId?{clinic_id:clinicId}:{}),...center,zoom},binary:true,signal:controller.signal})
        .then(blob=>{if(!controller.signal.aborted){imageUrl=URL.createObjectURL(blob);setUrl(imageUrl);}})
        .catch(e=>{if(!controller.signal.aborted)setError(e);})
        .finally(()=>{if(!controller.signal.aborted)setBusy(false);});
      return()=>{controller.abort();if(imageUrl)URL.revokeObjectURL(imageUrl);};
    },[center.latitude,center.longitude,zoom,retry]);
    function move(dx,dy){setCenter(C.mapPoint(center,zoom,dx,dy));}
    function confirm(){try{onConfirm(center);onClose();}catch(e){setError(e);}}
    return h(C.Drawer,{title:'在地图中确认门诊位置',onClose,width:720,footer:h(A.Space,null,h(A.Button,{onClick:onClose},'取消'),
      h(A.Button,{type:'primary',disabled:busy||!url||!!error,onClick:confirm},'确认中心标记为门诊位置'))},
      h(A.Alert,{type:'info',content:address+'。点击地图中的门诊位置，将其移到中心标记；确认前核对道路和建筑。'}),
      h(C.Error,{error,retry:()=>setRetry(v=>v+1)}),
      h(A.Space,{wrap:true,className:'detail-actions'},
        h(A.Button,{disabled:busy||zoom>=18,onClick:()=>setZoom(v=>v+1)},'放大'),
        h(A.Button,{disabled:busy||zoom<=3,onClick:()=>setZoom(v=>v-1)},'缩小'),
        [['向北',0,-100],['向南',0,100],['向西',-160,0],['向东',160,0]].map(([label,x,y])=>h(A.Button,{key:label,disabled:busy,onClick:()=>move(x,y)},label))),
      h(A.Spin,{loading:busy,style:{width:'100%'}},h('div',{className:'location-map',onClick:e=>{
        if(!url||busy)return;const r=e.currentTarget.getBoundingClientRect();move((e.clientX-r.left)/r.width*600-300,(e.clientY-r.top)/r.height*360-180);
      }},url?h('img',{src:url,alt:'腾讯地图真实底图，点击选择门诊位置',draggable:false}):h(A.Empty,{description:busy?'地图加载中':'地图未加载，不能确认位置'}),
      url&&h('span',{className:'location-map-pin','aria-label':'门诊位置标记'},'●'))),
      h('p',{className:'muted'},'位置确认仅保存到本次表单，提交后仍须平台审核。地图标识与底图版权信息原样保留。'));
  };
  C.dialogs.clinicChannel=function({row,onClose}){
    const channels=C.useChoices(base+'organizations?status=active&page_size=100');const [channel,setChannel]=React.useState('');const owners=C.useChoices(channel?base+'organizations/'+channel+'/members?status=active&page_size=100':null);
    return h(C.FormDialog,{title:'变更门诊所属渠道',onClose,fields:[{name:'channel_id',label:'新渠道',render:()=>h(A.Select,{options:(channels.data?.results||[]).filter(o=>o.kind==='channel').map(o=>({value:o.id,label:o.name})),onChange:setChannel})},{name:'responsible_id',label:'新负责业务员',type:'select',options:(owners.data?.results||[]).map(m=>({value:m.id,label:m.name}))},C.Reason],hint:'必须先从门诊列表下线。变更后核销的业绩归新渠道；历史已核销交易不追溯。',onSubmit:v=>C.api(base+'clinics/'+row.id+'/channel','POST',{...v,version:row.version})});
  };
})();
