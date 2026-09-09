/* REQ-039: real Document PiP; all appointment events remain role-local demos. */
window.ClinicFloating = (() => {
  const h=React.createElement,{useState,useRef,useEffect}=React,{Button,Tag,Alert,Tabs}=arco;
  function Workbench({pages,save,onOpen}) {
    const [target,setTarget]=useState(null),[opening,setOpening]=useState(false),[error,setError]=useState(''),[scheduled,setScheduled]=useState(false),[notice,setNotice]=useState('');
    const live=useRef({pages,save,onOpen}),pip=useRef(null),timer=useRef(null),alive=useRef(true),openingRef=useRef(false);
    live.current={pages,save,onOpen};
    const appointments=pages.find(p=>p.id==='appointments')?.rows||[],pending=appointments.filter(a=>a.status==='待确认');
    const supported=window.isSecureContext&&!!window.documentPictureInPicture&&window.top===window;
    useEffect(()=>{alive.current=true;const close=()=>{alive.current=false;clearTimeout(timer.current);const win=pip.current||window.documentPictureInPicture?.window;if(win&&!win.closed)win.close();};window.addEventListener('pagehide',close);return()=>{window.removeEventListener('pagehide',close);close();};},[]);
    function addDemo(){
      if(!alive.current)return;
      const next=JSON.parse(JSON.stringify(live.current.pages)),p=next.find(p=>p.id==='appointments');
      if(!p){setError('未找到本门诊预约数据，请刷新后重试。');return;}
      const id='PIP-'+Date.now()+'-'+Math.random().toString(36).slice(2,5);
      p.rows.unshift({id,name:'悬浮提醒测试客户（演示）',clinic:PROTOTYPE.org,scheme:'舒适洁牙权益',date:'2026-09-08',time:'14:00',intent:'2026-09-08 14:00',expiry:'2027-03-06',status:'待确认',quantity:1,held:1,used:0,fee:60,note:'悬浮工作台模拟预约；非真实客户，不发送短信',floatingDemo:true});
      live.current.save(next);setNotice(id);setScheduled(false);timer.current=null;
    }
    function schedule(){if(timer.current)return;setScheduled(true);timer.current=setTimeout(addDemo,5000);}
    function cancelTimer(){clearTimeout(timer.current);timer.current=null;setScheduled(false);}
    async function open(){
      setError('');if(pip.current&&!pip.current.closed){pip.current.focus();return;}
      if(!supported){setError('当前环境不支持独立悬浮窗。请用支持文档画中画的桌面Chrome/Edge，直接打开 http://127.0.0.1:8765/clinic/；不要使用嵌入预览。');return;}
      if(openingRef.current)return;openingRef.current=true;setOpening(true);
      try{
        const win=await window.documentPictureInPicture.requestWindow({width:400,height:520});
        if(!alive.current){win.close();return;}pip.current=win;
        win.document.title='齿慧通 · 前台预约提醒';win.document.documentElement.lang='zh-CN';
        for(const href of ['../shared/vendor/arco.min.css','floating.css']){const link=win.document.createElement('link');link.rel='stylesheet';link.href=new URL(href,location.href).href;win.document.head.append(link);}
        win.document.body.className='floating-document';const host=win.document.createElement('div');win.document.body.append(host);setTarget(host);
        win.addEventListener('pagehide',()=>{if(pip.current===win){pip.current=null;if(alive.current)setTarget(null);}},{once:true});
      }catch(e){if(alive.current)setError('悬浮窗未能打开（'+(e.name||'浏览器限制')+'）。请回到原后台点击开启，检查浏览器支持和窗口策略后重试。');}
      finally{openingRef.current=false;if(alive.current)setOpening(false);}
    }
    function process(id){window.focus();live.current.onOpen(id);}
    const controls=h('div',{className:'floating-demo-actions'},h(Button,{size:'small',onClick:addDemo,disabled:scheduled},'模拟新预约'),h(Button,{size:'small',onClick:scheduled?cancelTimer:schedule},scheduled?'取消延时模拟':'5秒后模拟新预约'));
    const content=h('section',{className:'floating-content'},h('header',null,h('strong',null,'齿慧通 · 前台工作台'),h(Tag,{color:'arcoblue'},'独立悬浮窗')),h('p',{className:'floating-muted'},'本门诊 · 演示数据，无服务端连接'),
      h('section',{className:'floating-count',key:notice||'initial'},h('div',{'aria-live':'polite'},h('strong',null,pending.length),h('span',null,'条预约待确认')),h('p',null,pending.length?'请及时联系客户，确认预约时间':'暂无待确认预约')),
      pending.some(a=>a.id===notice)&&h(Alert,{type:'warning',content:'收到一条模拟新预约，请返回后台处理。'}),scheduled&&h(Alert,{content:'约5秒后新增演示预约；切换Tab即可观察，后台计时可能延迟。'}),
      h(Tabs,{type:'line',activeTab:'pending'},h(Tabs.TabPane,{key:'pending',title:'待确认（'+pending.length+'）'},pending.length?h('div',null,...pending.slice(0,3).map(a=>h('article',{key:a.id,className:'floating-row'},h('div',null,h('strong',null,a.id),h('p',null,'意向 '+a.date+' '+a.time)),h(Button,{type:'primary',size:'small',onClick:()=>process(a.id)},'去确认'))),pending.length>3&&h('p',{className:'floating-muted'},'另有'+(pending.length-3)+'条，请到后台查看。')):h('p',{className:'floating-empty'},'待办已处理完毕，您可继续其他工作。'))),
      h(Button,{long:true,type:'primary',onClick:()=>process(null)},'返回后台处理预约'),h('footer',null,controls,h('p',{className:'floating-muted'},'仅模拟，不发送短信；关闭窗口不会确认或取消预约。'),h(Button,{type:'text',onClick:()=>pip.current?.close()},'关闭悬浮窗')));
    return h('section',{className:'floating-launcher'},h('div',null,h('strong',null,'前台悬浮提醒'),h('span',{className:'floating-muted'},target?'已开启 · 切换页签仍可查看':'主动开启后，可拖动到屏幕角落')),h('div',{className:'floating-launch-actions'},h(Button,{type:'primary',loading:opening,onClick:open},target?'查看悬浮工作台':'开启悬浮工作台'),controls),error&&h(Alert,{type:'warning',content:error}),scheduled&&h('p',null,'约5秒后新增模拟预约，现在可以切换Tab观察。'),target&&ReactDOM.createPortal(content,target));
  }
  return {Workbench};
})();
