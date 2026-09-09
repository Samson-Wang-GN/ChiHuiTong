/* REQ-032: local-only display/profile and location review; never calls a map API. */
window.PrototypeClinicInfo = (() => {
  const h=React.createElement,{useState}=React,{Alert,Button,Input,Upload,Image,Checkbox,Descriptions,Empty}=arco;
  const W=PrototypeWorkflows,clone=v=>JSON.parse(JSON.stringify(v));
  const defaults=c=>({businessContact:'',businessPhone:'',cover:null,location:null,timeout:24,hours:'09:00–18:00',...c});
  const validPoint=p=>p&&Number.isFinite(p.longitude)&&Number.isFinite(p.latitude)&&Math.abs(p.longitude)<=180&&Math.abs(p.latitude)<=90&&!(p.longitude===0&&p.latitude===0)&&p.coordinateSystem==='GCJ-02';
  const located=c=>validPoint(c.location)&&c.location.status==='已确认（演示）'&&c.location.address===c.address;
  const publicData=c=>({name:c.name,address:c.address,phone:c.phone,hours:c.hours,cover:c.cover,location:located(c)&&!c.needsReview&&!['草稿','待审核','审核不通过'].includes(c.qualification)?{longitude:c.location.longitude,latitude:c.location.latitude,coordinateSystem:c.location.coordinateSystem,demo:true}:null});
  const permitted=c=>PROTOTYPE.role==='channel'?c.channel===PROTOTYPE.org:PROTOTYPE.role==='clinic'?c.id===PROTOTYPE.pages.find(p=>p.id==='profile')?.rows[0]?.id:false;
  function validate(d){
    if(!/^1\d{10}$/.test(d.phone||''))return '请填写11位前台预约手机号。';
    if(!!String(d.businessContact||'').trim()!==!!String(d.businessPhone||'').trim())return '门诊业务联系人与联系人电话请一起填写，或一起留空待补充。';
    if(d.businessPhone&&!/^(1\d{10}|0\d{2,3}-?\d{7,8})$/.test(d.businessPhone))return '联系人电话应为大陆手机号或带区号固定电话。';
    if(d.cover&&!/^data:image\/(png|jpeg);base64,/.test(d.cover.url||''))return '展示图片无效，请重新上传PNG/JPG。';
    if(d.location&&(!validPoint(d.location)||d.location.address!==d.address))return '坐标无效或与当前地址不匹配，请重新解析核对。';
    return null;
  }
  function prepare(config){if(config.role==='platform'){const rows=config.pages.find(p=>p.id==='clinics').rows;if(!rows.some(c=>c.id==='MZ-CHANGE-DEMO'))rows.push({...clone(rows[0]),id:'MZ-CHANGE-DEMO',name:'资料变更审核门诊（独立演示）',status:'审核通过'});}const p=config.pages.find(p=>p.id==='profile');if(config.role==='clinic'&&p){p.custom='clinicProfile';p.description='维护本门诊基本资料、展示图片、联系方式与定位';p.actions=[];} }

  const profileKeys=['name','subject','address','phone','contact','businessContact','businessPhone','cover','location','hours','rep','files'];
  const approved=c=>!!c&&(c.qualification==='审核通过'||(!c.qualification&&c.status==='正常'));
  const waiting=c=>(c?.profileChanges||[]).some(r=>r.status==='待审核');
  const snapshot=c=>Object.fromEntries(profileKeys.map(k=>[k,clone(defaults(c)[k]??(k==='files'?[]:['cover','location'].includes(k)?null:''))]));
  const editorDraft=c=>({...c,...(!waiting(c)&&c?.profileChanges?.[0]?.status==='审核不通过'?c.profileChanges[0].after:{}),_baseVersion:c?.infoVersion||0});
  function commit(target,d){
    if(!permitted(target))return '只能维护本门诊或本渠道管理的门诊。';
    if(d.timeout!==undefined&&d.timeout!==(target.timeout??24))return '门诊待确认时限仅平台可修改。';
    if(waiting(target)||target.qualification==='待审核')return '已有资料待审核，请等待平台处理后再修改。';
    if(d._baseVersion!==undefined&&d._baseVersion!==(target.infoVersion||0))return '资料版本已变化，请重新打开后提交。';
    const error=validate(d);if(error)return error;
    const before=snapshot(target),after=snapshot({...target,...d});
    if(JSON.stringify(before)===JSON.stringify(after))return '资料没有变化，无需提交。';
    if(approved(target)){
      target.profileChanges=[{id:'BG-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),status:'待审核',before,after,baseVersion:target.infoVersion||0,submittedAt:new Date().toISOString(),submittedBy:PROTOTYPE.user,submittedRole:PROTOTYPE.role},...(target.profileChanges||[])];
    }else{
      Object.assign(target,after);target.infoVersion=(target.infoVersion||0)+1;
      target.infoHistory=[...(target.infoHistory||[]),{version:target.infoVersion,at:new Date().toISOString(),operator:PROTOTYPE.user,before}];
    }
    return null;
  }
  function reviewChange(c,id,pass,reason){
    if(PROTOTYPE.role!=='platform')return '只有平台可审核门诊资料变更。';
    const r=c.profileChanges?.find(r=>r.id===id);
    if(!r||r.status!=='待审核')return '申请已处理或不存在，请刷新。';
    if(!reason.trim())return '请填写审核意见。';
    if(pass&&(c.infoVersion||0)!==r.baseVersion)return '生效资料版本已变化，请退回后重新提交。';
    if(pass){
      const error=validate({...c,...r.after});if(error)return error;
      if((r.after.files||[]).some(f=>!W.fileOK(f)))return '申请附件缺失或不可读取，不能通过。';
      if((r.before.files||[]).length&& !['营业执照','医疗机构执业许可证','门诊照片'].every(k=>(r.after.files||[]).some(f=>f.kind===k)))return '请保留完整的资质与照片。';
      Object.assign(c,snapshot(r.after));c.infoVersion=(c.infoVersion||0)+1;
      c.infoHistory=[...(c.infoHistory||[]),{version:c.infoVersion,at:new Date().toISOString(),operator:PROTOTYPE.user,before:r.before,changeId:id}];
    }
    r.status=pass?'审核通过':'审核不通过';r.reason=reason.trim();r.reviewedAt=new Date().toISOString();r.reviewedBy=PROTOTYPE.user;
    return null;
  }
  function migrate(pages){
    if(PROTOTYPE.role==='platform'){
      const c=pages.find(p=>p.id==='clinics')?.rows.find(c=>c.id==='MZ-CHANGE-DEMO');
      if(c&&!c.changeDemoSeeded){
        c.changeDemoSeeded=true;const before=snapshot(c);
        c.profileChanges=[{id:'BG-DEMO-001',status:'待审核',before,after:{...before,phone:'13800000089',businessContact:'申请联系人（演示）',businessPhone:'13800000088'},baseVersion:c.infoVersion||0,submittedAt:'2026-09-09 10:00',submittedBy:'渠道业务员（演示）',submittedRole:'channel'}];
      }
    }
    return pages;
  }
  function Reviews({clinic:c,onSave}){
    const [selected,setSelected]=useState(null),[reason,setReason]=useState(''),[error,setError]=useState('');
    const r=c.profileChanges?.find(x=>x.id===selected);
    const act=pass=>{const next=clone(c),err=reviewChange(next,r.id,pass,reason);if(err){setError(err);return}onSave(next);setError('');setReason('')};
    const labels=['门诊名称','经营主体','经营地址','前台预约手机号','接待联系人','业务联系人','联系人电话','展示图片','地图定位','营业时间','负责业务员','资质附件'];
    const val=v=>v==null||v===''?'—':typeof v==='object'?(Array.isArray(v)?v.map(f=>f.name).join('、'):v.name||[v.address,v.longitude,v.latitude,v.status].filter(x=>x!==undefined).join(' · ')):v;
    return h('section',{className:'panel'},h('h3',null,'资料变更审核'),
      h(Alert,{type:'info',content:waiting(c)?'有资料变更待审核；当前生效资料保持不变。':'已审核资料的所有修改均需平台审核；退回仍使用原信息。'}),
      h(W.RecordList,{items:c.profileChanges||[],states:['待审核','审核通过','审核不通过'],columns:[['id','申请编号'],['submittedBy','提交人'],['submittedAt','提交时间'],['reason','审核意见'],['status','状态']],onView:x=>{setSelected(x.id);setReason('');setError('')}}),
      r&&h(arco.Drawer,{visible:true,title:'门诊资料变更 · '+r.id,width:960,footer:null,onCancel:()=>setSelected(null)},
        h(Alert,{type:'info',content:r.status+' · 基准版本 '+r.baseVersion+' · 审核前及退回后继续使用当前生效资料'}),
        h(arco.Table,{pagination:false,rowKey:'key',scroll:{x:700},data:profileKeys.map((key,i)=>({key,label:labels[i],before:val(r.before[key]),after:val(r.after[key]),changed:JSON.stringify(r.before[key])!==JSON.stringify(r.after[key])})),columns:[{title:'字段',dataIndex:'label',width:140},{title:'提交时生效资料',dataIndex:'before'},{title:'申请的新资料',dataIndex:'after'},{title:'变化',width:80,render:(_,x)=>x.changed?'已修改':'未修改'}]}),
        h('h3',null,'原展示图片'),h(Preview,{clinic:r.before}),h('h3',null,'申请展示图片'),h(Preview,{clinic:r.after}),
        h('h3',null,'原全部资质附件'),h(W.Files,{files:r.before.files}),h('h3',null,'申请全部资质附件'),h(W.Files,{files:r.after.files}),
        r.reason&&h(Alert,{type:r.status==='审核不通过'?'error':'info',content:'审核意见：'+r.reason}),
        error&&h(Alert,{type:'error',content:error}),
        PROTOTYPE.role==='platform'&&r.status==='待审核'&&h(React.Fragment,null,W.field('变更审核意见',h(Input.TextArea,{value:reason,onChange:setReason})),h('div',{className:'flow-actions'},h(Button,{type:'primary',onClick:()=>act(true)},'通过资料变更'),h(Button,{status:'danger',onClick:()=>act(false)},'退回资料变更')))
      ));
  }
  function Preview({clinic}){const c=publicData(clinic);return h('section',{className:'panel'},h('h3',null,'客户小程序展示预览'),h('p',{className:'muted'},'仅预览当前填写内容，未同步小程序；不展示业务联系人。'),c.cover?h('div',{className:'clinic-display-cover'},h(Image,{src:c.cover.url,width:'100%',height:'100%',fit:'cover',alt:'门诊展示图片'})):h(Empty,{description:'尚未上传展示图片'}),h('h3',null,c.name||'门诊名称'),h('p',null,c.address||'请填写地址'),h('p',null,'预约电话：'+(c.phone||'待补充')),h('p',null,c.location?'位置已核对（演示），未启用真实距离排序':'位置待核对，暂不提供精确距离或地图点位'));}
  function Summary({clinic}){return h(React.Fragment,null,h(Descriptions,{column:2,border:true,data:[['前台预约手机号',clinic.phone||'待补充'],['门诊业务联系人',clinic.businessContact||'待补充'],['联系人电话',clinic.businessPhone||'待补充'],['位置状态',located(clinic)?'已确认（演示）':'待解析/待核对'],['经度',clinic.location?.longitude??'—'],['纬度',clinic.location?.latitude??'—'],['坐标系',clinic.location?.coordinateSystem||'GCJ-02（待定位）']].map(([label,value])=>({label,value}))}),h(Preview,{clinic}));}
  function Fields({draft:d,onChange:set,onBusy}){
    const [error,setError]=useState(''),[busy,setBusy]=useState(false);
    const put=(k,v)=>set({...d,[k]:v});
    const upload=file=>{
      if(!['image/png','image/jpeg'].includes(file.type)||! /\.(png|jpe?g)$/i.test(file.name)||file.size>512*1024){setError('仅支持可解码的PNG/JPG，单张不超过512KB；原图片未更换。');return false;}
      setBusy(true);onBusy?.(true);const reader=new FileReader();
      const done=()=>{setBusy(false);onBusy?.(false)};
      reader.onload=async()=>{try{const img=new window.Image();img.src=reader.result;await img.decode();set(prev=>({...prev,cover:{name:file.name,type:file.type,url:reader.result}}));setError('')}catch{setError('图片无法解码，原图片未更换。')}finally{done()}};
      reader.onerror=()=>{setError('图片读取失败，原图片未更换。');done()};reader.readAsDataURL(file);return false;
    };
    return h(React.Fragment,null,error&&h(Alert,{type:'error',content:error}),h('h3',null,'小程序展示图片'),h('p',{className:'muted'},'单张PNG/JPG，推荐16:9，原型上限512KB；请勿上传真实患者资料。'),h('div',{className:'flow-actions'},h(Upload,{accept:'.png,.jpg,.jpeg',beforeUpload:upload,autoUpload:false,showUploadList:false,disabled:busy},h(Button,null,d.cover?'替换展示图片':'上传展示图片')),d.cover&&h(Button,{status:'danger',disabled:busy,onClick:()=>put('cover',null)},'移除展示图片')),h('div',{className:'flow-form-grid'},W.field('门诊业务联系人',h(Input,{value:d.businessContact||'',onChange:v=>put('businessContact',v)})),W.field('联系人电话',h(Input,{value:d.businessPhone||'',onChange:v=>put('businessPhone',v),placeholder:'手机号或带区号固定电话'}))),h('p',{className:'muted'},'预约待确认时限：'+(d.timeout??24)+'小时 · 仅平台可修改'),h(Preview,{clinic:d}));
  }

  const demoPoints={'演示市春和路12号':[116.32,39.98],'演示市景明路28号':[116.33,39.99],'演示市滨河路36号':[116.34,39.97]};
  function LocationFields({draft:d,onChange:set}){
    const [error,setError]=useState(''),[agreed,setAgreed]=useState(false),[zoom,setZoom]=useState(1);
    const base=demoPoints[d.address],p=d.location,shown=base&&validPoint(p)&&p.address===d.address;
    const resetPoint=point=>{
      setAgreed(false);setError('');
      set(prev=>({...prev,location:{...point,address:prev.address,coordinateSystem:'GCJ-02',status:'待核对',source:'本地虚构示意地图',demo:true}}));
    };
    const parse=()=>{
      setAgreed(false);setZoom(1);
      if(!base){set(prev=>({...prev,location:null}));setError('真实地图尚未接入：此地址没有演示候选。请核对地址后重试，不能用默认坐标替代。');return;}
      resetPoint({longitude:base[0],latitude:base[1]});
    };
    const project=(lng,lat)=>({x:320+(lng-base[0])*100000*zoom,y:160-(lat-base[1])*100000*zoom});
    const fromXY=(x,y)=>resetPoint({longitude:Number((base[0]+(x-320)/100000/zoom).toFixed(6)),latitude:Number((base[1]-(y-160)/100000/zoom).toFixed(6))});
    const pointer=e=>{const r=e.currentTarget.getBoundingClientRect();fromXY(Math.max(0,Math.min(640,(e.clientX-r.left)*640/r.width)),Math.max(0,Math.min(320,(e.clientY-r.top)*320/r.height)))};
    const marker=shown?project(p.longitude,p.latitude):null;
    const confirm=()=>{
      if(!shown||!agreed){setError('请在地图上核对当前地址和门诊入口，并勾选确认。');return;}
      set(prev=>({...prev,location:{...prev.location,status:'已确认（演示）',confirmedAt:new Date().toISOString(),confirmedBy:PROTOTYPE.user}}));setError('');
    };
    const street=d.address.includes('景明')?'景明路':d.address.includes('滨河')?'滨河路':'春和路';
    return h('section',{className:'clinic-location-section'},
      h('h3',null,'门诊位置核对'),
      h(Alert,{type:'warning',content:'虚构示意地图，仅用于原型选点演示；道路、地标和坐标均不是实际地理位置。真实地图服务尚未接入。'}),
      h('div',{className:'flow-actions'},h(Button,{onClick:parse,disabled:!d.address.trim()},'按地址在地图中定位（演示）')),
      error&&h(Alert,{type:'error',content:error}),
      !shown?h(Empty,{description:'填写经营地址后定位，在地图上核对门诊入口'}):h(React.Fragment,null,
        h('p',null,'候选地址：'+p.address+' · '+p.status),
        h('div',{className:'clinic-map-toolbar'},h('span',null,'点击地图选点或拖动标记；方向键微调'),h(Button,{size:'small',disabled:zoom>=3,onClick:()=>setZoom(v=>v+0.5)},'放大地图'),h(Button,{size:'small',disabled:zoom<=1,onClick:()=>setZoom(v=>v-0.5)},'缩小地图'),h(Button,{size:'small',onClick:()=>setZoom(1)},'显示全图')),
        h('div',{className:'clinic-map-frame'},
          h('svg',{viewBox:'0 0 640 320',preserveAspectRatio:'none',role:'group','aria-label':'门诊入口示意地图',tabIndex:0,
            onPointerDown:e=>{if(e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);pointer(e)},
            onPointerMove:e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))pointer(e)},
            onPointerUp:e=>{if(e.currentTarget.hasPointerCapture(e.pointerId)){pointer(e);e.currentTarget.releasePointerCapture(e.pointerId)}},
            onKeyDown:e=>{const move={ArrowLeft:[-4,0],ArrowRight:[4,0],ArrowUp:[0,-4],ArrowDown:[0,4]}[e.key];if(move){e.preventDefault();fromXY(Math.max(0,Math.min(640,marker.x+move[0])),Math.max(0,Math.min(320,marker.y+move[1])))}}},
            h('rect',{width:640,height:320,fill:'#f2f3f5'}),
            h('g',{transform:'translate(320 160) scale('+zoom+') translate(-320 -160)'},
              ...[[25,25,125,75,'社区公园'],[215,25,120,75,'示例商业楼'],[425,25,175,75,'公交站'],[25,225,125,70,'停车场'],[215,225,120,70,'门诊楼'],[425,225,175,70,'邻里中心']].map(([x,y,w,ht,label],i)=>h('g',{key:label},h('rect',{x,y,width:w,height:ht,rx:4,fill:i===0?'#d9f2df':'#e5e6eb',stroke:'#c9cdd4'}),h('text',{x:x+w/2,y:y+ht/2,textAnchor:'middle',fill:'#4e5969',fontSize:14},label))),
              h('path',{d:'M0 160 H640 M180 0 V320 M380 0 V320',stroke:'white',strokeWidth:32,fill:'none'}),
              h('path',{d:'M0 160 H640',stroke:'#f7ba1e',strokeWidth:2,strokeDasharray:'8 8',fill:'none'}),
              h('text',{x:65,y:140,fill:'#4e5969',fontSize:14},street+'（示意）'),
              h('text',{x:395,y:285,fill:'#4e5969',fontSize:14},'步行入口'),
              h('circle',{cx:280,cy:211,r:5,fill:'#165dff'})),
            h('g',{'data-testid':'clinic-map-marker',transform:'translate('+marker.x+' '+marker.y+')',style:{cursor:'grab'}},
              h('path',{d:'M0 0 C-22 -22 -16 -42 0 -42 C16 -42 22 -22 0 0Z',fill:'#165dff',stroke:'white',strokeWidth:2}),
              h('circle',{cy:-27,r:5,fill:'white'}),
              h('rect',{x:-58,y:8,width:116,height:24,rx:4,fill:'white',stroke:'#165dff'}),
              h('text',{y:25,textAnchor:'middle',fontSize:13,fill:'#165dff'},'当前选择的入口')),
            h('text',{x:12,y:22,fill:'#86909c',fontSize:12,pointerEvents:'none'},'示意地图 · 非真实地理数据'),
            h('text',{x:610,y:25,fill:'#4e5969',fontSize:13},'北↑'))),
        h('div',{className:'flow-actions'},h(Button,{size:'small',onClick:()=>resetPoint({longitude:base[0]-0.0004,latitude:base[1]-0.00051})},'选择门诊楼入口（示意）'),h(Button,{size:'small',onClick:parse},'恢复地址候选点')),
        h('p',{className:'muted','data-testid':'clinic-map-coordinates'},'辅助坐标（自动回填）：经度 '+p.longitude.toFixed(6)+'，纬度 '+p.latitude.toFixed(6)+' · GCJ-02'),
        h(Checkbox,{checked:agreed,onChange:setAgreed},'已在地图上核对门诊入口（演示）'),
        h('div',{className:'flow-actions'},h(Button,{type:'primary',onClick:confirm},'确认门诊位置（演示）')),
        h('p',{'aria-live':'polite'},p.status==='已确认（演示）'?'位置已确认，请保存门诊资料；移动点位后需要重新确认。':'当前点位尚未确认，不能用于位置推荐。'))
    );
  }

  function Profile({pages,save,Editor}){
    const [edit,setEdit]=useState(false),[error,setError]=useState('');const p=pages.find(p=>p.id==='profile'),c=p?.rows[0];
    if(!c)return h(Empty,{description:'尚未开通门诊资料'});
    return h(React.Fragment,null,h(W.RecordList,{items:p.rows,states:['正常','待审核','审核通过','已暂停'],columns:p.columns,onView:()=>{if(!waiting(c)&&c.qualification!=='待审核')setEdit(true)}}),h('div',{className:'flow-actions'},h(Button,{type:'primary',disabled:waiting(c)||c.qualification==='待审核',onClick:()=>setEdit(true)},'维护门诊资料')),h(Summary,{clinic:c}),h(PrototypeManagement.Logs,{record:c}),h(Reviews,{clinic:c}),error&&h(Alert,{type:'error',content:error}),edit&&h(Editor,{clinic:c,self:true,onCancel:()=>setEdit(false),onSave:d=>{const next=clone(pages),target=next.find(p=>p.id==='profile').rows.find(r=>r.id===c.id);const err=commit(target,d);if(err){setError(err);return}W.audit(next,'维护本门诊资料',c.id);save(next);setEdit(false);setError('')}}));
  }
  return {prepare,defaults,validate,validPoint,located,publicData,permitted,commit,Fields,LocationFields,Summary,Profile,approved,waiting,editorDraft,reviewChange,Reviews,migrate,snapshot};
})();
