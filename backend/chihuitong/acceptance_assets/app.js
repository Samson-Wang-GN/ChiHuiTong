(function(){
  'use strict';
  const C=window.CHT,{h,A}=C;
  const roleNames={platform:'平台管理后台',resource:'客户资源方后台',channel:'门诊渠道后台',clinic:'门诊后台'};
  const phones={platform:'13800000001',resource:'13800000002',channel:'13800000003',clinic:'13800000004'};
  function DialogHost(){
    const [stack,setStack]=React.useState([]);
    React.useEffect(()=>{const open=e=>setStack(v=>[...v,e.detail]);const clear=()=>setStack([]);C.events.addEventListener('open',open);C.events.addEventListener('expired',clear);C.events.addEventListener('logout',clear);return()=>{C.events.removeEventListener('open',open);C.events.removeEventListener('expired',clear);C.events.removeEventListener('logout',clear);};},[]);
    return stack.map(({type,props,key})=>{const Component=C.dialogs[type];return Component?h(Component,{...props,key,onClose:()=>setStack(v=>v.filter(d=>d.key!==key))}):null;});
  }
  function Login({onLogin,notice}){
    const [phone,setPhone]=React.useState(phones[C.role]||''),[code,setCode]=React.useState(''),[error,setError]=React.useState(null),[busy,setBusy]=React.useState(false),[sms,setSms]=React.useState(null),[wait,setWait]=React.useState(0),[members,setMembers]=React.useState([]),[chosen,setChosen]=React.useState(null),[reminder,setReminder]=React.useState(()=>{try{return localStorage.getItem('chihuitong.clinic.reminder')!=='off';}catch{return true;}});
    React.useEffect(()=>{if(!wait)return;const id=setTimeout(()=>setWait(n=>n-1),1000);return()=>clearTimeout(id);},[wait]);
    async function act(fn){setBusy(true);setError(null);try{await fn();}catch(e){setError(e);C.reminder?.close();}finally{setBusy(false);}}
    function finish(member){C.actor=member;setCode('');setSms(null);onLogin(member);}
    function login(){if(C.role==='clinic'&&reminder&&C.reminder)C.reminder.preopen();act(async()=>{const result=await C.api('/api/v1/auth/login','POST',{phone,code});C.token=result.token;const me=await C.api('/api/v1/auth/me');const list=me.memberships.filter(m=>C.role==='resource'?['broker','bank','insurance'].includes(m.kind):m.kind===C.role);if(!list.length){await C.api('/api/v1/auth/logout','POST',{});C.token='';C.reminder?.close();throw new Error('此手机号没有当前后台身份，请确认登录入口');}if(list.length===1)finish(list[0]);else{setMembers(list);setChosen(list[0].id);}});}
    return h('div',{className:'login-page'},h('div',{className:'login-brand'},'齿慧通'),h(A.Card,{className:'login',title:roleNames[C.role]+' · 登录'},h(A.Space,{direction:'vertical',size:16,style:{width:'100%'}},notice&&h(A.Alert,{type:'warning',content:notice}),h(C.Error,{error}),members.length?h('div',null,h(A.Select,{value:chosen,onChange:setChosen,options:members.map(m=>({value:m.id,label:m.organization_name+' · '+C.text('role',m.role)})),style:{width:'100%'}}),h(A.Button,{type:'primary',long:true,onClick:()=>finish(members.find(m=>m.id===chosen)),style:{marginTop:16}},'进入工作台')):h(React.Fragment,null,h('label',{className:'login-field'},'手机号',h(A.Input,{value:phone,onChange:v=>{setPhone(v);setSms(null);},'aria-label':'手机号',autoComplete:'off',maxLength:40})),h('div',{className:'login-code'},h('label',{className:'login-field'},'验证码',h(A.Input,{value:code,onChange:setCode,maxLength:6,'aria-label':'验证码',autoComplete:'one-time-code',onPressEnter:login})),h(A.Button,{disabled:wait>0,loading:busy,onClick:()=>act(async()=>{await C.api('/api/v1/auth/code','POST',{phone});setWait(60);setSms(null);A.Message.success('验证码已生成，请在测试短信箱查看');})},wait?wait+'秒后重试':'获取验证码')),h(A.Button,{type:'text',onClick:()=>act(async()=>setSms(await C.api('/acceptance/sms','POST',{phone})))},'查看测试短信箱'),sms&&h(A.Alert,{type:'info',content:'本次验证码：'+sms.code+'（5分钟内有效，仅可使用一次）'}),C.role==='clinic'&&h(A.Checkbox,{checked:reminder,onChange:v=>{setReminder(v);try{localStorage.setItem('chihuitong.clinic.reminder',v?'on':'off');}catch{A.Message.warning('浏览器未允许保存本机提醒偏好');}}},'登录时开启预约提醒'),h(A.Button,{type:'primary',long:true,loading:busy,onClick:login},'登录')))),h('p',{className:'login-note'},'受保护的合成数据验收环境 · 不要录入真实客户资料'));
  }
  const menus={
    platform:[['workbench','工作台'],['tasks','待处理任务'],['institutions','机构管理'],['clinics','门诊管理'],['products','推广产品'],['sales','推广产品销售'],['appointments','预约管理'],['clinicBills','门诊账单'],['partnerBills','合作方结算单'],['overview','客户与权益概览'],['notifications','站内消息'],['sms','短信管理'],['jobs','系统任务'],['calendar','工作日日历'],['accounts','账号管理']],
    resource:[['workbench','工作台'],['tasks','待处理任务'],['sales','推广产品销售'],['overview','客户与权益概览'],['appointments','预约与核销明细'],['partnerBills','合作方结算单'],['cooperation','合作合同与推广产品'],['notifications','站内消息'],['accounts','账号管理']],
    channel:[['workbench','工作台'],['tasks','待处理任务'],['clinics','门诊管理'],['appointments','预约与核销明细'],['clinicBills','门诊账单'],['partnerBills','合作方结算单'],['cooperation','合作合同与推广产品'],['notifications','站内消息'],['accounts','账号管理']],
    clinic:[['workbench','工作台'],['tasks','待处理任务'],['appointments','预约管理'],['overdue','过期预约待办'],['clinics','门诊资料'],['clinicBills','门诊账单'],['notifications','站内消息'],['accounts','账号管理']]
  };
  C.navigate=key=>C.events.dispatchEvent(new CustomEvent('navigate',{detail:key}));
  class Boundary extends React.Component{
    constructor(props){super(props);this.state={error:false};}
    static getDerivedStateFromError(){return {error:true};}
    render(){return this.state.error?h(A.Result,{status:'error',title:'页面暂时无法显示',subTitle:'数据未被修改。请返回工作台重试。',extra:h(A.Button,{onClick:()=>{this.setState({error:false});C.navigate('workbench');}},'返回工作台')}):this.props.children;}
  }
  function App(){
    const [member,setMember]=React.useState(null),[page,setPage]=React.useState('workbench'),[notice,setNotice]=React.useState('');
    React.useEffect(()=>{const expired=()=>{setMember(null);setNotice('登录已失效，请重新验证手机号');C.reminder?.close();};const navigate=e=>setPage(e.detail);C.events.addEventListener('expired',expired);C.events.addEventListener('navigate',navigate);return()=>{C.events.removeEventListener('expired',expired);C.events.removeEventListener('navigate',navigate);};},[]);
    if(!C.role)return h('main',{className:'entry'},h('h1',null,'齿慧通 · 后台入口'),h(A.Alert,{type:'warning',content:'独立合成验收环境，短信与支付仅作模拟，不发生真实外发或资金往来。'}),h(A.Space,{direction:'vertical',size:16},Object.entries(roleNames).map(([key,name])=>h(A.Button,{key,href:'/chihuitong/'+key+'/'},name))));
    if(!member)return h(Login,{notice,onLogin:m=>{setMember(m);setPage('workbench');setNotice('');}});
    const links=menus[C.role].filter(([key])=>C.pages[key]).filter(([key])=>member.role==='admin'||!(key==='accounts'||(C.role==='clinic'&&['clinicBills','clinics','cooperation'].includes(key)))).map(([key,title])=>[key,key==='partnerBills'&&member.role==='staff'?'本人结算明细':title]);
    const Component=C.pages[page]||C.pages.workbench;
    const logout=async()=>{try{await C.api('/api/v1/auth/logout','POST',{});}catch(e){A.Message.error(e.message);return;}C.token='';C.actor=null;C.events.dispatchEvent(new Event('logout'));C.reminder?.close();setMember(null);};
    return h(React.Fragment,null,h('header',{className:'shell-header'},h('div',{className:'brand'},h('span',{className:'brand-mark'},'齿'),'齿慧通',h('span',{className:'role-name'},roleNames[C.role])),h('div',{className:'header-right'},h('span',{className:'org-label'},member.organization_name),h(A.Tag,null,C.text('role',member.role)),h(A.Button,{onClick:logout},'退出登录'))),h('aside',{className:'sidebar'},h('div',{className:'org-block'},h('strong',null,member.organization_name),h('span',{className:'muted'},member.role==='admin'?'本机构全部授权数据':'仅本人负责的业务数据')),h(A.Menu,{selectedKeys:[page],onClickMenuItem:key=>{C.taskCategory='all';setPage(key);}},links.map(([key,title])=>h(A.Menu.Item,{key},title)))),h('main',{className:'workspace'},h(A.Alert,{type:'warning',content:'合成数据验收环境 · 支付和短信仅作模拟，不代表真实到账或送达，请勿上传真实客户或付款资料。'}),h('div',{className:'page-heading'},h('h1',null,links.find(([key])=>key===page)?.[1]||'工作台')),h(Boundary,{key:page},h(Component)),h('footer',{className:'page-foot'},'齿慧通 · 业务数据按当前身份授权展示')),h(DialogHost));
  }
  ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();
