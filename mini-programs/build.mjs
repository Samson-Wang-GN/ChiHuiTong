import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

if(os.hostname()!=='VM-0-12-ubuntu'||process.platform!=='linux')throw new Error('仅允许在指定开发服务器构建');
const root=path.dirname(fileURLToPath(import.meta.url));
const destination=path.join(root,'dist');
if(fs.existsSync(destination))throw new Error('输出目录已存在，请使用新的隔离工作区构建');
execFileSync(process.execPath,[path.join(root,'node_modules/typescript/bin/tsc'),'-p',path.join(root,'tsconfig.json')],{stdio:'inherit'});
const routes=JSON.parse(fs.readFileSync(path.join(root,'routes.json'),'utf8'));
const publicConfig=process.env.CHT_MINI_BUILD_CONFIG?JSON.parse(fs.readFileSync(process.env.CHT_MINI_BUILD_CONFIG,'utf8')):{};
for(const audience of ['customer','clinic']){
  const folder=path.join(destination,audience);fs.mkdirSync(folder,{recursive:true});
  const input=publicConfig[audience]||{};
  for(const key of Object.keys(input))if(!['appid','apiBase','privacyReady'].includes(key))throw new Error('构建配置含非公开字段');
  const config={audience,appid:input.appid||'touristappid',apiBase:input.apiBase||'',privacyReady:input.privacyReady===true};
  if(config.apiBase&&!/^https:\/\/[a-zA-Z0-9.-]+(?::443)?(?:\/[a-zA-Z0-9_/-]*)?$/.test(config.apiBase))throw new Error('API地址必须为无凭证的HTTPS地址');
  if(config.appid!=='touristappid'&&!/^wx[a-fA-F0-9]{16}$/.test(config.appid))throw new Error('AppID格式错误');
  if(config.privacyReady&&(config.appid==='touristappid'||!config.apiBase))throw new Error('正式隐私授权须同时配置AppID和HTTPS地址');
  const write=(name,value)=>{const target=path.join(folder,name);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,value);};
  const json=(name,value)=>write(name,JSON.stringify(value,null,2)+'\n');
  fs.cpSync(path.join(root,'compiled/shared'),path.join(folder,'shared'),{recursive:true});
  fs.cpSync(path.join(root,'compiled',audience),path.join(folder,'domain'),{recursive:true});
  write('shared/config.js','exports.config = '+JSON.stringify(config)+';\n');
  write('shared/vendor/qrcode.js',fs.readFileSync(path.join(root,'node_modules/qrcode-generator/dist/qrcode.js')));
  // Upstream npm tarball embeds its license notice in the distributed source.
  write('NOTICE-qrcode.txt','qrcode-generator 2.0.4; Copyright (c) 2009 Kazuhiko Arase; MIT.\nThe original notice is retained verbatim in shared/vendor/qrcode.js.\nhttps://github.com/kazuhikoarase/qrcode-generator\n');
  write('app.js',`const runtime=require('./shared/runtime');\nApp({onLaunch(){runtime.clearSession();},onHide(){runtime.cleanFiles();}});\n`);
  write('app.wxss',fs.readFileSync(path.join(root,'native/app.wxss')));
  const tabs=audience==='customer'?[['home','首页'],['benefits','权益'],['appointments','预约'],['mine','我的']]:[['home','工作台'],['appointments','预约'],['scan','核销'],['mine','我的']];
  json('app.json',{pages:routes[audience].map(p=>'pages/'+p+'/index'),window:{navigationBarTitleText:audience==='customer'?'齿慧通':'齿慧通门诊',navigationBarBackgroundColor:'#ffffff',navigationBarTextStyle:'black',backgroundTextStyle:'dark',enablePullDownRefresh:true},tabBar:{color:'#6b7785',selectedColor:'#165dff',backgroundColor:'#ffffff',list:tabs.map(([p,text])=>({pagePath:'pages/'+p+'/index',text}))},style:'v2',lazyCodeLoading:'requiredComponents',...(audience==='customer'?{permission:{'scope.userLocation':{desc:'仅在您主动查找附近门诊时获取位置，用于计算门诊直线距离'}},requiredPrivateInfos:['getLocation']}:{}),sitemapLocation:'sitemap.json'});
  json('sitemap.json',{desc:'医疗预约页面不参与搜索索引',rules:[{action:'disallow',page:'*'}]});
  json('project.config.json',{appid:config.appid,projectname:'ChiHuiTong-'+audience,compileType:'miniprogram',miniprogramRoot:'./',setting:{urlCheck:true,es6:true,minified:true},packOptions:{ignore:[{type:'file',value:'BUILD.json'}]}});
  for(const page of routes[audience]){
    write('pages/'+page+'/index.js',`const {createPage}=require('../../shared/controller');\nconst {screens}=require('../../domain/screens');\nPage(createPage('${page}',screens));\n`);
    write('pages/'+page+'/index.wxml',fs.readFileSync(path.join(root,'native/page.wxml')));
    json('pages/'+page+'/index.json',{usingComponents:{'qr-code':'/components/qr/index'}});
    write('pages/'+page+'/index.wxss','');
  }
  write('components/qr/index.js',"require('../../shared/qr');\n");
  write('components/qr/index.wxml',fs.readFileSync(path.join(root,'native/qr.wxml')));
  write('components/qr/index.wxss','');json('components/qr/index.json',{component:true});
  json('BUILD.json',{audience,accountConfigured:config.appid!=='touristappid',realWechatAcceptance:false,source:process.env.CHT_SOURCE_COMMIT||'isolated-workspace'});
}
const hashes={};for(const file of fs.readdirSync(destination,{recursive:true}).sort()){const target=path.join(destination,file);if(fs.statSync(target).isFile())hashes[file]=crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex');}
fs.writeFileSync(path.join(destination,'manifest.json'),JSON.stringify(hashes,null,2)+'\n');
console.log('已生成两个独立原生工程；不代表通过微信原生编译或真机验收');
