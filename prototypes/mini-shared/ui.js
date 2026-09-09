/* 两端共享UI助手，不包含任何角色业务记录。 */
window.Mini=(()=>{
  const h=React.createElement,{useState,useEffect}=React;
  const {Button,Tag,Tabs,Modal}=arco;
  const today='2026-09-07',clone=v=>JSON.parse(JSON.stringify(v));
  function publicNames(data){const mapping={'舒适洁牙权益':'舒适洁牙服务','种植牙抵用权益':'种植牙专享抵用券','正畸抵用权益':'正畸专享抵用券'};const walk=o=>{if(!o||typeof o!=='object')return;for(const k of Object.keys(o)){if(typeof o[k]==='string'&&mapping[o[k]])o[k]=mapping[o[k]];else if(typeof o[k]==='object')walk(o[k])}};walk(data);return data}
  function useStore(key,seed,migrate=x=>x){const [data,set]=useState(()=>{try{const raw=localStorage.getItem(key);if(raw&&!localStorage.getItem(key+'-before-0.29'))localStorage.setItem(key+'-before-0.29',raw);if(raw&&!localStorage.getItem(key+'-before-0.23'))localStorage.setItem(key+'-before-0.23',raw);if(raw&&!localStorage.getItem(key+'-before-0.19'))localStorage.setItem(key+'-before-0.19',raw);return migrate(publicNames(JSON.parse(raw)||clone(seed)))}catch{return migrate(publicNames(clone(seed)))}});return [data,next=>{set(next);try{localStorage.setItem(key,JSON.stringify(next))}catch{arco.Message.warning('演示修改未能保存，刷新将恢复样例')}}];}
  function useRoute(){const [route,set]=useState(location.hash.slice(1)||'home');useEffect(()=>{const cb=()=>{set(location.hash.slice(1)||'home');window.scrollTo(0,0)};addEventListener('hashchange',cb);return()=>removeEventListener('hashchange',cb)},[]);return [route,id=>{location.hash=id;set(id);window.scrollTo(0,0)}];}
  const btn=(text,onClick,props={})=>h(Button,{long:true,type:'primary',onClick,...props},text);
  const note=(text,type='info')=>h('div',{className:'notice '+(type==='info'?'':type),role:type==='error'?'alert':undefined},text);
  const tag=s=>h(Tag,{color:/冻结|过期|逾期|失效/.test(s)?'red':/待|占用/.test(s)?'orange':/成功|可使用|完成|结清|正常/.test(s)?'green':'arcoblue'},s);
  const field=(label,input)=>h('div',{className:'field'},h('span',null,label),React.cloneElement(input,{'aria-label':label}));
  const row=(label,value)=>h('div',{className:'row'},h('span',null,label),h('span',null,value));
  const card=(title,subtitle,content,actions)=>h('section',{className:'card'},h('div',{className:'card-top'},h('h3',null,title),subtitle&&tag(subtitle)),content,h('div',{className:'stack'},actions));
  const heading=(title,sub)=>h('div',{className:'intro'},h('h1',null,title),sub&&h('div',{className:'muted'},sub));
  const datePlus=days=>{const d=new Date(today+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10)};
  const validDate=(date,time,expiry)=>!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d{2}:\d{2}$/.test(time)?'请填写完整日期和时间':date<today?'不能选择评审日期之前的时间':date>expiry?'预约或改期不能超过权益到期日 '+expiry:null;
  function StateList({states,items,render,statusKey='status'}){const [selected,set]=useState('全部');return h(Tabs,{activeTab:selected,onChange:set,overflow:'scroll',headerPadding:false,destroyOnHide:true,animation:false},...['全部',...states].map(s=>{const rows=items.filter(r=>s==='全部'||r[statusKey]===s);return h(Tabs.TabPane,{key:s,title:s+'（'+rows.length+'）'},selected===s?(rows.length?rows.map(render):h('div',{className:'empty'},'暂无'+(s==='全部'?'相关':s)+'记录')):null)}));}
  function Shell({title,route,go,nav,children,back='home'}){return h('div',{className:'phone'},h('header',{className:'mobile-head'},h(Button,{type:'text',size:'small',onClick:()=>go(back),'aria-label':'返回'},'‹'),h('strong',null,title),h('span',{className:'capsule','aria-hidden':true},'•••')),h('main',{className:'mobile-main'},children,h('div',{className:'review-note'},'交互原型 · 虚构数据 · 评审日期 '+today+'。微信授权、定位、扫码与短信未接入。')),h('nav',{className:'tabbar','aria-label':'底部导航'},...nav.map(([id,label,icon])=>h('button',{key:id,className:route.split('/')[0]===id?'active':'',onClick:()=>go(id)},h('span',{className:'nav-mark','aria-hidden':true},icon),label))));}
  const confirm=(title,content,onOk)=>Modal.confirm({title,content:h('div',{className:'modal-content'},content),okText:'确认',cancelText:'返回',onOk});
  const log=(data,text)=>{data.messages.unshift({id:'MSG-'+Date.now(),name:text,status:'未读'});};
  return {h,clone,useStore,useRoute,btn,note,tag,field,row,card,heading,datePlus,validDate,StateList,Shell,confirm,log,today};
})();
