import {config} from './config';
import {Entity, View} from './model';
import * as R from './runtime';
import {Context, Screen} from './screens';

const navigation = new Set(['home','benefits','appointments','mine','activate','messages','profile','privacy','tasks','fulfillment','notifications','cooperation','bills','contracts','products','membership']);
const detailNavigation = new Set(['appointment','bill','contract']);
const publicScreens:Record<string,Screen> = {
  login:{public:true,async load(){return {title:config.audience==='customer'?'齿慧通 · 客户登录':'齿慧通 · 门诊登录',notice:config.audience==='customer'?'授权手机号以领取您的权益和管理预约。':'请使用门诊后台已开通的管理员或员工手机号授权登录。',actions:[{key:'privacy',label:'阅读隐私说明'}]};}},
  privacy:{public:true,async load(){return {title:'隐私保护',notice:config.privacyReady?'请阅读并同意本小程序经审核的隐私保护指引。手机号用于身份识别，定位仅用于您主动查找门诊，扫码用于激活或核销，付款图片仅用于对账。':'小程序主体及正式隐私保护指引尚待配置。当前禁止手机号授权，不采集真实授权数据。',actions:config.privacyReady?[{key:'privacy-contract',label:'查看微信隐私保护指引'}]:[]};}},
  membership:{async load(){return {title:'选择门诊身份',notice:'请选择本次工作的门诊；切换后清除上一门诊的页面数据。',rows:(R.current()?.memberships||[]).map(m=>({id:m.id,title:m.organization_name,lines:[m.role==='admin'?'管理员':'员工'],actions:[{key:'select-membership',id:m.id,label:'进入该门诊'}]}))};}},
};

// Exposed only for deterministic server tests; native wrappers register this object as Page.
export function createPage(name:string, registry:Record<string,Screen>):Entity {
  const screen=registry[name]||publicScreens[name];
  if(!screen)throw new Error('页面未注册');
  return {
    data:{view:{title:'加载中'},form:{},busy:false,error:'',activeStatus:'all',isLogin:name==='login',privacyReady:config.privacyReady,privacyAgreed:false},
    ctx:{params:{},form:{},status:['tasks','fulfillment','messages'].includes(name)?'pending':'all',page:1,cache:{}} as Context,
    visible:false,sequence:0,
    onLoad(this:Entity,params:Entity){this.ctx={params,form:{},status:['tasks','fulfillment','messages'].includes(name)?'pending':'all',page:1,cache:{}};},
    async onShow(this:Entity){this.visible=true;this.ctx.params={...this.ctx.params,...R.consumeNavigation()};await this.reload(true);},
    onHide(this:Entity){this.visible=false;this.sequence++;this.setData({'view.qr':''});},
    onUnload(this:Entity){this.visible=false;this.sequence++;this.ctx={params:{},form:{},status:'all',page:1,cache:{}};this.setData({view:{},form:{}});},
    async onPullDownRefresh(this:Entity){try{await this.reload(true);}finally{wx.stopPullDownRefresh();}},
    async guard(this:Entity,refresh=false){
      if(screen.public)return true;
      if(!R.current()){wx.reLaunch({url:'/pages/login/index'});return false;}
      if(refresh)await R.refreshIdentity();
      if(config.audience==='clinic'&&!R.current()?.membership&&name!=='membership'){wx.reLaunch({url:'/pages/membership/index'});return false;}
      if(screen.admin)R.requireAdmin();
      return true;
    },
    async reload(this:Entity,refresh=false){
      const seq=++this.sequence;
      try {
        this.setData({busy:true,error:''});
        if(!await this.guard(refresh))return;
        const view:View=await screen.load(this.ctx);
        if(!this.visible||seq!==this.sequence)return;
        for(const field of view.fields||[])if(this.ctx.form[field.key]===undefined)this.ctx.form[field.key]=field.value??(field.type==='checkbox'?false:'');
        this.setData({view,form:{...this.ctx.form},activeStatus:this.ctx.status});
        wx.setNavigationBarTitle({title:view.title});
      }catch(e){if(seq===this.sequence)this.showError(e);}finally{if(seq===this.sequence)this.setData({busy:false});}
    },
    showError(this:Entity,e:unknown){const error=e as Error & {status?:number};this.setData({error:error.message||'操作未完成，请稍后重试',...(error.status===401||error.status===403?{view:{title:'暂不可访问'},form:{}}:{})});if(error.status===401)wx.reLaunch({url:'/pages/login/index'});},
    change(this:Entity,e:Entity){const key=e.currentTarget.dataset.key;const type=e.currentTarget.dataset.type;let value=e.detail.value;if(type==='checkbox')value=value.includes('yes');if(type==='picker'){const f=this.data.view.fields.find((x:Entity)=>x.key===key);value=f.options[Number(value)];}this.ctx.form[key]=value;this.setData({form:{...this.ctx.form}});},
    consent(this:Entity,e:Entity){this.setData({privacyAgreed:e.detail.value.includes('yes')});},
    async authorize(this:Entity,e:Entity){if(this.data.busy)return;this.setData({busy:true,error:''});try{if(!this.data.privacyAgreed)throw new Error('请先阅读并同意隐私保护指引');await R.login(e.detail.code||'');wx.reLaunch({url:'/pages/'+(config.audience==='clinic'&&!R.current()?.membership?'membership':'home')+'/index'});}catch(error){this.showError(error);}finally{this.setData({busy:false});}},
    async privacyContract(this:Entity){await new Promise<void>((resolve,reject)=>wx.openPrivacyContract({success:()=>resolve(),fail:()=>reject(new Error('隐私保护指引暂不可用，请联系平台'))}));},
    async act(this:Entity,e:Entity){if(this.data.busy)return;const {key,id}=e.currentTarget.dataset;this.setData({busy:true,error:''});try{
      if(!await this.guard())return;
      if(key==='retry'){await this.reload(true);return;}
      if(key==='privacy-contract'){await this.privacyContract();return;}
      if(key==='logout'){if(await R.confirm('确认退出当前账号？')){try{await R.logout();}finally{wx.reLaunch({url:'/pages/login/index'});}}return;}
      if(key==='select-membership'){R.selectMembership(id);wx.reLaunch({url:'/pages/home/index'});return;}
      if(key==='attachment'){R.requireAdmin();await R.attachment(id);return;}
      if(navigation.has(key)){R.go(key);return;}
      if(detailNavigation.has(key)){R.go(key,{id});return;}
      await screen.action?.(this.ctx,key,id);
      await this.reload();
    }catch(error){this.showError(error);}finally{this.setData({busy:false});}},
    async submit(this:Entity){if(this.data.busy)return;this.setData({busy:true,error:''});try{if(!await this.guard())return;await screen.submit?.(this.ctx);await this.reload();}catch(error){this.showError(error);}finally{this.setData({busy:false});}},
    async status(this:Entity,e:Entity){if(this.data.busy)return;this.ctx.status=e.currentTarget.dataset.key;this.ctx.page=1;await this.reload();},
    async paginate(this:Entity,e:Entity){if(this.data.busy)return;const next=this.ctx.page+Number(e.currentTarget.dataset.delta);if(next<1)return;this.ctx.page=next;await this.reload();},
  };
}
